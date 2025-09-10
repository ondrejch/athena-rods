#!/usr/bin/env python3
"""
Loop to just show RPi5 load on the LCD
Ondrej Chvala <ochvala@utexas.edu>
"""

import threading
import time
from arod_control.display import Display


def run_display() -> None:
    """ Thread that manages the LCD display """
    display = Display()
    time.sleep(2)
    while True:
        display.show_sensors()
        time.sleep(1)


def main_loop() -> None:
    # Start all threads
    """Runs the main loop with threading, primarily for running a display function.
    Parameters:
        None
    Returns:
        None"""
    display_thread = threading.Thread(target=run_display)
    display_thread.daemon = True
    display_thread.start()
    time.sleep(2)

    while True:
        time.sleep(5)
        pass


if __name__ == "__main__":
    main_loop()
