#!/usr/bin/env python3
"""
Centralized pytest configuration and hardware mocking for athena-rods tests.

This file ensures that all hardware-specific libraries are mocked consistently
across all tests, allowing the test suite to run in any environment without
requiring physical hardware.
"""

import sys
import pytest
from unittest.mock import Mock, MagicMock


def create_mock_gpio():
    """Create a comprehensive mock for RPi.GPIO"""
    mock_gpio = Mock()
    
    # GPIO constants
    mock_gpio.BCM = 11
    mock_gpio.BOARD = 10
    mock_gpio.OUT = 0
    mock_gpio.IN = 1
    mock_gpio.HIGH = 1
    mock_gpio.LOW = 0
    mock_gpio.PUD_UP = 22
    mock_gpio.PUD_DOWN = 21
    mock_gpio.RISING = 31
    mock_gpio.FALLING = 32
    mock_gpio.BOTH = 33
    
    # GPIO functions
    mock_gpio.setmode = Mock()
    mock_gpio.setup = Mock()
    mock_gpio.output = Mock()
    mock_gpio.input = Mock(return_value=0)
    mock_gpio.cleanup = Mock()
    mock_gpio.setwarnings = Mock()
    mock_gpio.add_event_detect = Mock()
    mock_gpio.remove_event_detect = Mock()
    mock_gpio.wait_for_edge = Mock()
    mock_gpio.event_detected = Mock(return_value=False)
    
    return mock_gpio


def create_mock_spidev():
    """Create a comprehensive mock for spidev"""
    mock_spidev = Mock()
    mock_spi = Mock()
    
    # SPI device methods
    mock_spi.open = Mock()
    mock_spi.close = Mock()
    mock_spi.writebytes = Mock()
    mock_spi.readbytes = Mock(return_value=[0])
    mock_spi.xfer = Mock(return_value=[0])
    mock_spi.xfer2 = Mock(return_value=[0])
    
    # SPI properties
    mock_spi.max_speed_hz = 1000000
    mock_spi.mode = 0
    mock_spi.bits_per_word = 8
    
    mock_spidev.SpiDev = Mock(return_value=mock_spi)
    
    return mock_spidev


def create_mock_smbus():
    """Create a comprehensive mock for smbus/smbus2"""
    mock_smbus = Mock()
    mock_bus = Mock()
    
    # SMBus methods
    mock_bus.write_byte = Mock()
    mock_bus.write_byte_data = Mock()
    mock_bus.write_word_data = Mock()
    mock_bus.write_block_data = Mock()
    mock_bus.read_byte = Mock(return_value=0)
    mock_bus.read_byte_data = Mock(return_value=0)
    mock_bus.read_word_data = Mock(return_value=0)
    mock_bus.read_block_data = Mock(return_value=[0])
    mock_bus.close = Mock()
    
    mock_smbus.SMBus = Mock(return_value=mock_bus)
    
    return mock_smbus


def create_mock_sensors():
    """Create a comprehensive mock for sensors (lm-sensors)"""
    mock_sensors = Mock()
    
    # Mock sensor functions
    mock_sensors.init = Mock()
    mock_sensors.cleanup = Mock()
    mock_sensors.iter_detected_chips = Mock(return_value=[])
    
    return mock_sensors


def create_mock_gpiozero():
    """Create a comprehensive mock for gpiozero"""
    mock_gpiozero = Mock()
    
    # Mock LED class
    mock_led = Mock()
    mock_led.on = Mock()
    mock_led.off = Mock()
    mock_led.toggle = Mock()
    mock_led.blink = Mock()
    mock_led.is_lit = False
    
    # Mock Motor class
    mock_motor = Mock()
    mock_motor.forward = Mock()
    mock_motor.backward = Mock()
    mock_motor.stop = Mock()
    mock_motor.value = 0.0
    
    # Mock DistanceSensor class
    mock_distance = Mock()
    mock_distance.distance = 0.5  # 50cm default
    mock_distance.when_in_range = Mock()
    mock_distance.when_out_of_range = Mock()
    
    # Mock AngularServo class
    mock_servo = Mock()
    mock_servo.angle = 0
    mock_servo.min = Mock()
    mock_servo.max = Mock()
    mock_servo.mid = Mock()
    
    # Mock Button class
    mock_button = Mock()
    mock_button.is_pressed = False
    mock_button.when_pressed = Mock()
    mock_button.when_released = Mock()
    
    # Set up the module structure
    mock_gpiozero.LED = Mock(return_value=mock_led)
    mock_gpiozero.Motor = Mock(return_value=mock_motor)
    mock_gpiozero.DistanceSensor = Mock(return_value=mock_distance)
    mock_gpiozero.AngularServo = Mock(return_value=mock_servo)
    mock_gpiozero.Button = Mock(return_value=mock_button)
    
    return mock_gpiozero


# Global hardware mocks setup
@pytest.fixture(scope="session", autouse=True)
def hardware_mocks():
    """
    Session-scoped fixture that mocks all hardware dependencies.
    This runs automatically for all tests and ensures consistent mocking.
    """
    # Create all mocks
    mock_rpi_gpio = create_mock_gpio()
    mock_spidev = create_mock_spidev()
    mock_smbus = create_mock_smbus()
    mock_smbus2 = create_mock_smbus()
    mock_sensors = create_mock_sensors() 
    mock_gpiozero = create_mock_gpiozero()
    
    # Mock subprocess for LCD operations
    mock_subprocess = Mock()
    mock_subprocess.run = Mock()
    mock_subprocess.call = Mock(return_value=0)
    mock_subprocess.check_output = Mock(return_value=b"")
    
    # Apply mocks to sys.modules
    original_modules = {}
    modules_to_mock = {
        'RPi': Mock(),
        'RPi.GPIO': mock_rpi_gpio,
        'spidev': mock_spidev,
        'smbus': mock_smbus,
        'smbus2': mock_smbus2,
        'sensors': mock_sensors,
        'gpiozero': mock_gpiozero,
        'subprocess': mock_subprocess,
    }
    
    # Store original modules and apply mocks
    for module_name, mock_module in modules_to_mock.items():
        if module_name in sys.modules:
            original_modules[module_name] = sys.modules[module_name]
        sys.modules[module_name] = mock_module
    
    yield {
        'RPi.GPIO': mock_rpi_gpio,
        'spidev': mock_spidev, 
        'smbus': mock_smbus,
        'smbus2': mock_smbus2,
        'sensors': mock_sensors,
        'gpiozero': mock_gpiozero,
        'subprocess': mock_subprocess,
    }
    
    # Restore original modules after tests
    for module_name in modules_to_mock:
        if module_name in original_modules:
            sys.modules[module_name] = original_modules[module_name]
        elif module_name in sys.modules:
            del sys.modules[module_name]


@pytest.fixture(scope="function")
def fresh_sensors_mock(mocker):
    """
    Function-scoped fixture for hwsens tests that need isolated sensor mocks.
    This ensures test isolation by providing a fresh mock for each test function.
    """
    # Clean up any existing modules first
    modules_to_clean = ['sensors', 'arod_control.hwsens']
    for module in modules_to_clean:
        if module in sys.modules:
            del sys.modules[module]
    
    # Create fresh mock
    mock_sensors = create_mock_sensors()
    
    # Patch it in sys.modules  
    mocker.patch.dict('sys.modules', {'sensors': mock_sensors})
    
    return mock_sensors