#!/usr/bin/env python3
"""
Tests for hwsens hardware sensors module
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock

# Mock hardware dependencies before importing
mock_sensors = Mock()

sys.modules['sensors'] = mock_sensors

from arod_control.hwsens import get_sensors


class TestHwsens:
    """Test class for hardware sensors"""

    def setup_method(self):
        """Reset mocks before each test"""
        mock_sensors.reset_mock()
        # Set up a default empty return for iter_detected_chips
        mock_sensors.iter_detected_chips.return_value = []

    def test_get_sensors_with_fan_and_temp(self):
        """Test get_sensors returns correct data for fan and temperature"""
        # Mock chip and feature objects
        mock_feature_fan = Mock()
        mock_feature_fan.label = 'fan1'
        mock_feature_fan.get_value.return_value = 2500.0  # 2500 RPM
        
        mock_feature_temp = Mock()
        mock_feature_temp.label = 'temp1'
        mock_feature_temp.get_value.return_value = 65.5  # 65.5°C
        
        mock_chip_fan = Mock()
        mock_chip_fan.prefix = b'pwm_fan'
        mock_chip_fan.__iter__ = Mock(return_value=iter([mock_feature_fan]))
        
        mock_chip_cpu = Mock()
        mock_chip_cpu.prefix = b'cpu_thermal'
        mock_chip_cpu.__iter__ = Mock(return_value=iter([mock_feature_temp]))
        
        # Mock the sensors module
        mock_sensors.iter_detected_chips.return_value = [mock_chip_fan, mock_chip_cpu]
        
        # Call the function
        result = get_sensors()
        
        # Verify sensors lifecycle
        mock_sensors.init.assert_called_once()
        mock_sensors.cleanup.assert_called_once()
        
        # Verify results
        assert 'fan1' in result
        assert 'temp1' in result
        assert result['fan1'] == 2500.0
        assert result['temp1'] == 65.5

    def test_get_sensors_case_insensitive_labels(self):
        """Test that label matching is case insensitive"""
        # Test with uppercase labels
        mock_feature_fan = Mock()
        mock_feature_fan.label = 'FAN1'  # Uppercase
        mock_feature_fan.get_value.return_value = 3000.0
        
        mock_feature_temp = Mock()
        mock_feature_temp.label = 'TEMP1'  # Uppercase
        mock_feature_temp.get_value.return_value = 70.0
        
        mock_chip_fan = Mock()
        mock_chip_fan.prefix = b'pwm_fan'
        mock_chip_fan.__iter__ = Mock(return_value=iter([mock_feature_fan]))
        
        mock_chip_cpu = Mock()
        mock_chip_cpu.prefix = b'cpu_thermal'
        mock_chip_cpu.__iter__ = Mock(return_value=iter([mock_feature_temp]))
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip_fan, mock_chip_cpu]
        
        result = get_sensors()
        
        # Should still match due to case insensitive comparison
        assert 'fan1' in result
        assert 'temp1' in result
        assert result['fan1'] == 3000.0
        assert result['temp1'] == 70.0

    def test_get_sensors_mixed_case_labels(self):
        """Test with mixed case labels"""
        mock_feature_fan = Mock()
        mock_feature_fan.label = 'Fan1'  # Mixed case
        mock_feature_fan.get_value.return_value = 1800.0
        
        mock_chip = Mock()
        mock_chip.prefix = b'pwm_fan'
        mock_chip.__iter__ = Mock(return_value=iter([mock_feature_fan]))
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip]
        
        result = get_sensors()
        
        assert 'fan1' in result
        assert result['fan1'] == 1800.0

    def test_get_sensors_no_matching_sensors(self):
        """Test get_sensors returns empty dict when no matching sensors found"""
        # Mock feature with non-matching label
        mock_feature = Mock()
        mock_feature.label = 'voltage1'
        mock_feature.get_value.return_value = 3.3
        
        mock_chip = Mock()
        mock_chip.prefix = b'some_chip'
        mock_chip.__iter__ = Mock(return_value=iter([mock_feature]))
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip]
        
        result = get_sensors()
        
        # Should return empty dict
        assert result == {}
        
        # Verify sensors lifecycle still called
        mock_sensors.init.assert_called_once()
        mock_sensors.cleanup.assert_called_once()

    def test_get_sensors_only_fan(self):
        """Test get_sensors with only fan sensor available"""
        mock_feature_fan = Mock()
        mock_feature_fan.label = 'fan1'
        mock_feature_fan.get_value.return_value = 2200.0
        
        mock_chip = Mock()
        mock_chip.prefix = b'pwm_fan'
        mock_chip.__iter__ = Mock(return_value=iter([mock_feature_fan]))
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip]
        
        result = get_sensors()
        
        assert 'fan1' in result
        assert 'temp1' not in result
        assert result['fan1'] == 2200.0

    def test_get_sensors_only_temp(self):
        """Test get_sensors with only temperature sensor available"""
        mock_feature_temp = Mock()
        mock_feature_temp.label = 'temp1'
        mock_feature_temp.get_value.return_value = 58.3
        
        mock_chip = Mock()
        mock_chip.prefix = b'cpu_thermal'
        mock_chip.__iter__ = Mock(return_value=iter([mock_feature_temp]))
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip]
        
        result = get_sensors()
        
        assert 'temp1' in result
        assert 'fan1' not in result
        assert result['temp1'] == 58.3

    def test_get_sensors_multiple_chips_same_type(self):
        """Test get_sensors with multiple chips but only matching ones are used"""
        # Create multiple features, some matching, some not
        mock_feature_fan = Mock()
        mock_feature_fan.label = 'fan1'
        mock_feature_fan.get_value.return_value = 2800.0
        
        mock_feature_other = Mock()
        mock_feature_other.label = 'fan2'  # Won't match (not 'fan1')
        mock_feature_other.get_value.return_value = 1500.0
        
        mock_feature_temp = Mock()
        mock_feature_temp.label = 'temp1'
        mock_feature_temp.get_value.return_value = 62.0
        
        # First chip with fan1
        mock_chip1 = Mock()
        mock_chip1.prefix = b'pwm_fan'
        mock_chip1.__iter__ = Mock(return_value=iter([mock_feature_fan]))
        
        # Second chip with fan2 (shouldn't match)
        mock_chip2 = Mock()
        mock_chip2.prefix = b'other_fan'
        mock_chip2.__iter__ = Mock(return_value=iter([mock_feature_other]))
        
        # Third chip with CPU temp
        mock_chip3 = Mock()
        mock_chip3.prefix = b'cpu_thermal'
        mock_chip3.__iter__ = Mock(return_value=iter([mock_feature_temp]))
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip1, mock_chip2, mock_chip3]
        
        result = get_sensors()
        
        # Should only have fan1 and temp1
        assert 'fan1' in result
        assert 'temp1' in result
        assert result['fan1'] == 2800.0
        assert result['temp1'] == 62.0

    def test_get_sensors_temp_not_cpu_thermal(self):
        """Test that temp1 is only detected from cpu_thermal chip"""
        mock_feature_temp = Mock()
        mock_feature_temp.label = 'temp1'
        mock_feature_temp.get_value.return_value = 45.0
        
        # Chip that's not cpu_thermal
        mock_chip = Mock()
        mock_chip.prefix = b'other_thermal'
        mock_chip.__iter__ = Mock(return_value=iter([mock_feature_temp]))
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip]
        
        result = get_sensors()
        
        # temp1 should not be in result because chip prefix is not cpu_thermal
        assert 'temp1' not in result
        assert result == {}

    def test_get_sensors_with_print_enabled(self, capsys):
        """Test get_sensors with printing enabled"""
        mock_feature_fan = Mock()
        mock_feature_fan.label = 'fan1'
        mock_feature_fan.get_value.return_value = 2400.0
        
        mock_feature_temp = Mock()
        mock_feature_temp.label = 'temp1'
        mock_feature_temp.get_value.return_value = 67.8
        
        mock_chip_fan = Mock()
        mock_chip_fan.prefix = b'pwm_fan'
        mock_chip_fan.__iter__ = Mock(return_value=iter([mock_feature_fan]))
        
        mock_chip_cpu = Mock()
        mock_chip_cpu.prefix = b'cpu_thermal'
        mock_chip_cpu.__iter__ = Mock(return_value=iter([mock_feature_temp]))
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip_fan, mock_chip_cpu]
        
        # Call with print enabled
        result = get_sensors(do_print=True)
        
        # Verify output was printed
        captured = capsys.readouterr()
        assert 'fan1: 2400 RPM' in captured.out
        assert 'temp1: 68 C' in captured.out  # Rounded to 68
        
        # Verify data is still returned correctly
        assert result['fan1'] == 2400.0
        assert result['temp1'] == 67.8

    def test_get_sensors_with_print_disabled(self, capsys):
        """Test get_sensors with printing disabled (default)"""
        mock_feature_fan = Mock()
        mock_feature_fan.label = 'fan1'
        mock_feature_fan.get_value.return_value = 2100.0
        
        mock_chip = Mock()
        mock_chip.prefix = b'pwm_fan'
        mock_chip.__iter__ = Mock(return_value=iter([mock_feature_fan]))
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip]
        
        # Call with default print setting (False)
        result = get_sensors()
        
        # Verify no output was printed
        captured = capsys.readouterr()
        assert captured.out == ''
        
        # Verify data is still returned correctly
        assert result['fan1'] == 2100.0

    def test_get_sensors_empty_chips(self):
        """Test get_sensors with no chips detected"""
        mock_sensors.iter_detected_chips.return_value = []
        
        result = get_sensors()
        
        assert result == {}
        mock_sensors.init.assert_called_once()
        mock_sensors.cleanup.assert_called_once()

    def test_get_sensors_chip_with_no_features(self):
        """Test get_sensors with chip that has no features"""
        mock_chip = Mock()
        mock_chip.prefix = b'empty_chip'
        mock_chip.__iter__ = Mock(return_value=iter([]))  # No features
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip]
        
        result = get_sensors()
        
        assert result == {}

    def test_get_sensors_feature_value_zero(self):
        """Test get_sensors handles zero values correctly"""
        mock_feature_fan = Mock()
        mock_feature_fan.label = 'fan1'
        mock_feature_fan.get_value.return_value = 0.0  # Fan stopped
        
        mock_chip = Mock()
        mock_chip.prefix = b'pwm_fan'
        mock_chip.__iter__ = Mock(return_value=iter([mock_feature_fan]))
        
        mock_sensors.iter_detected_chips.return_value = [mock_chip]
        
        result = get_sensors()
        
        assert 'fan1' in result
        assert result['fan1'] == 0.0

    def test_sensors_lifecycle_called_correctly(self):
        """Test that sensors.init() and sensors.cleanup() are always called"""
        # Mock an empty chip list
        mock_sensors.iter_detected_chips.return_value = []
        
        get_sensors()
        
        # Verify lifecycle methods called in correct order
        assert mock_sensors.init.call_count == 1
        assert mock_sensors.cleanup.call_count == 1
        
        # Verify init was called before cleanup
        handle = mock_sensors.mock_calls
        init_call_index = next(i for i, call in enumerate(handle) if 'init' in str(call))
        cleanup_call_index = next(i for i, call in enumerate(handle) if 'cleanup' in str(call))
        assert init_call_index < cleanup_call_index