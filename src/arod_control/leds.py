#!/usr/bin/env python3
"""
Control of LEDs attached to RPi5
Ondrej Chvala <ochvala@utexas.edu>
"""

from gpiozero import LED


class LEDs:
    def __init__(self):
        self.leds = [LED(17), LED(18), LED(27)]
        self.state = [False, False, False]
        n_leds: int = len(self.leds)
        assert n_leds == len(self.state)
        self.turn_off()

    def turn_off(self, i_led: int = -1):
        if i_led >= 0:
            assert i_led < len(self.leds)
            self.leds[i_led].off()
            self.state[i_led] = False
        else:
            for led in self.leds:
                led.off()

    def turn_on(self, i_led: int = -1):
        if i_led >= 0:
            assert i_led < len(self.leds)
            self.leds[i_led].on()
            self.state[i_led] = True
        else:
            for led in self.leds:
                led.on()
