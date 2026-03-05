"""Network benchmark and mTLS verification helpers for ATHENA-rods."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import socket
import ssl
import threading
from typing import Optional


def recv_exact(sock: socket.socket, nbytes: int) -> bytes:
    """Receive exactly ``nbytes`` or raise ``ConnectionError``."""
    chunks = bytearray()
    while len(chunks) < nbytes:
        data = sock.recv(nbytes - len(chunks))
        if not data:
            raise ConnectionError("Socket closed while receiving data")
        chunks.extend(data)
    return bytes(chunks)


def _cert_path(cert_dir: Path, name: str) -> Path:
    path = cert_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Missing certificate file: {path}")
    return path


def create_tls_server_context(cert_dir: Path, require_client_cert: bool = True) -> ssl.SSLContext:
    """Create server-side TLS context using ATHENA certificate layout."""
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(
        certfile=str(_cert_path(cert_dir, "server.crt")),
        keyfile=str(_cert_path(cert_dir, "server.key")),
    )
    ctx.load_verify_locations(cafile=str(_cert_path(cert_dir, "ca.crt")))
    ctx.verify_mode = ssl.CERT_REQUIRED if require_client_cert else ssl.CERT_NONE
    return ctx


def create_tls_client_context(
    cert_dir: Path,
    with_client_cert: bool = True,
    trust_athena_ca: bool = True,
) -> ssl.SSLContext:
    """Create client-side TLS context for local loopback tests."""
    if trust_athena_ca:
        ctx = ssl.create_default_context(cafile=str(_cert_path(cert_dir, "ca.crt")))
    else:
        ctx = ssl.create_default_context()

    ctx.check_hostname = False
    if with_client_cert:
        ctx.load_cert_chain(
            certfile=str(_cert_path(cert_dir, "instbox.crt")),
            keyfile=str(_cert_path(cert_dir, "instbox.key")),
        )
    return ctx


@dataclass
class LocalEchoServer:
    """Small loopback echo server used by benchmark/test scripts."""

    host: str = "127.0.0.1"
    port: int = 0
    tls_context: Optional[ssl.SSLContext] = None

    def __post_init__(self) -> None:
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.bound_port: Optional[int] = None
        self._startup_error: Optional[Exception] = None

    def start(self) -> None:
        """Start background server thread."""
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise TimeoutError("Echo server failed to start")
        if self._startup_error is not None:
            raise RuntimeError("Echo server startup failed") from self._startup_error

    def _serve(self) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((self.host, self.port))
                listener.listen(4)
                listener.settimeout(0.5)
                self.bound_port = listener.getsockname()[1]
                self._ready.set()

                while not self._stop.is_set():
                    try:
                        conn, _addr = listener.accept()
                    except socket.timeout:
                        continue
                    except OSError:
                        break

                    try:
                        if self.tls_context is not None:
                            conn = self.tls_context.wrap_socket(conn, server_side=True)

                        with conn:
                            conn.settimeout(1.0)
                            while not self._stop.is_set():
                                try:
                                    data = conn.recv(8192)
                                except socket.timeout:
                                    continue
                                if not data:
                                    break
                                conn.sendall(data)
                    except ssl.SSLError:
                        # Intentional in negative security tests.
                        continue
                    except OSError:
                        continue
        except Exception as exc:  # noqa: BLE001 - store startup error for caller
            self._startup_error = exc
            self._ready.set()

    def stop(self) -> None:
        """Stop server thread and release resources."""
        self._stop.set()
        # Nudge accept() out of blocking state.
        if self.bound_port is not None:
            try:
                with socket.create_connection((self.host, self.bound_port), timeout=0.2):
                    pass
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def __enter__(self) -> "LocalEchoServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
