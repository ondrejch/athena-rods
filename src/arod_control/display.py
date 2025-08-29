#!/usr/bin/env python3
"""
Tools for LCD1602
Ondrej Chvala <ochvala@utexas.edu>
"""
import LCD1602  # LCD1602 interface
import os
from hwsens import get_sensors
from datetime import datetime


class Display():
    def __init__(self):
        # Initialize LCD with I2C address 0x27 and enable backlight
        LCD1602.init(0x27, 1)
        LCD1602.write(0, 0, f' ** ATHENA rods **')
        LCD1602.write(0, 1, datetime.now().isoformat())

    def show_sensors(self):
        load5 = os.getloadavg()[2]
        sens = get_sensors()
        LCD1602.write(0, 0, f'L {load5:.2f}, {sens["fan1"]:.0f} rpm')
        LCD1602.write(0, 1, f'temp {sens["temp1"]:.1f} C')

    def show_message(self, message: str):
        if '\n' in message:     # Multi-line messages are shown on
            lines = message.split('\n')
            LCD1602.write(0, 0, lines[0])
            LCD1602.write(0, 1, lines[1])
        else:                   # Single-line message is split to fit
            m = message.strip()
            LCD1602.write(0, 0, m)
            if len(m) > 16:
                LCD1602.write(0, 1, m[16:])
