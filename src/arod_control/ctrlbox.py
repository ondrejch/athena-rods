#!/usr/bin/env python3
"""
Main loop for the control box RPi5
Ondrej Chvala <ochvala@utexas.edu>
"""

import logging
import threading
import time
from arod_control.leds import LEDs
from arod_control.display import Display
from arod_control.authorization import RFID_Authorization, FaceAuthorization


CB_STATE: dict = {  # Control box machine state
    'auth': {       # Authorization status
        'face': '',
        'rfid': ''
    },
    'refresh': {    # Refresh rate for loops [s]
        'leds':  1,     # LED
        'display': 1,   # LCD
        'rfid': 15*60,  # RFID authorization
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

# LOGGER
logger = logging.getLogger('ACBox')  # ATHENA rods Control Box
logger.setLevel(logging.DEBUG)

# Formatter for logging messages
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler logs DEBUG and above
file_handler = logging.FileHandler('ATHENA_controller.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Console handler logs INFO and above
console_handler = logging.StreamHandler()
#console_handler.setLevel(logging.INFO)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Usage examples
# logger.debug('This will go to the log file, but not the console')
# logger.info('This will go to both the log file and the console')
# logger.error('This will go to both the log file and the console')


def run_leds():
    """ Thread that manages state of LEDs """
    leds = LEDs()
    logger.info('LEDs thread initialized')
    while True:
        time.sleep(CB_STATE['refresh']['leds'])
        for i, led_set in enumerate(CB_STATE['leds']):
            # print(i, led_set)
            if led_set == 1:    # The LEDs are flipped polarity
                leds.turn_off(i_led=i)
            elif led_set == 0:
                leds.turn_on(i_led=i)
            elif led_set == 9:
                if leds.state[i]:
                    leds.turn_off(i_led=i)
                else:
                    leds.turn_on(i_led=i)


def run_display():
    """ Thread that manages the LCD display """
    display = Display()
    logger.info('LCD display thread initialized')
    while True:
        message = CB_STATE['message']['text']
        time.sleep(CB_STATE['refresh']['display'])
        if message:
            display.show_message(message)
            message = message.replace("\n"," \\\\ ")
            logger.info(f"LCD display: show message {message} for {CB_STATE['message']['timer']} sec")
            CB_STATE['message']['text'] = ''
            time.sleep(CB_STATE['message']['timer'] - CB_STATE['refresh']['display'])
        else:
            display.show_sensors()


def run_auth():
    """ Thread that manages authorization """
    rfid_auth = RFID_Authorization()
    face_auth = FaceAuthorization()
    logger.info('Autorization thread initialized')
    while True:
        while not CB_STATE['auth']['face']:     # 1. Wait for face authorization
            detected_name = face_auth.scan_face()
            if detected_name in APPROVED_USER_NAMES:
                CB_STATE['auth']['face'] = detected_name
                logger.info(f'Autorization: authorized user {detected_name} by face')
            else:
                time.sleep(2)

        CB_STATE['message']['text'] = f"Authorized user\n{CB_STATE['auth']['face']}"
        CB_STATE['message']['timer'] = 5
        CB_STATE['leds'][1] = 0

        logger.info(f"RFID: {CB_STATE['auth']['rfid']}")
        while not CB_STATE['auth']['rfid']:     # 2. Wait for RFID authorizationa
            (tag_id, tag_t) = rfid_auth.read_tag()
            logger.debug(f"tag_id, tag_t: {tag_id}, {tag_t}")
            if rfid_auth.auth_tag():
                CB_STATE['auth']['rfid'] = tag_id
                logger.debug(f"auth ok")
            else:
                logger.info(f'Authorization: RFID failed')
                time.sleep(2)

        logger.info(f"Authorization: RFID {CB_STATE['auth']['rfid']} token authorized, OK for {CB_STATE['refresh']['rfid']//60} minutes!")
        CB_STATE['message']['text'] = f"RFID authorized\nOK for {CB_STATE['refresh']['rfid']//60} mins!"
        CB_STATE['message']['timer'] = 5
        CB_STATE['leds'][1] = 1

        time.sleep(CB_STATE['refresh']['rfid']) # 3. Auth re-checking
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
        logger.info(f"Authorization: RFID re-authorization failed, resetting to unauthorized!")


def main_loop():
    # Start all threads
    led_thread = threading.Thread(target=run_leds)
    led_thread.daemon = True
    led_thread.start()
    display_thread = threading.Thread(target=run_display)
    display_thread.daemon = True
    display_thread.start()
    time.sleep(2)
    auth_thread = threading.Thread(target=run_auth)
    auth_thread.daemon = True
    auth_thread.start()

    while True:
        time.sleep(5)
        pass


if __name__ == "__main__":
    logger.info(f"*** ATHENA rods Control Box started ***")
    main_loop()

