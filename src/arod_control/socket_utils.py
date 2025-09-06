#!/usr/bin/env python3
"""
Socket communication utilities for ATHENA-rods
"""

import socket
import time
import logging
import threading
import json
import struct
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger('SocketUtils')
logger.setLevel(logging.INFO)  # Ensure we're capturing appropriate log level


class SocketManager:
    """Manager for socket connections with reconnection capabilities"""

    def __init__(self, host: str, port: int, handshake: str):
        """Initialize socket manager with connection parameters

        Args:
            host (str): Host to connect to
            port (int): Port number
            handshake (str): Handshake string to send on connection
        """
        self.host = host
        self.port = port
        self.handshake = handshake
        self.socket = None
        self.connected = False
        self.lock = threading.Lock()
        self.buffer = b""
        self.reconnect_delay = 1  # Starting delay (seconds)
        self.max_delay = 30  # Maximum delay (seconds)
        self._shutdown_requested = False

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
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(timeout)

                # Connect and send handshake
                logger.info(f"Attempting to connect to {self.host}:{self.port} ({self.handshake})")
                self.socket.connect((self.host, self.port))

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
        """Close the socket connection safely"""
        with self.lock:
            self._shutdown_requested = True
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
                    self.socket.settimeout(min(0.5, end_time - time.time()))

            chunk, success = self.receive(remaining)

            if self._shutdown_requested:
                return b"", False

            if not success:
                # Only return failure if it's an actual error, not a timeout
                if not chunk:
                    return b"", False

            if chunk:
                result += chunk
                if len(result) == size:
                    return result, True

            # Small delay to avoid tight loop, check for shutdown
            time.sleep(0.01)

        return result, len(result) == size

    def receive_json(self) -> Tuple[Dict[str, Any], bool]:
        """Receive and parse JSON data"""
        if self._shutdown_requested:
            return {}, False

        with self.lock:
            try:
                if self.socket:
                    self.socket.settimeout(0.5)

                data, success = self.receive(1024)
                if not success and not data:
                    return {}, False

                if data:
                    self.buffer += data

                # Need a full line
                if b'\n' not in self.buffer:
                    return {}, True

                line, self.buffer = self.buffer.split(b'\n', 1)
                if not line:
                    return {}, True

                # Try JSON first
                try:
                    result = json.loads(line.decode('utf-8'))
                    return result, True
                except json.JSONDecodeError:
                    # Swallow common non-JSON control acks silently
                    try:
                        text = line.decode('utf-8', errors='ignore').strip()
                        if text.startswith('OK:') or text.startswith('REJECT:'):
                            return {}, True
                    except Exception:
                        pass
                    # Not JSON, not a known ack: ignore silently
                    return {}, True

            except Exception as e:
                logger.error(f"Error receiving JSON data: {e}")
                self.connected = False
                return {}, False


class StreamingPacket:
    # unchanged
    @staticmethod
    def pack_float_triplet(val1: float, val2: float, val3: float) -> bytes:
        return struct.pack('!fff', val1, val2, val3)

    @staticmethod
    def unpack_float_triplet(data: bytes) -> Tuple[float, float, float]:
        return struct.unpack('!fff', data)
