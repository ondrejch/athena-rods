#!/usr/bin/env python3
"""
Tools for LCD1602
Ondrej Chvala <ochvala@utexas.edu>
"""
import os
from datetime import datetime
from arod_control.hwsens import get_sensors
from arod_control import LCD1602  # LCD1602 interface


class Display():
    """Display class: Represents a 16x2 LCD interface, enabling initialization and display of messages and sensor data.
    Parameters:
        - None: The class does not take parameters during initialization.
    Processing Logic:
        - Initializes the LCD display with a specific I2C address and backlight setting.
        - Uses external sensor data to update and display system load and temperature.
        - Supports both single-line and multi-line message displays, fitting text appropriately across two lines of the LCD screen."""
    def __init__(self):
        # Initialize LCD with I2C address 0x27 and enable backlight
        LCD1602.init(0x27, 1)
        LCD1602.write(0, 0, '** ATHENArods **'.ljust(16))
        LCD1602.write(0, 1, datetime.now().isoformat().ljust(16))

    def show_sensors(self):
        load5 = os.getloadavg()[2]
        sens = get_sensors()
        LCD1602.write(0, 0, f'L {load5:.2f}, {sens["fan1"]:.0f} rpm'.ljust(16))
        LCD1602.write(0, 1, f'temp {sens["temp1"]:.1f} C'.ljust(16))

    def show_message(self, message: str):
        """Show a message on a 16x2 LCD screen.
        Parameters:
            - message (str): The message to be displayed on the LCD screen. Can be a single or multi-line string.
        Returns:
            - None: This function does not return a value."""
        if '\n' in message:     # Multi-line messages are shown on
            lines = message.split('\n')
            LCD1602.write(0, 0, lines[0].ljust(16))
            LCD1602.write(0, 1, lines[1].ljust(16))
        else:                   # Single-line message is split to fit
            m = message.strip()
            LCD1602.write(0, 0, m)
            if len(m) > 16:
                LCD1602.write(0, 1, m[16:].ljust(16))
