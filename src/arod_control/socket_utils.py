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
logger.setLevel(logging.INFO)


class SocketManager:
    # ... class init and other methods unchanged ...

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
