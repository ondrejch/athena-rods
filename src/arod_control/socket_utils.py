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
from typing import Tuple, Optional, Dict, Any, Callable

logger = logging.getLogger('SocketUtils')


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

    def connect(self, timeout: float = 10.0) -> bool:
        """Connect to the server with timeout

        Args:
            timeout (float): Socket timeout in seconds

        Returns:
            bool: True if connected successfully, False otherwise
        """
        with self.lock:
            try:
                if self.socket:
                    self.close()

                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(timeout)
                self.socket.connect((self.host, self.port))
                self.socket.sendall(self.handshake.encode('utf-8') + b'\n')
                self.connected = True
                self.reconnect_delay = 1  # Reset delay on successful connection
                logger.info(f"Connected to {self.host}:{self.port} ({self.handshake})")
                return True
            except Exception as e:
                logger.error(f"Connection failed to {self.host}:{self.port}: {e}")
                self.connected = False
                return False

    def close(self):
        """Close the socket connection safely"""
        with self.lock:
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

    def connect_with_backoff(self, max_attempts: Optional[int] = None) -> bool:
        """Connect with exponential backoff retry logic

        Args:
            max_attempts (Optional[int]): Maximum number of attempts or None for unlimited

        Returns:
            bool: True if connected successfully, False otherwise
        """
        attempts = 0
        current_delay = self.reconnect_delay

        while max_attempts is None or attempts < max_attempts:
            if self.connect():
                return True

            attempts += 1
            logger.info(f"Retrying connection in {current_delay}s (attempt {attempts})")
            time.sleep(current_delay)
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
        with self.lock:
            if not self.connected:
                if not self.connect_with_backoff():
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
        with self.lock:
            if not self.connected:
                if not self.connect_with_backoff():
                    return b"", False

            try:
                data = self.socket.recv(size)
                if not data:
                    logger.info("Connection closed by peer")
                    self.connected = False
                    return b"", False
                return data, True
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
        result = b""
        end_time = time.time() + timeout

        while len(result) < size and time.time() < end_time:
            with self.lock:
                if not self.connected:
                    if not self.connect_with_backoff(max_attempts=1):
                        return b"", False

            chunk, success = self.receive(size - len(result))
            if not success:
                return b"", False

            result += chunk

        return result, len(result) == size

    def receive_json(self) -> Tuple[Dict[str, Any], bool]:
        """Receive and parse JSON data

        Returns:
            Tuple[Dict[str, Any], bool]: (data, success) where success is True if received successfully
        """
        with self.lock:
            try:
                data, success = self.receive(1024)
                if not success:
                    return {}, False

                self.buffer += data
                if b'\n' not in self.buffer:
                    return {}, False

                line, self.buffer = self.buffer.split(b'\n', 1)
                result = json.loads(line.decode('utf-8'))
                return result, True
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
                return {}, False
            except Exception as e:
                logger.error(f"Error receiving JSON data: {e}")
                self.connected = False
                return {}, False


class StreamingPacket:
    """Helper class for streaming binary packets of fixed size"""

    @staticmethod
    def pack_float_triplet(val1: float, val2: float, val3: float) -> bytes:
        """Pack three float values into a binary packet

        Args:
            val1 (float): First float value
            val2 (float): Second float value
            val3 (float): Third float value

        Returns:
            bytes: Binary packet
        """
        return struct.pack('!fff', val1, val2, val3)

    @staticmethod
    def unpack_float_triplet(data: bytes) -> Tuple[float, float, float]:
        """Unpack binary packet into three float values

        Args:
            data (bytes): Binary packet

        Returns:
            Tuple[float, float, float]: Unpacked values
        """
        return struct.unpack('!fff', data)
