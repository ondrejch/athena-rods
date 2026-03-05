#!/usr/bin/env python3
"""Tests for local network benchmark helpers."""

from pathlib import Path
import socket
import errno

import pytest

from arod_common.netbench import (
    LocalEchoServer,
    create_tls_client_context,
    create_tls_server_context,
    recv_exact,
)


def _is_socket_permission_error(exc: BaseException) -> bool:
    """Return ``True`` when test failures come from restricted sockets."""
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, PermissionError):
            return True
        if isinstance(current, OSError) and current.errno in {errno.EPERM, errno.EACCES}:
            return True
        current = current.__cause__ or current.__context__
    return False


def _skip_if_socket_restricted(exc: BaseException) -> None:
    if _is_socket_permission_error(exc):
        pytest.skip("Loopback sockets are not permitted in this environment")


def test_local_echo_server_plain_round_trip() -> None:
    try:
        with LocalEchoServer() as server:
            with socket.create_connection(("127.0.0.1", int(server.bound_port)), timeout=2.0) as sock:
                payload = b"athena-netbench"
                sock.sendall(payload)
                assert recv_exact(sock, len(payload)) == payload
    except Exception as exc:  # noqa: BLE001 - skip on restricted CI sandboxes
        _skip_if_socket_restricted(exc)
        raise


def test_local_echo_server_mtls_round_trip() -> None:
    cert_dir = Path("etc") / "certs"
    if not cert_dir.exists():
        pytest.skip("TLS cert directory not available")

    try:
        server_ctx = create_tls_server_context(cert_dir=cert_dir, require_client_cert=True)
        with LocalEchoServer(tls_context=server_ctx) as server:
            raw = socket.create_connection(("127.0.0.1", int(server.bound_port)), timeout=3.0)
            client_ctx = create_tls_client_context(cert_dir=cert_dir, with_client_cert=True, trust_athena_ca=True)
            with raw:
                with client_ctx.wrap_socket(raw, server_hostname="ctrlbox") as tls_sock:
                    payload = b"secure-echo"
                    tls_sock.sendall(payload)
                    assert recv_exact(tls_sock, len(payload)) == payload
    except Exception as exc:  # noqa: BLE001 - skip on restricted CI sandboxes
        _skip_if_socket_restricted(exc)
        raise
