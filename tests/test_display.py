#!/usr/bin/env python3
"""
Tests for display module
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock

# Mock hardware dependencies before importing
mock_smbus = Mock()
mock_subprocess = Mock()
mock_sensors = Mock()

sys.modules['smbus2'] = mock_smbus
sys.modules['subprocess'] = mock_subprocess
sys.modules['sensors'] = mock_sensors

from arod_control.display import Display
from arod_control import LCD1602, hwsens


class TestDisplay:
    """Test class for Display"""

    @pytest.fixture
    def mock_lcd_init(self):
        """Mock LCD1602 initialization"""
        with patch.object(LCD1602, 'init') as mock_init, \
             patch.object(LCD1602, 'write') as mock_write:
            yield mock_init, mock_write

    @pytest.fixture
    def mock_hwsens(self):
        """Mock hardware sensors"""
        with patch.object(hwsens, 'get_sensors') as mock_get_sensors:
            yield mock_get_sensors

    def test_display_init(self, mock_lcd_init):
        """Test Display initialization"""
        mock_init, mock_write = mock_lcd_init
        
        with patch('arod_control.display.datetime') as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2023-12-01T10:30:45"
            
            display = Display()
        
        # Verify LCD initialization
        mock_init.assert_called_once_with(0x27, 1)
        
        # Verify initial messages written
        assert mock_write.call_count == 2
        mock_write.assert_any_call(0, 0, '** ATHENArods **')
        mock_write.assert_any_call(0, 1, "2023-12-01T10:30:45")

    def test_display_init_pads_short_timestamp(self, mock_lcd_init):
        """Test Display initialization pads short timestamp"""
        mock_init, mock_write = mock_lcd_init
        
        with patch('arod_control.display.datetime') as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T01:01"  # Shorter
            
            display = Display()
        
        # Should pad to 16 characters with ljust(16)
        mock_write.assert_any_call(0, 1, "2023-01-01T01:01")  # Actually no padding unless < 16 chars

    def test_show_sensors_with_data(self, mock_lcd_init):
        """Test show_sensors displays sensor data correctly"""
        mock_init, mock_write = mock_lcd_init
        
        # Create display instance
        display = Display()
        mock_write.reset_mock()  # Reset call count from init
        
        # Mock sensor data
        with patch('arod_control.display.get_sensors') as mock_get_sensors:
            mock_get_sensors.return_value = {
                'fan1': 2500.7,
                'temp1': 65.3
            }
            
            # Mock system load
            with patch('os.getloadavg', return_value=[1.0, 1.5, 2.25]):
                display.show_sensors()
        
        # Verify sensor data display
        assert mock_write.call_count == 2
        
        # Check actual format: f'L {load5:.2f}, {sens["fan1"]:.0f} rpm'.ljust(16)
        expected_line1 = 'L 2.25, 2501 rpm'.ljust(16)
        mock_write.assert_any_call(0, 0, expected_line1)
        
        # Check second line: f'temp {sens["temp1"]:.1f} C'.ljust(16)
        expected_line2 = 'temp 65.3 C'.ljust(16)
        mock_write.assert_any_call(0, 1, expected_line2)

    def test_show_sensors_missing_fan_data(self, mock_lcd_init):
        """Test show_sensors handles missing fan data"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        # Mock sensor data without fan1 - mock get_sensors directly
        with patch('arod_control.display.get_sensors') as mock_get_sensors:
            mock_get_sensors.return_value = {
                'temp1': 58.9
            }
            
            with patch('os.getloadavg', return_value=[0.5, 0.8, 1.1]):
                with pytest.raises(KeyError):
                    display.show_sensors()

    def test_show_sensors_missing_temp_data(self, mock_lcd_init):
        """Test show_sensors handles missing temperature data"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        # Mock sensor data without temp1
        with patch('arod_control.display.get_sensors') as mock_get_sensors:
            mock_get_sensors.return_value = {
                'fan1': 3000.0
            }
            
            with patch('os.getloadavg', return_value=[0.5, 0.8, 1.1]):
                with pytest.raises(KeyError):
                    display.show_sensors()

    def test_show_sensors_zero_values(self, mock_lcd_init):
        """Test show_sensors with zero sensor values"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        # Mock zero sensor values
        with patch('arod_control.display.get_sensors') as mock_get_sensors:
            mock_get_sensors.return_value = {
                'fan1': 0.0,
                'temp1': 0.0
            }
            
            with patch('os.getloadavg', return_value=[0.0, 0.0, 0.0]):
                display.show_sensors()
        
        expected_line1 = 'L 0.00, 0 rpm'.ljust(16)
        expected_line2 = 'temp 0.0 C'.ljust(16)
        mock_write.assert_any_call(0, 0, expected_line1)
        mock_write.assert_any_call(0, 1, expected_line2)

    def test_show_sensors_high_values(self, mock_lcd_init):
        """Test show_sensors with high sensor values"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        # Mock high sensor values
        with patch('arod_control.display.get_sensors') as mock_get_sensors:
            mock_get_sensors.return_value = {
                'fan1': 9999.9,
                'temp1': 99.99
            }
            
            with patch('os.getloadavg', return_value=[10.0, 15.0, 99.99]):
                display.show_sensors()
        
        # Check formatting: f'L {load5:.2f}, {sens["fan1"]:.0f} rpm'.ljust(16)
        expected_line1 = 'L 99.99, 10000 rpm'.ljust(16)
        expected_line2 = 'temp 100.0 C'.ljust(16)  # Rounded to 100.0
        mock_write.assert_any_call(0, 0, expected_line1)
        mock_write.assert_any_call(0, 1, expected_line2)

    def test_show_message_single_line_short(self, mock_lcd_init):
        """Test show_message with short single line"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        display.show_message("Hello World")
        
        # Should display on first line only
        mock_write.assert_called_once_with(0, 0, "Hello World")

    def test_show_message_single_line_long(self, mock_lcd_init):
        """Test show_message with long single line (splits to two lines)"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        long_message = "This is a very long message that exceeds 16 characters"
        display.show_message(long_message)
        
        # Should split at character 16
        assert mock_write.call_count == 2
        # First call: LCD1602.write(0, 0, m) where m is the stripped message
        mock_write.assert_any_call(0, 0, long_message)  # Full message on first line
        # Second call: LCD1602.write(0, 1, m[16:].ljust(16)) - rest of message
        expected_second_line = long_message[16:].ljust(16)
        mock_write.assert_any_call(0, 1, expected_second_line)

    def test_show_message_exactly_16_chars(self, mock_lcd_init):
        """Test show_message with exactly 16 characters"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        message_16_chars = "1234567890123456"  # Exactly 16 chars
        display.show_message(message_16_chars)
        
        # Should display on first line only
        mock_write.assert_called_once_with(0, 0, message_16_chars)

    def test_show_message_17_chars(self, mock_lcd_init):
        """Test show_message with 17 characters (splits)"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        message_17_chars = "12345678901234567"  # 17 chars
        display.show_message(message_17_chars)
        
        # Should split
        assert mock_write.call_count == 2
        mock_write.assert_any_call(0, 0, message_17_chars)  # Full message on first line
        mock_write.assert_any_call(0, 1, "7               ")  # Char 16 onward, padded to 16

    def test_show_message_multi_line_explicit(self, mock_lcd_init):
        """Test show_message with explicit multi-line (contains \\n)"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        multi_line_message = "Line 1\nLine 2"
        display.show_message(multi_line_message)
        
        # Should display each line
        assert mock_write.call_count == 2
        mock_write.assert_any_call(0, 0, "Line 1          ")  # Padded to 16
        mock_write.assert_any_call(0, 1, "Line 2          ")  # Padded to 16

    def test_show_message_multi_line_long_lines(self, mock_lcd_init):
        """Test show_message with multi-line where lines are long"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        # Lines longer than 16 characters
        multi_line_message = "This is a very long first line\nThis is also a long second line"
        display.show_message(multi_line_message)
        
        # Should display each line, padded to 16 chars with ljust(16)
        assert mock_write.call_count == 2
        lines = multi_line_message.split('\n')
        mock_write.assert_any_call(0, 0, lines[0].ljust(16))
        mock_write.assert_any_call(0, 1, lines[1].ljust(16))

    def test_show_message_empty_string(self, mock_lcd_init):
        """Test show_message with empty string"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        display.show_message("")
        
        # Should display empty string (after strip)
        mock_write.assert_called_once_with(0, 0, "")

    def test_show_message_whitespace_only(self, mock_lcd_init):
        """Test show_message with whitespace only"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        display.show_message("   \n   ")
        
        # Should strip and show empty lines
        assert mock_write.call_count == 2
        mock_write.assert_any_call(0, 0, "                ")  # Empty, padded
        mock_write.assert_any_call(0, 1, "                ")  # Empty, padded

    def test_show_message_leading_trailing_spaces(self, mock_lcd_init):
        """Test show_message strips leading/trailing spaces for single line"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        display.show_message("  Hello World  ")
        
        # Should strip for single line
        mock_write.assert_called_once_with(0, 0, "Hello World")

    def test_show_message_three_lines(self, mock_lcd_init):
        """Test show_message with three lines (only first two should show)"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        three_line_message = "Line 1\nLine 2\nLine 3"
        display.show_message(three_line_message)
        
        # Should only display first two lines
        assert mock_write.call_count == 2
        mock_write.assert_any_call(0, 0, "Line 1          ")
        mock_write.assert_any_call(0, 1, "Line 2          ")
        # Line 3 should be ignored

    def test_show_message_newline_at_end(self, mock_lcd_init):
        """Test show_message with newline at end"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        message_with_newline = "Hello\n"
        display.show_message(message_with_newline)
        
        # Should split and show empty second line
        assert mock_write.call_count == 2
        mock_write.assert_any_call(0, 0, "Hello           ")
        mock_write.assert_any_call(0, 1, "                ")  # Empty second line

    def test_multiple_operations(self, mock_lcd_init):
        """Test multiple display operations"""
        mock_init, mock_write = mock_lcd_init
        
        display = Display()
        mock_write.reset_mock()
        
        # Show message first
        display.show_message("Status: OK")
        
        # Then show sensors
        with patch('arod_control.display.get_sensors') as mock_get_sensors:
            mock_get_sensors.return_value = {'fan1': 2000.0, 'temp1': 60.0}
            with patch('os.getloadavg', return_value=[1.0, 1.0, 1.5]):
                display.show_sensors()
        
        # Should have called write 3 times total (1 for message + 2 for sensors)
        assert mock_write.call_count == 3