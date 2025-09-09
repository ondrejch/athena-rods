#!/usr/bin/env python3
"""
Tests for MFRC522 RFID reader module
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock

# Mock hardware dependencies before importing the module
mock_spidev = Mock()
mock_gpiozero = Mock()

sys.modules['spidev'] = mock_spidev
sys.modules['gpiozero'] = mock_gpiozero

# Now we can import the module
from mfrc522.MFRC522 import MFRC522


class TestMFRC522:
    """Test class for MFRC522 RFID reader"""

    @pytest.fixture
    def mock_spi(self):
        """Mock SPI device"""
        mock_device = Mock()
        mock_spidev.SpiDev.return_value = mock_device
        return mock_device

    @pytest.fixture
    def mock_gpio(self):
        """Mock GPIO device"""
        mock_device = Mock()
        mock_gpiozero.DigitalOutputDevice.return_value = mock_device
        return mock_device

    @pytest.fixture
    def mfrc522(self, mock_spi, mock_gpio):
        """Create MFRC522 instance with mocked dependencies"""
        with patch.object(MFRC522, 'mfrc522_init'):
            reader = MFRC522(bus=0, device=0, spd=1000000, pin_rst=22)
        return reader

    def test_init(self, mock_spi, mock_gpio):
        """Test MFRC522 initialization"""
        with patch.object(MFRC522, 'mfrc522_init'):
            reader = MFRC522()
        
        # Verify SPI setup
        mock_spidev.SpiDev.assert_called_once()
        mock_spi.open.assert_called_once_with(0, 0)
        assert mock_spi.max_speed_hz == 1000000
        
        # Verify GPIO setup
        mock_gpiozero.DigitalOutputDevice.assert_called_once_with(22)
        mock_gpio.on.assert_called_once()

    def test_calculate_crc_known_input(self, mfrc522, mock_spi):
        """Test calculate_crc with known inputs and expected outputs"""
        # Setup mock responses for CRC calculation
        mock_spi.xfer2.return_value = [0x00, 0x00]  # Mock write operations
        
        # Mock read operations for CRC result registers
        def mock_read_side_effect(addr_list):
            addr = addr_list[0]
            if addr == ((MFRC522.CRC_RESULT_REG_L << 1) & 0x7E) | 0x80:
                return [0x00, 0x63]  # Low byte of CRC
            elif addr == ((MFRC522.CRC_RESULT_REG_M << 1) & 0x7E) | 0x80:
                return [0x00, 0xA7]  # High byte of CRC
            elif addr == ((MFRC522.DIVIRQ_REG << 1) & 0x7E) | 0x80:
                return [0x00, 0x04]  # Indicate CRC ready
            return [0x00, 0x00]
        
        mock_spi.xfer2.side_effect = mock_read_side_effect
        
        # Test with known input data
        input_data = [0x50, 0x00, 0x57, 0xCD]  # Example RFID command
        result = mfrc522.calculate_crc(input_data)
        
        # Verify the result
        assert isinstance(result, list)
        assert len(result) == 2
        assert result == [0x63, 0xA7]  # Expected CRC values

    def test_calculate_crc_empty_input(self, mfrc522, mock_spi):
        """Test calculate_crc with empty input"""
        # Mock the SPI operations - need more calls since it also reads for the loop
        def mock_side_effect(cmd_list):
            cmd = cmd_list[0] if cmd_list else 0
            # Check if it's a read operation (has 0x80 bit set)
            if cmd & 0x80:
                # Read operations
                addr = (cmd & 0x7E) >> 1
                if addr == mfrc522.DIVIRQ_REG:
                    return [0x00, 0x04]  # CRC ready
                elif addr == mfrc522.CRC_RESULT_REG_L:
                    return [0x00, 0x00]  # Low byte
                elif addr == mfrc522.CRC_RESULT_REG_M:
                    return [0x00, 0x00]  # High byte
            return [0x00, 0x00]  # Write operations
            
        mock_spi.xfer2.side_effect = mock_side_effect
        
        result = mfrc522.calculate_crc([])
        
        # Should return two zero bytes for empty input
        assert result == [0x00, 0x00]

    def test_mfrc522_to_card_success(self, mfrc522, mock_spi):
        """Test mfrc522_to_card with successful response"""
        # Mock successful communication with a function that handles all calls
        def mock_side_effect(cmd_list):
            cmd = cmd_list[0] if cmd_list else 0
            if cmd & 0x80:  # Read operations
                addr = (cmd & 0x7E) >> 1
                if addr == mfrc522.COMMIRQ_REG:
                    return [0x00, 0x30]  # Indicate completion
                elif addr == mfrc522.ERROR_REG:
                    return [0x00, 0x00]  # No error
                elif addr == mfrc522.FIFO_LEVEL_REG:
                    return [0x00, 0x04]  # 4 bytes available
                elif addr == mfrc522.CONTROL_REG:
                    return [0x00, 0x00]  # No last bits
                elif addr == mfrc522.FIFO_DATA_REG:
                    return [0x00, 0x04]  # Sample data byte
            return [0x00, 0x00]  # Write operations
        
        mock_spi.xfer2.side_effect = mock_side_effect
        
        command = MFRC522.PCD_TRANSCEIVE
        send_data = [0x26]  # REQA command
        
        status, back_data, back_len = mfrc522.mfrc522_to_card(command, send_data)
        
        # Verify successful communication
        assert status == MFRC522.MI_OK
        assert isinstance(back_data, list)
        assert back_len > 0

    def test_mfrc522_to_card_timeout(self, mfrc522, mock_spi):
        """Test mfrc522_to_card with timeout (no response)"""
        # Mock timeout scenario - COMMIRQ_REG never indicates completion
        def mock_side_effect(cmd_list):
            cmd = cmd_list[0] if cmd_list else 0
            if cmd & 0x80:  # Read operations
                addr = (cmd & 0x7E) >> 1
                if addr == mfrc522.COMMIRQ_REG:
                    return [0x00, 0x00]  # Never indicate completion (timeout)
                elif addr == mfrc522.ERROR_REG:
                    return [0x00, 0x1B]  # Indicate error to trigger MI_ERR path
            return [0x00, 0x00]  # Write operations
            
        mock_spi.xfer2.side_effect = mock_side_effect
        
        command = MFRC522.PCD_TRANSCEIVE
        send_data = [0x26]
        
        status, back_data, back_len = mfrc522.mfrc522_to_card(command, send_data)
        
        # Should return error status on timeout
        assert status == MFRC522.MI_ERR
        assert back_data == []
        assert back_len == 0

    def test_mfrc522_to_card_error(self, mfrc522, mock_spi):
        """Test mfrc522_to_card with error response"""
        # Mock error scenario
        def mock_side_effect(cmd_list):
            cmd = cmd_list[0] if cmd_list else 0
            if cmd & 0x80:  # Read operations
                addr = (cmd & 0x7E) >> 1
                if addr == mfrc522.COMMIRQ_REG:
                    return [0x00, 0x30]  # Indicate completion
                elif addr == mfrc522.ERROR_REG:
                    return [0x00, 0x01]  # Indicate error (bit in 0x1B mask)
            return [0x00, 0x00]  # Write operations
        
        mock_spi.xfer2.side_effect = mock_side_effect
        
        command = MFRC522.PCD_TRANSCEIVE
        send_data = [0x26]
        
        status, back_data, back_len = mfrc522.mfrc522_to_card(command, send_data)
        
        # Should return error status
        assert status == MFRC522.MI_ERR
        assert back_data == []
        assert back_len == 0

    def test_mfrc522_read(self, mfrc522, mock_spi):
        """Test mfrc522_read method"""
        # Mock successful read operation
        mock_spi.xfer2.return_value = [0x00, 0xAB]  # Mock read response
        
        result = mfrc522.read_mfrc522(0x01)  # Read from address 0x01
        
        # Verify correct SPI command and result
        expected_cmd = [((0x01 << 1) & 0x7E) | 0x80, 0]
        mock_spi.xfer2.assert_called_with(expected_cmd)
        assert result == 0xAB

    def test_mfrc522_write(self, mfrc522, mock_spi):
        """Test mfrc522_write method"""
        # Test write operation
        mfrc522.write_mfrc522(0x01, 0xCD)  # Write 0xCD to address 0x01
        
        # Verify correct SPI command
        expected_cmd = [(0x01 << 1) & 0x7E, 0xCD]
        mock_spi.xfer2.assert_called_with(expected_cmd)

    def test_set_bit_mask(self, mfrc522, mock_spi):
        """Test set_bit_mask method"""
        # Mock read to return current register value
        mock_spi.xfer2.side_effect = [
            [0x00, 0x10],  # Read current value
            [0x00, 0x00],  # Write operation
        ]
        
        mfrc522.set_bit_mask(0x01, 0x08)  # Set bit 3 in register 0x01
        
        # Should read current value and write with bit set
        assert mock_spi.xfer2.call_count == 2

    def test_clear_bit_mask(self, mfrc522, mock_spi):
        """Test clear_bit_mask method"""
        # Mock read to return current register value
        mock_spi.xfer2.side_effect = [
            [0x00, 0x18],  # Read current value (has bit 3 set)
            [0x00, 0x00],  # Write operation
        ]
        
        mfrc522.clear_bit_mask(0x01, 0x08)  # Clear bit 3 in register 0x01
        
        # Should read current value and write with bit cleared
        assert mock_spi.xfer2.call_count == 2

    def test_antenna_on(self, mfrc522, mock_spi):
        """Test antenna_on method"""
        # Mock read to return current TX_CONTROL_REG value without antenna bits
        mock_spi.xfer2.side_effect = [
            [0x00, 0x00],  # Read TX_CONTROL_REG (antenna off)
            [0x00, 0x00],  # Read again for set_bit_mask
            [0x00, 0x00],  # Write operation
        ]
        
        mfrc522.antenna_on()
        
        # Should attempt to set antenna bits
        assert mock_spi.xfer2.call_count >= 2

    def test_antenna_off(self, mfrc522, mock_spi):
        """Test antenna_off method"""
        # Mock operations for clearing antenna bits
        mock_spi.xfer2.side_effect = [
            [0x00, 0x03],  # Read current value (antenna on)
            [0x00, 0x00],  # Write operation
        ]
        
        mfrc522.antenna_off()
        
        # Should clear antenna bits
        assert mock_spi.xfer2.call_count == 2