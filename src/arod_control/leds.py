#!/usr/bin/env python3
"""
Control of LEDs attached to RPi5
Ondrej Chvala <ochvala@utexas.edu>
"""

from typing import List
from gpiozero import LED


class LEDs:
    """A class to control multiple LED objects by managing their states (on/off).
    Parameters:
        - None: This class takes no input parameters at initialization.
    Processing Logic:
        - Initializes a list of LED objects and a list to store their states (on/off) using GPIO pins.
        - Ensures that the number of LED objects matches the number of states initialized.
        - Provides methods to turn an individual LED on or off by its index, and to operate all LEDs simultaneously.
        - Defaults to affecting all LEDs when no index is specified for operations."""
    def __init__(self) -> None:
        self.leds: List[LED] = [LED(17), LED(18), LED(27)]
        self.state: List[bool] = [False, False, False]
        n_leds: int = len(self.leds)
        assert n_leds == len(self.state)
        self.turn_off()

    def turn_off(self, i_led: int = -1) -> None:
        """Turn off specified LED or all LEDs controlled by this function.
        Parameters:
            - i_led (int, optional): The index of the LED to turn off. Defaults to -1, which turns off all LEDs.
        Returns:
            - None: This function does not return any value."""
        if i_led >= 0:
            assert i_led < len(self.leds)
            self.leds[i_led].off()
            self.state[i_led] = False
        else:
            for led in self.leds:
                led.off()

    def turn_on(self, i_led: int = -1) -> None:
        """Turns on a specific LED or all LEDs in the collection.
        Parameters:
            - i_led (int): Index of the LED to turn on. If negative, all LEDs are turned on.
        Returns:
            - None"""
        if i_led >= 0:
            assert i_led < len(self.leds)
            self.leds[i_led].on()
            self.state[i_led] = True
        else:
            for led in self.leds:
                led.on()
