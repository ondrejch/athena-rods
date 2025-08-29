#!/usr/bin/env python3
"""
Main loop for the control box RPi5
Ondrej Chvala <ochvala@utexas.edu>
"""

import threading
import time
from leds import LEDs
from display import Display
from authorization import RFID_Authorization, FaceAuthorization


CB_STATE: dict = {  # Control box machine state
    'auth': {       # Authorization status
        'face': '',
        'rfid': False
    },
    'refresh': {    # Refresh rate for loops [s]
        'leds':  2,     # LED
        'display': 2,   # LCD
        'rfid': 120,    # RFID authorization
        'as_1': 0.1     #
    },
    'leds': [9, 9, 9],  # 0 - off, 1 - on, 9 - flashing
    'message': {
        'text': '',     # Text to show
        'timer': 2      # for how long [s]
    },
    'as_1': {     # Synchronized machine state with actuator/sensor box1
        'distance': -1,  # Ultrasound distance measurement
    }
}

APPROVED_USER_NAMES: list[str] = ['Ondrej Chvala']


def run_leds():
    """ Thread that manages state of LEDs """
    leds = LEDs()
    while True:
        time.sleep(CB_STATE['refresh']['leds'])
        for i, led_set in enumerate(CB_STATE['leds']):
            # print(i, led_set)
            if led_set == 0:
                leds.turn_off(i_led=i)
            elif led_set == 1:
                leds.turn_on(i_led=i)
            elif led_set == 9:
                if leds.state(i):
                    leds.turn_off(i_led=i)
                else:
                    leds.turn_on(i_led=i)


def run_display():
    """ Thread that manages the LCD display """
    display = Display()
    while True:
        time.sleep(CB_STATE['refresh']['display'])
        if CB_STATE['message']['text']:
            display.show_message(CB_STATE['message']['text'])
            time.sleep(CB_STATE['message']['timer'])
        else:
            display.show_sensors()


def run_auth():
    """ Thread that manages authorization """
    face_auth = FaceAuthorization()
    rfid_auth = RFID_Authorization()

    while True:
        while not CB_STATE['auth']['face']:     # 1. Wait for face authorization
            detected_name = face_auth.scan_face()
            if detected_name in APPROVED_USER_NAMES:
                CB_STATE['auth']['face'] = detected_name
            time.sleep(2)

        CB_STATE['message']['text'] = f"Authorized user\n{CB_STATE['auth']['face']}"
        CB_STATE['message']['timer'] = 5
        CB_STATE['leds'][2] = 0

        while not rfid_auth.auth_tag():         # 2. Wait for RFID authorization
            time.sleep(2)

        CB_STATE['message']['text'] = f"RFID token authorized\nOK for 15 minutes!"
        CB_STATE['message']['timer'] = 5
        CB_STATE['leds'][2] = 1

        time.sleep(15 * 60)                     # 3. Auth re-checking
        attempts = 5                            # RFID re-authenticate trials

        CB_STATE['leds'][2] = 0
        for i in range(attempts):
            if rfid_auth.auth_tag():
                CB_STATE['leds'][2] = 1
                break
            else:
                time.sleep(2)

        CB_STATE['leds'][2] = 9                 # Reset authorization requirement
        CB_STATE['auth']['face'] = ''


def main_loop():
    # Start all threads
    led_thread = threading.Thread(target=run_leds)
    led_thread.daemon = True
    led_thread.start()
    display_thread = threading.Thread(target=run_display)
    display_thread.daemon = True
    display_thread.start()
    auth_thread = threading.Thread(target=run_auth)
    auth_thread.daemon = True
    auth_thread.start()

    while True:
        pass


if __name__ == "__main__":
    main_loop()
