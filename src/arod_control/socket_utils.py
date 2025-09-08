#!/usr/bin/env python3
"""
Socket communication utilities for ATHENA-rods with X.509 certificate-based encryption
"""

import socket
import time
import logging
import threading
import json
import struct
import ssl
import os
from typing import Tuple, Optional, Dict, Any, Union
from arod_control import AUTH_ETC_PATH

logger = logging.getLogger('SocketUtils')
logger.setLevel(logging.INFO)  # Ensure we're capturing appropriate log level


class SocketManager:
    """Manager for socket connections with reconnection capabilities and SSL/TLS support"""

    def __init__(self, host: str, port: int, handshake: str, use_ssl: bool = True,
                 cert_dir: str = os.path.join(os.path.expanduser('~'), "%s/certs" % AUTH_ETC_PATH),
                 server_mode: bool = False):
        """Initialize socket manager with connection parameters

        Args:
            host (str): Host to connect to
            port (int): Port number
            handshake (str): Handshake string to send on connection
            use_ssl (bool): Whether to use SSL/TLS encryption
            cert_dir (str): Directory containing certificates
            server_mode (bool): Whether this is a server socket
        """
        self.host = host
        self.port = port
        self.handshake = handshake
        self.use_ssl = use_ssl
        self.server_mode = server_mode
        self.cert_dir = os.path.expanduser(cert_dir)
        self.socket: Optional[Union[socket.socket, ssl.SSLSocket]] = None
        self.ssl_context: Optional[ssl.SSLContext] = None
        self.connected = False
        # Use a re-entrant lock to allow nested acquisition within class methods
        self.lock = threading.RLock()
        self.buffer = b""
        self.reconnect_delay = 1  # Starting delay (seconds)
        self.max_delay = 30  # Maximum delay (seconds)
        self._shutdown_requested = False

        # Initialize SSL context if SSL is enabled
        if self.use_ssl:
            self._init_ssl_context()

    def _init_ssl_context(self):
        """Initialize SSL context with certificates"""
        try:
            # Create SSL context with modern security settings
            self.ssl_context = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH if not self.server_mode else ssl.Purpose.CLIENT_AUTH)

            # Server and client setup differ
            if self.server_mode:
                # Server needs certificate and private key
                self.ssl_context.verify_mode = ssl.CERT_REQUIRED
                self.ssl_context.load_cert_chain(certfile=os.path.join(self.cert_dir, "server.crt"),
                    keyfile=os.path.join(self.cert_dir, "server.key"))
                # Load CA certificate to verify client certificates
                self.ssl_context.load_verify_locations(cafile=os.path.join(self.cert_dir, "ca.crt"))
            else:
                # Client configuration
                # Determine client certificate name from handshake
                if "instr" in self.handshake:
                    client_name = "instbox"
                elif "display" in self.handshake:
                    client_name = "visbox"
                else:
                    # Fallback for other potential clients, though not currently used
                    client_name = self.handshake

                logger.info(f"Loading client certificate for '{client_name}' based on handshake '{self.handshake}'")

                # Load client certificate and key
                client_cert = os.path.join(self.cert_dir, f"{client_name}.crt")
                client_key = os.path.join(self.cert_dir, f"{client_name}.key")

                if os.path.exists(client_cert) and os.path.exists(client_key):
                    self.ssl_context.load_cert_chain(certfile=client_cert, keyfile=client_key)
                else:
                    logger.error(
                        f"Client certificate or key not found: {client_cert} / {client_key}")  # This will likely cause a connection failure, which is appropriate

                # Load CA certificate for server verification
                self.ssl_context.load_verify_locations(cafile=os.path.join(self.cert_dir, "ca.crt"))

                # Check hostname (for clients)
                self.ssl_context.check_hostname = True

            logger.info("SSL context initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing SSL context: {e}")
            self.ssl_context = None

    def connect(self, timeout: float = 10.0) -> bool:
        """Connect to the server with timeout

        Args:
            timeout (float): Socket timeout in seconds

        Returns:
            bool: True if connected successfully, False otherwise
        """
        if self._shutdown_requested:
            return False

        with self.lock:
            try:
                # Clean up any existing socket first
                if self.socket:
                    try:
                        self.socket.shutdown(socket.SHUT_RDWR)
                    except:
                        pass
                    try:
                        self.socket.close()
                    except:
                        pass
                    self.socket = None
                    self.connected = False

                # Create new socket
                plain_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                plain_socket.settimeout(timeout)

                # Connect and wrap with SSL if enabled
                logger.info(f"Attempting to connect to {self.host}:{self.port} ({self.handshake})")
                plain_socket.connect((self.host, self.port))

                if self.use_ssl and self.ssl_context:
                    try:
                        self.socket = self.ssl_context.wrap_socket(plain_socket,
                            server_hostname=self.host if not self.server_mode else None)
                        logger.info(f"SSL handshake completed - Cipher: {self.socket.cipher()}")
                    except ssl.SSLError as ssl_err:
                        logger.error(f"SSL handshake failed: {ssl_err}")
                        plain_socket.close()
                        return False
                else:
                    self.socket = plain_socket

                # Send handshake with newline
                handshake_bytes = self.handshake.encode('utf-8') + b'\n'
                self.socket.sendall(handshake_bytes)

                # Connection successful
                self.connected = True
                self.reconnect_delay = 1  # Reset delay on successful connection
                logger.info(f"Successfully connected to {self.host}:{self.port} ({self.handshake})")
                return True
            except Exception as e:
                logger.error(f"Connection failed to {self.host}:{self.port}: {e}")
                self.connected = False
                if self.socket:
                    try:
                        self.socket.close()
                    except Exception:
                        pass
                    self.socket = None
                return False

    def close(self):
        """Close the socket connection safely with timeout to prevent deadlocks"""
        self._shutdown_requested = True  # Set this flag outside the lock

        # Try to acquire lock with timeout
        lock_acquired = False
        try:
            lock_acquired = self.lock.acquire(timeout=2.0)  # 2 second timeout
            if lock_acquired:
                if self.socket:
                    try:
                        self.socket.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                    try:
                        self.socket.close()
                    except Exception as e:
                        logger.warning(f"Error closing socket: {e}")
                    finally:
                        self.socket = None
                        self.connected = False
                        logger.info(f"Socket closed ({self.handshake})")
            else:
                logger.warning(f"Could not acquire lock to close socket {self.handshake} cleanly")
                # Force close without lock if we couldn't acquire it
                if self.socket:
                    try:
                        self.socket.close()
                        logger.info(f"Socket {self.handshake} force-closed without lock")
                    except Exception:
                        pass
                    self.socket = None
                    self.connected = False
        finally:
            if lock_acquired:
                self.lock.release()

    # ... [rest of methods remain the same - connect_with_backoff, send_binary, etc.] ...

    def connect_with_backoff(self, max_attempts: Optional[int] = None) -> bool:
        """Connect with exponential backoff retry logic

        Args:
            max_attempts (Optional[int]): Maximum number of attempts or None for unlimited

        Returns:
            bool: True if connected successfully, False otherwise
        """
        if self._shutdown_requested:
            return False

        attempts = 0
        current_delay = self.reconnect_delay

        while (max_attempts is None or attempts < max_attempts) and not self._shutdown_requested:
            if self.connect():
                return True

            attempts += 1
            logger.info(f"Retrying connection in {current_delay}s (attempt {attempts})")

            # Sleep with early exit possibility if shutdown requested
            start_time = time.time()
            while time.time() - start_time < current_delay:
                if self._shutdown_requested:
                    return False
                time.sleep(0.1)

            # Increase backoff delay for next attempt
            current_delay = min(current_delay * 2, self.max_delay)

        logger.error(f"Failed to connect after {attempts} attempts")
        return False

    def send_binary(self, data: bytes) -> bool:
        """Send binary data with reconnection logic

        Args:
            data (bytes): Binary data to send

        Returns:
            bool: True if sent successfully, False otherwise
        """
        if self._shutdown_requested:
            return False

        with self.lock:
            if not self.connected:
                if not self.connect_with_backoff(max_attempts=1):
                    return False

            try:
                assert self.socket is not None
                self.socket.sendall(data)
                return True
            except Exception as e:
                logger.error(f"Error sending data: {e}")
                self.connected = False
                return False

    def send_json(self, data: Dict[str, Any]) -> bool:
        """Send JSON data with reconnection logic

        Args:
            data (Dict[str, Any]): JSON data to send

        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            json_str = json.dumps(data) + '\n'
            return self.send_binary(json_str.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error encoding JSON data: {e}")
            return False

    def receive(self, size: int) -> Tuple[bytes, bool]:
        """Receive binary data with reconnection logic

        Args:
            size (int): Number of bytes to receive

        Returns:
            Tuple[bytes, bool]: (data, success) where success is True if received successfully
        """
        if self._shutdown_requested:
            return b"", False

        with self.lock:
            if not self.connected:
                if not self.connect_with_backoff(max_attempts=1):
                    return b"", False

            try:
                assert self.socket is not None
                data = self.socket.recv(size)
                if not data:
                    logger.info("Connection closed by peer")
                    self.connected = False
                    return b"", False
                return data, True
            except socket.timeout:
                # Timeout is not a connection error, just no data available
                return b"", True
            except Exception as e:
                logger.error(f"Error receiving data: {e}")
                self.connected = False
                return b"", False

    def receive_exactly(self, size: int, timeout: float = 5.0) -> Tuple[bytes, bool]:
        """Receive exactly the specified number of bytes

        Args:
            size (int): Number of bytes to receive
            timeout (float): Timeout in seconds

        Returns:
            Tuple[bytes, bool]: (data, success) where success is True if received successfully
        """
        if self._shutdown_requested:
            return b"", False

        result = b""
        end_time = time.time() + timeout

        while len(result) < size and time.time() < end_time and not self._shutdown_requested:
            remaining = size - len(result)

            # Use shorter timeouts for individual receives to allow for shutdown checks
            with self.lock:
                if self.socket:
                    try:
                        self.socket.settimeout(min(0.5, max(0.0, end_time - time.time())))
                    except Exception:
                        pass

            chunk, success = self.receive(remaining)

            if self._shutdown_requested:
                return b"", False

            if not success and not chunk:
                # Actual error (not just timeout)
                return b"", False

            if chunk:
                result += chunk
                if len(result) == size:
                    return result, True

            # Small delay to avoid tight loop, check for shutdown
            time.sleep(0.01)

        return result, len(result) == size

    def receive_json(self) -> Tuple[Dict[str, Any], bool]:
        """Receive and parse a single line-delimited JSON object.

        Returns:
            (data, success): data is the parsed dict or {}, success indicates the I/O call didn't hard-fail.
            success can be True with {} when no complete JSON line is available yet.
        """
        if self._shutdown_requested:
            return {}, False

        # Briefly set a shorter timeout while holding the lock
        with self.lock:
            if self.socket:
                try:
                    self.socket.settimeout(0.5)
                except Exception:
                    pass

        # Perform the potentially blocking recv outside of the lock to avoid nested locking
        data, success = self.receive(1024)
        if not success and not data:
            # Hard failure or remote closed
            return {}, False

        if data:
            # Safely append to internal buffer
            with self.lock:
                self.buffer += data

        # Try to parse a complete line-delimited JSON message
        with self.lock:
            if b'\n' not in self.buffer:
                # No full line yet; not an error
                return {}, True

            line, self.buffer = self.buffer.split(b'\n', 1)

        if not line.strip():
            # Empty line; not an error
            return {}, True

        # Try JSON first
        try:
            result = json.loads(line.decode('utf-8'))
            return result, True
        except json.JSONDecodeError:
            # Swallow common non-JSON control acks silently if any ever appear
            try:
                text = line.decode('utf-8', errors='ignore').strip()
                if text.startswith('OK:') or text.startswith('REJECT:'):
                    return {}, True
            except Exception:
                pass
            # Not JSON; ignore this line without failing the stream
            return {}, True


class StreamingPacket:
    """Helpers for streaming binary packets."""

    # Sizes for packet formats
    PACKET_SIZE_TRIPLET = 12  # 3 x float32
    PACKET_SIZE_QUAD = 16  # 4 x float32
    PACKET_SIZE_TIME64 = 20  # 3 x float32 + 1 x float64 (timestamp ms)

    @staticmethod
    def pack_float_triplet(val1: float, val2: float, val3: float) -> bytes:
        """Pack three floats (big-endian)."""
        return struct.pack('!fff', val1, val2, val3)

    @staticmethod
    def unpack_float_triplet(data: bytes) -> Tuple[float, float, float]:
        """Unpack three floats (big-endian)."""
        return struct.unpack('!fff', data)

    @staticmethod
    def pack_float_quad(val1: float, val2: float, val3: float, val4: float) -> bytes:
        """Pack four floats (big-endian)."""
        return struct.pack('!ffff', val1, val2, val3, val4)

    @staticmethod
    def unpack_float_quad(data: bytes) -> Tuple[float, float, float, float]:
        """Unpack four floats (big-endian)."""
        return struct.unpack('!ffff', data)

    @staticmethod
    def pack_triplet_plus_time64(val1: float, val2: float, val3: float, t_ms: float) -> bytes:
        """Pack three float32 values plus one float64 timestamp in milliseconds."""
        return struct.pack('!fffd', val1, val2, val3, t_ms)

    @staticmethod
    def unpack_triplet_plus_time64(data: bytes) -> Tuple[float, float, float, float]:
        """Unpack three float32 values plus one float64 timestamp in milliseconds."""
        return struct.unpack('!fffd', data)
