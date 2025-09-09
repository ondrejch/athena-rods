#!/usr/bin/env python3
"""
Tests for LCD1602 display module
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock

# Mock hardware dependencies before importing
mock_smbus = Mock()
mock_subprocess = Mock()

sys.modules['smbus2'] = mock_smbus
sys.modules['subprocess'] = mock_subprocess

from arod_control import LCD1602


class TestLCD1602:
    """Test class for LCD1602 display"""

    @pytest.fixture
    def mock_bus(self):
        """Mock SMBus instance"""
        mock_bus_instance = Mock()
        mock_smbus.SMBus.return_value = mock_bus_instance
        return mock_bus_instance

    @pytest.fixture
    def mock_i2c_scan_success(self):
        """Mock successful I2C scan"""
        with patch('arod_control.LCD1602.i2c_scan') as mock_scan:
            mock_scan.return_value = ['27', '3f', '48']  # Common I2C addresses
            yield mock_scan

    @pytest.fixture
    def mock_i2c_scan_no_lcd(self):
        """Mock I2C scan with no LCD found"""
        with patch('arod_control.LCD1602.i2c_scan') as mock_scan:
            mock_scan.return_value = ['48', '50']  # Other devices, no LCD
            yield mock_scan

    def setup_method(self):
        """Setup for each test"""
        # Reset global variables
        if hasattr(LCD1602, 'LCD_ADDR'):
            delattr(LCD1602, 'LCD_ADDR')
        if hasattr(LCD1602, 'BLEN'):
            delattr(LCD1602, 'BLEN')

    def test_write_word_with_backlight_on(self, mock_bus):
        """Test write_word function with backlight enabled"""
        # Set up global state
        LCD1602.BLEN = 1
        LCD1602.LCD_ADDR = 0x27
        
        # Mock the BUS global variable
        LCD1602.BUS = mock_bus
        
        # Test data
        test_addr = 0x27
        test_data = 0x50
        
        LCD1602.write_word(test_addr, test_data)
        
        # With BLEN=1, data should have 0x08 bit set
        expected_data = test_data | 0x08
        mock_bus.write_byte.assert_called_once_with(test_addr, expected_data)

    def test_write_word_with_backlight_off(self, mock_bus):
        """Test write_word function with backlight disabled"""
        # Set up global state
        LCD1602.BLEN = 0
        LCD1602.LCD_ADDR = 0x27
        LCD1602.BUS = mock_bus
        
        # Test data
        test_addr = 0x27
        test_data = 0x58  # Has 0x08 bit set initially
        
        LCD1602.write_word(test_addr, test_data)
        
        # With BLEN=0, 0x08 bit should be cleared
        expected_data = test_data & 0xF7  # Clear bit 3 (0x08)
        mock_bus.write_byte.assert_called_once_with(test_addr, expected_data)

    def test_send_command(self, mock_bus):
        """Test send_command function sends correct sequence"""
        LCD1602.LCD_ADDR = 0x27
        LCD1602.BLEN = 1
        LCD1602.BUS = mock_bus
        
        command = 0x38  # Example command
        
        with patch('time.sleep'):  # Mock sleep to speed up tests
            LCD1602.send_command(command)
        
        # Should call write_byte 4 times (high nibble enable/disable, low nibble enable/disable)
        assert mock_bus.write_byte.call_count == 4
        
        # Verify the sequence of calls
        calls = mock_bus.write_byte.call_args_list
        
        # First call: high nibble with EN=1, RS=0, RW=0, backlight=1
        assert calls[0][0] == (0x27, (0x38 & 0xF0) | 0x04 | 0x08)  # 0x3C
        
        # Second call: high nibble with EN=0
        assert calls[1][0] == (0x27, (0x38 & 0xF0) | 0x08)  # 0x38
        
        # Third call: low nibble with EN=1
        assert calls[2][0] == (0x27, ((0x38 & 0x0F) << 4) | 0x04 | 0x08)  # 0x8C
        
        # Fourth call: low nibble with EN=0
        assert calls[3][0] == (0x27, ((0x38 & 0x0F) << 4) | 0x08)  # 0x88

    def test_send_data(self, mock_bus):
        """Test send_data function sends correct sequence"""
        LCD1602.LCD_ADDR = 0x27
        LCD1602.BLEN = 1
        LCD1602.BUS = mock_bus
        
        data = 0x41  # ASCII 'A'
        
        with patch('time.sleep'):
            LCD1602.send_data(data)
        
        # Should call write_byte 4 times
        assert mock_bus.write_byte.call_count == 4
        
        calls = mock_bus.write_byte.call_args_list
        
        # First call: high nibble with EN=1, RS=1, RW=0, backlight=1
        assert calls[0][0] == (0x27, (0x41 & 0xF0) | 0x05 | 0x08)  # 0x4D
        
        # Second call: high nibble with EN=0, RS=1
        assert calls[1][0] == (0x27, (0x41 & 0xF0) | 0x01 | 0x08)  # 0x49
        
        # Third call: low nibble with EN=1, RS=1
        assert calls[2][0] == (0x27, ((0x41 & 0x0F) << 4) | 0x05 | 0x08)  # 0x1D
        
        # Fourth call: low nibble with EN=0, RS=1
        assert calls[3][0] == (0x27, ((0x41 & 0x0F) << 4) | 0x01 | 0x08)  # 0x19

    def test_init_auto_detect_0x27(self, mock_bus, mock_i2c_scan_success):
        """Test init function auto-detects 0x27 address"""
        LCD1602.BUS = mock_bus
        
        with patch('time.sleep'):
            result = LCD1602.init()
        
        assert result is True
        assert LCD1602.LCD_ADDR == 0x27
        assert LCD1602.BLEN == 1  # Default backlight on
        
        # Should call initialization sequence
        assert mock_bus.write_byte.call_count > 10  # Multiple initialization commands

    def test_init_auto_detect_0x3f(self, mock_bus):
        """Test init function auto-detects 0x3f when 0x27 not available"""
        LCD1602.BUS = mock_bus
        
        with patch('arod_control.LCD1602.i2c_scan') as mock_scan:
            mock_scan.return_value = ['3f', '48']  # Only 0x3f available
            
            with patch('time.sleep'):
                result = LCD1602.init()
        
        assert result is True
        assert LCD1602.LCD_ADDR == 0x3f

    def test_init_no_lcd_found(self, mock_bus, mock_i2c_scan_no_lcd):
        """Test init function raises error when no LCD found"""
        LCD1602.BUS = mock_bus
        
        with pytest.raises(IOError, match="I2C address 0x27 or 0x3f no found"):
            LCD1602.init()

    def test_init_specific_address(self, mock_bus):
        """Test init function with specific address"""
        LCD1602.BUS = mock_bus
        
        with patch('arod_control.LCD1602.i2c_scan') as mock_scan:
            mock_scan.return_value = ['27', '3f']
            
            with patch('time.sleep'):
                result = LCD1602.init(addr=0x3f, bl=0)
        
        assert result is True
        assert LCD1602.LCD_ADDR == 0x3f
        assert LCD1602.BLEN == 0  # Backlight off

    def test_init_invalid_address(self, mock_bus):
        """Test init function with invalid address"""
        LCD1602.BUS = mock_bus
        
        with patch('arod_control.LCD1602.i2c_scan') as mock_scan:
            mock_scan.return_value = ['27', '3f']
            
            with pytest.raises(IOError, match="I2C address 0x50 or 0x3f no found"):
                LCD1602.init(addr=0x50)

    def test_init_exception_handling(self, mock_bus, mock_i2c_scan_success):
        """Test init function handles exceptions gracefully"""
        LCD1602.BUS = mock_bus
        
        # Make write_byte raise an exception
        mock_bus.write_byte.side_effect = Exception("I2C error")
        
        result = LCD1602.init()
        
        assert result is False

    def test_clear(self, mock_bus):
        """Test clear function sends correct command"""
        LCD1602.LCD_ADDR = 0x27
        LCD1602.BLEN = 1
        LCD1602.BUS = mock_bus
        
        with patch('time.sleep'):
            LCD1602.clear()
        
        # Should send clear screen command (0x01)
        # This will result in 4 write_byte calls due to send_command implementation
        assert mock_bus.write_byte.call_count == 4

    def test_write_simple_string(self, mock_bus):
        """Test write function with simple coordinates and string"""
        LCD1602.LCD_ADDR = 0x27
        LCD1602.BLEN = 1
        LCD1602.BUS = mock_bus
        
        with patch('time.sleep'):
            LCD1602.write(0, 0, "Hi")
        
        # Should send position command + data for each character
        # Position command: 4 calls, 'H': 4 calls, 'i': 4 calls = 12 total
        assert mock_bus.write_byte.call_count == 12

    def test_write_coordinate_bounds(self, mock_bus):
        """Test write function respects coordinate boundaries"""
        LCD1602.LCD_ADDR = 0x27
        LCD1602.BLEN = 1
        LCD1602.BUS = mock_bus
        
        with patch('time.sleep'):
            # Test with out-of-bounds coordinates
            LCD1602.write(-5, -1, "A")  # Should be clamped to (0, 0)
        
        calls = mock_bus.write_byte.call_args_list
        
        # First command should be position for (0,0) = 0x80
        # High nibble: 0x80 & 0xF0 = 0x80, plus control bits
        expected_pos_high = 0x80 | 0x04 | 0x08  # 0x8C
        assert calls[0][0] == (0x27, expected_pos_high)

    def test_write_second_line(self, mock_bus):
        """Test write function positions correctly on second line"""
        LCD1602.LCD_ADDR = 0x27
        LCD1602.BLEN = 1
        LCD1602.BUS = mock_bus
        
        with patch('time.sleep'):
            LCD1602.write(5, 1, "A")
        
        calls = mock_bus.write_byte.call_args_list
        
        # Position for (5, 1) should be 0x80 + 0x40*1 + 5 = 0xC5
        # High nibble: 0xC5 & 0xF0 = 0xC0, plus control bits
        expected_pos_high = 0xC0 | 0x04 | 0x08  # 0xCC
        assert calls[0][0] == (0x27, expected_pos_high)

    def test_write_coordinate_clamping(self, mock_bus):
        """Test write function clamps coordinates to valid ranges"""
        LCD1602.LCD_ADDR = 0x27
        LCD1602.BLEN = 1
        LCD1602.BUS = mock_bus
        
        with patch('time.sleep'):
            # Test coordinates beyond limits
            LCD1602.write(20, 5, "A")  # Should be clamped to (15, 1)
        
        calls = mock_bus.write_byte.call_args_list
        
        # Position for (15, 1) should be 0x80 + 0x40*1 + 15 = 0xCF
        # High nibble: 0xCF & 0xF0 = 0xC0, plus control bits
        expected_pos_high = 0xC0 | 0x04 | 0x08  # 0xCC
        assert calls[0][0] == (0x27, expected_pos_high)

    def test_write_empty_string(self, mock_bus):
        """Test write function with empty string"""
        LCD1602.LCD_ADDR = 0x27
        LCD1602.BLEN = 1
        LCD1602.BUS = mock_bus
        
        with patch('time.sleep'):
            LCD1602.write(0, 0, "")
        
        # Should only send position command (4 calls), no character data
        assert mock_bus.write_byte.call_count == 4

    def test_openlight(self, mock_bus):
        """Test openlight function"""
        LCD1602.BUS = mock_bus
        
        LCD1602.openlight()
        
        # Should write backlight command and close bus
        mock_bus.write_byte.assert_called_once_with(0x27, 0x08)
        mock_bus.close.assert_called_once()

    @patch('arod_control.LCD1602.subprocess')
    def test_i2c_scan(self, mock_subprocess_module):
        """Test i2c_scan function parses output correctly"""
        # Mock subprocess output
        mock_subprocess_module.check_output.return_value = b"     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f\n00:          -- -- -- -- -- -- -- -- -- -- -- -- -- \n10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- \n20: -- -- -- -- -- -- -- 27 -- -- -- -- -- -- -- -- \n30: -- -- -- -- -- -- -- -- -- -- -- -- 3c -- -- 3f \n"
        
        result = LCD1602.i2c_scan()
        
        # Should extract addresses, removing '--' entries
        assert '27' in result
        assert '3c' in result  
        assert '3f' in result
        assert isinstance(result, list)