#!/usr/bin/env python3
"""Tests for socket utility helpers used by ATHENA-rods."""

from unittest.mock import patch

import pytest

from arod_control.socket_utils import SocketManager, StreamingPacket


class TestStreamingPacket:
    """Round-trip tests for binary packet helper methods."""

    def test_triplet_round_trip(self):
        """Test float triplet packing/unpacking is stable."""
        payload = StreamingPacket.pack_float_triplet(1.25, -0.5, 42.0)
        assert len(payload) == StreamingPacket.PACKET_SIZE_TRIPLET
        values = StreamingPacket.unpack_float_triplet(payload)
        assert values == pytest.approx((1.25, -0.5, 42.0))

    def test_quad_round_trip(self):
        """Test float quad packing/unpacking is stable."""
        payload = StreamingPacket.pack_float_quad(1.0, 2.0, 3.0, 4.0)
        assert len(payload) == StreamingPacket.PACKET_SIZE_QUAD
        values = StreamingPacket.unpack_float_quad(payload)
        assert values == pytest.approx((1.0, 2.0, 3.0, 4.0))

    def test_triplet_time64_round_trip(self):
        """Test triplet+time packet format used by telemetry stream."""
        payload = StreamingPacket.pack_triplet_plus_time64(0.25, -0.001, 12.5, 1.713e12)
        assert len(payload) == StreamingPacket.PACKET_SIZE_TIME64
        values = StreamingPacket.unpack_triplet_plus_time64(payload)
        assert values == pytest.approx((0.25, -0.001, 12.5, 1.713e12))


class TestSocketManagerJsonParsing:
    """Behavior tests for line-buffered JSON receiver."""

    def test_receive_json_buffers_partial_message(self):
        """Test partial JSON line is buffered until newline arrives."""
        manager = SocketManager("127.0.0.1", 65433, "ctrl_display", use_ssl=False)

        with patch.object(manager, "receive", side_effect=[(b'{"type":', True), (b'"settings"}\n', True)]):
            first, first_ok = manager.receive_json()
            second, second_ok = manager.receive_json()

        assert first_ok is True
        assert first == {}
        assert second_ok is True
        assert second == {"type": "settings"}

    def test_receive_json_ignores_non_json_ack_lines(self):
        """Test control ack lines do not fail JSON receive loop."""
        manager = SocketManager("127.0.0.1", 65433, "ctrl_display", use_ssl=False)

        with patch.object(manager, "receive", return_value=(b"OK:CONNECTED\n", True)):
            data, ok = manager.receive_json()

        assert ok is True
        assert data == {}
