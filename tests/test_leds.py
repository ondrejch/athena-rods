#!/usr/bin/env python3
"""
Tests for LEDs control module
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock

# Mock hardware dependencies before importing
mock_gpiozero = Mock()

sys.modules['gpiozero'] = mock_gpiozero

from arod_control.leds import LEDs


class TestLEDs:
    """Test class for LEDs controller"""

    @pytest.fixture
    def mock_led_instances(self):
        """Mock LED instances"""
        mock_led1 = Mock()
        mock_led2 = Mock()
        mock_led3 = Mock()
        
        mock_gpiozero.LED.side_effect = [mock_led1, mock_led2, mock_led3]
        
        return [mock_led1, mock_led2, mock_led3]

    @pytest.fixture
    def leds_controller(self, mock_led_instances):
        """Create LEDs controller instance with mocked LED objects"""
        controller = LEDs()
        return controller, mock_led_instances

    def test_init_creates_correct_leds(self, mock_led_instances):
        """Test LEDs initialization creates correct LED objects with proper GPIO pins"""
        controller = LEDs()
        
        # Verify LED objects are created with correct GPIO pins
        assert mock_gpiozero.LED.call_count == 3
        mock_gpiozero.LED.assert_any_call(17)
        mock_gpiozero.LED.assert_any_call(18)
        mock_gpiozero.LED.assert_any_call(27)
        
        # Verify controller state
        assert len(controller.leds) == 3
        assert len(controller.state) == 3
        assert controller.state == [False, False, False]
        
        # Verify all LEDs are turned off during initialization
        for mock_led in mock_led_instances:
            mock_led.off.assert_called()

    def test_turn_on_specific_led(self, leds_controller):
        """Test turning on a specific LED by index"""
        controller, mock_leds = leds_controller
        
        # Turn on LED at index 1
        controller.turn_on(1)
        
        # Verify only LED 1 is turned on
        mock_leds[0].on.assert_not_called()
        mock_leds[1].on.assert_called_once()
        mock_leds[2].on.assert_not_called()
        
        # Verify state is updated
        assert controller.state[1] is True
        assert controller.state[0] is False
        assert controller.state[2] is False

    def test_turn_on_all_leds(self, leds_controller):
        """Test turning on all LEDs when no index specified"""
        controller, mock_leds = leds_controller
        
        # Turn on all LEDs
        controller.turn_on()
        
        # Verify all LEDs are turned on
        for mock_led in mock_leds:
            mock_led.on.assert_called()

    def test_turn_on_negative_index(self, leds_controller):
        """Test turning on all LEDs with negative index"""
        controller, mock_leds = leds_controller
        
        # Turn on all LEDs with negative index
        controller.turn_on(-1)
        
        # Verify all LEDs are turned on
        for mock_led in mock_leds:
            mock_led.on.assert_called()

    def test_turn_off_specific_led(self, leds_controller):
        """Test turning off a specific LED by index"""
        controller, mock_leds = leds_controller
        
        # First turn on LED 0 to have something to turn off
        controller.state[0] = True
        
        # Turn off LED at index 0
        controller.turn_off(0)
        
        # Verify only LED 0 is turned off (beyond initialization)
        mock_leds[0].off.assert_called()
        
        # Verify state is updated
        assert controller.state[0] is False

    def test_turn_off_all_leds(self, leds_controller):
        """Test turning off all LEDs when no index specified"""
        controller, mock_leds = leds_controller
        
        # Reset mock call counts from initialization
        for mock_led in mock_leds:
            mock_led.reset_mock()
        
        # Turn off all LEDs
        controller.turn_off()
        
        # Verify all LEDs are turned off
        for mock_led in mock_leds:
            mock_led.off.assert_called_once()

    def test_turn_off_negative_index(self, leds_controller):
        """Test turning off all LEDs with negative index"""
        controller, mock_leds = leds_controller
        
        # Reset mock call counts from initialization
        for mock_led in mock_leds:
            mock_led.reset_mock()
        
        # Turn off all LEDs with negative index
        controller.turn_off(-1)
        
        # Verify all LEDs are turned off
        for mock_led in mock_leds:
            mock_led.off.assert_called_once()

    def test_turn_on_invalid_index_high(self, leds_controller):
        """Test that turning on LED with index too high raises assertion"""
        controller, mock_leds = leds_controller
        
        # Should raise AssertionError for index >= len(leds)
        with pytest.raises(AssertionError):
            controller.turn_on(3)  # Only indices 0, 1, 2 are valid

    def test_turn_on_invalid_index_very_high(self, leds_controller):
        """Test that turning on LED with very high index raises assertion"""
        controller, mock_leds = leds_controller
        
        with pytest.raises(AssertionError):
            controller.turn_on(100)

    def test_turn_off_invalid_index_high(self, leds_controller):
        """Test that turning off LED with index too high raises assertion"""
        controller, mock_leds = leds_controller
        
        with pytest.raises(AssertionError):
            controller.turn_off(3)

    def test_turn_off_invalid_index_very_high(self, leds_controller):
        """Test that turning off LED with very high index raises assertion"""
        controller, mock_leds = leds_controller
        
        with pytest.raises(AssertionError):
            controller.turn_off(100)

    def test_state_tracking_turn_on(self, leds_controller):
        """Test that state is properly tracked when turning LEDs on"""
        controller, mock_leds = leds_controller
        
        # Initial state should be all False
        assert all(not state for state in controller.state)
        
        # Turn on each LED individually and check state
        for i in range(len(controller.leds)):
            controller.turn_on(i)
            assert controller.state[i] is True
            # Other LEDs should still be False (if they haven't been turned on yet)
            for j in range(i):
                assert controller.state[j] is True  # Already turned on
            for j in range(i + 1, len(controller.state)):
                assert controller.state[j] is False  # Not turned on yet

    def test_state_tracking_turn_off(self, leds_controller):
        """Test that state is properly tracked when turning LEDs off"""
        controller, mock_leds = leds_controller
        
        # First turn on all LEDs
        controller.turn_on()
        # Note: turn_on() without index doesn't update state array, only calls on() on LEDs
        # So we need to manually set state for this test
        controller.state = [True, True, True]
        
        # Turn off each LED individually and check state
        for i in range(len(controller.leds)):
            controller.turn_off(i)
            assert controller.state[i] is False
            # Other LEDs should still be True (if they haven't been turned off yet)
            for j in range(i):
                assert controller.state[j] is False  # Already turned off
            for j in range(i + 1, len(controller.state)):
                assert controller.state[j] is True  # Still on

    def test_multiple_operations(self, leds_controller):
        """Test multiple on/off operations work correctly"""
        controller, mock_leds = leds_controller
        
        # Reset mocks to clear initialization calls
        for mock_led in mock_leds:
            mock_led.reset_mock()
        
        # Turn on LED 0
        controller.turn_on(0)
        mock_leds[0].on.assert_called_once()
        assert controller.state[0] is True
        
        # Turn on LED 2
        controller.turn_on(2)
        mock_leds[2].on.assert_called_once()
        assert controller.state[2] is True
        
        # Turn off LED 0
        controller.turn_off(0)
        mock_leds[0].off.assert_called_once()
        assert controller.state[0] is False
        
        # LED 2 should still be on (in state tracking)
        assert controller.state[2] is True

    def test_edge_case_zero_index(self, leds_controller):
        """Test that index 0 works correctly (edge case)"""
        controller, mock_leds = leds_controller
        
        # Reset mocks
        for mock_led in mock_leds:
            mock_led.reset_mock()
        
        # Turn on LED at index 0
        controller.turn_on(0)
        mock_leds[0].on.assert_called_once()
        mock_leds[1].on.assert_not_called()
        mock_leds[2].on.assert_not_called()
        
        # Turn off LED at index 0
        controller.turn_off(0)
        mock_leds[0].off.assert_called_once()

    def test_last_index(self, leds_controller):
        """Test that the last valid index works correctly"""
        controller, mock_leds = leds_controller
        
        # Reset mocks
        for mock_led in mock_leds:
            mock_led.reset_mock()
        
        # Turn on LED at last index (2)
        controller.turn_on(2)
        mock_leds[0].on.assert_not_called()
        mock_leds[1].on.assert_not_called()
        mock_leds[2].on.assert_called_once()
        
        # Turn off LED at last index (2)
        controller.turn_off(2)
        mock_leds[2].off.assert_called_once()

    def test_gpio_pin_assignments(self, mock_led_instances):
        """Test that GPIO pins are assigned correctly"""
        controller = LEDs()
        
        # Verify the specific GPIO pins used
        expected_pins = [17, 18, 27]
        calls = mock_gpiozero.LED.call_args_list
        
        for i, expected_pin in enumerate(expected_pins):
            assert calls[i][0][0] == expected_pin