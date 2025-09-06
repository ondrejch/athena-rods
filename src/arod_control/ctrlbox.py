#!/usr/bin/env python3
"""
Main loop for the control box RPi5
Ondrej Chvala <ochvala@utexas.edu>
"""

import logging
import threading
import time
import socket
import json
from arod_control.leds import LEDs
from arod_control.display import Display
from arod_control.authorization import RFID_Authorization, FaceAuthorization
from arod_control import PORT_CTRL, PORT_STREAM     # Socket settings

FAKE_FACE_AUTH: bool = True  # FAKE face authorization, use for developemnt only!!
CB_STATE: dict = {  # Control box machine state
    'auth': {       # Authorization status
        'face': '',
        'rfid': '',
        'disp': False   # Is display computer alllowed to connect?
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
        'distance': -1.0,   # Ultrasound distance measurement [float]
        'motor': 0,         # AROD motor down, stop, up [-1, 0, 1]
        'servo': 0,         # Servo engaging [0, 1]
        'bswitch': 0        # Bottom switch pressed [0, 1]
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

# SOCKET communications setup
connections = {
    "stream_instr": None,
    "stream_display": None,
    "ctrl_instr": None,
    "ctrl_display": None,
}
lock = threading.Lock()
server_stream: (socket.socket, None) = None
server_ctrl: (socket.socket, None) = None


def accept_connections(server, role, conn_key):
    """ Socket communication: accepting client connections """
    while True:
        time.sleep(0.5)
        conn, addr = server.accept()
        try:
            handshake = conn.recv(32).decode('utf-8').strip()
        except Exception:
            conn.close()
            continue
        # Authorization check for display clients only
        if role.startswith("stream_display") or role.startswith("ctrl_display"):
            if not CB_STATE['auth']['disp']:
                logger.info(f"Rejected {role} connection from {addr} due to AUTH=False")
                conn.sendall(b'REJECT:UNAUTHORIZED\n')
                conn.close()
                continue
        if handshake != role:
            conn.close()
            continue
        with lock:
            connections[conn_key] = conn
        logger.info(f"Socket connection: {role} connected from {addr}")


def forward_stream(src_key, dst_key):
    """ Socket communication: forwarding stream from Instrumentation to Display computers """
    while True:
        with lock:
            src_sock = connections.get(src_key)
            dst_sock = connections.get(dst_key)
        if not src_sock or not dst_sock:
            continue
        try:
            data = src_sock.recv(12)  # 3 floats: neutron_density, reactivity, and distance
            if not data:
                break
            dst_sock.sendall(data)
        except Exception as e:
            logger.info(f"Stream {src_key} to {dst_key} error:", e)
            break


def forward_ctrl(src_key, dst_key):
    """ Socket communication: Forwarding JSON-formatted messages """
    buffer = b""
    while True:
        with lock:
            src_sock = connections.get(src_key)
            dst_sock = connections.get(dst_key)
        if not src_sock or not dst_sock:
            continue
        try:
            msg = src_sock.recv(1024)
            if not msg:
                break
            buffer += msg
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                try:
                    json.loads(line.decode('utf-8'))  # parse, just check validity
                    dst_sock.sendall(line + b'\n')
                except json.JSONDecodeError:
                    # Invalid JSON, skip this line
                    logger.info(f"Invalid JSON received on {src_key}: {line}")
                    continue
                except Exception as e:
                    logger.info(f"Unexpected exception in forward_ctrl JSON parse: {e}")
                    continue
        except Exception as e:
            logger.info(f"Control {src_key} to {dst_key} error: {e}")
            break


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
    logger.info('Authorization thread initialized')
    while True:
        if not FAKE_FACE_AUTH:
            while not CB_STATE['auth']['face']:     # 1. Wait for face authorization
                detected_name = face_auth.scan_face()
                if detected_name in APPROVED_USER_NAMES:
                    CB_STATE['auth']['face'] = detected_name
                    logger.info(f'Authorization: authorized user {detected_name} by face')
                else:
                    time.sleep(2)
            else:
                detected_name = APPROVED_USER_NAMES[0]
                CB_STATE['auth']['face'] = detected_name
                logger.info(f'FAKE Authorization: authorized user {detected_name} by face')

        CB_STATE['message']['text'] = f"Authorized user\n{CB_STATE['auth']['face']}"
        CB_STATE['message']['timer'] = 5
        CB_STATE['leds'][1] = 0

        logger.info(f"RFID: {CB_STATE['auth']['rfid']}")
        while not CB_STATE['auth']['rfid']:     # 2. Wait for RFID authorization
            (tag_id, tag_t) = rfid_auth.read_tag()
            logger.debug(f"tag_id, tag_t: {tag_id}, {tag_t}")
            if rfid_auth.auth_tag():
                CB_STATE['auth']['rfid'] = tag_id
                logger.debug(f"auth ok, tag {tag_id}")
            else:
                logger.info('Authorization: RFID failed')
                time.sleep(2)

        logger.info(f"Authorization: RFID {CB_STATE['auth']['rfid']} token authorized, OK for {CB_STATE['refresh']['rfid']//60} minutes!")
        CB_STATE['message']['text'] = f"RFID authorized\nOK for {CB_STATE['refresh']['rfid']//60} mins!"
        CB_STATE['message']['timer'] = 5
        CB_STATE['leds'][1] = 1
        CB_STATE['auth']['disp'] = True

        time.sleep(CB_STATE['refresh']['rfid']) # 3. Auth re-checking
        attempts = 5                            # RFID re-authenticate trials

        CB_STATE['leds'][1] = 0
        for i in range(attempts):
            if rfid_auth.auth_tag():
                CB_STATE['auth']['disp'] = True
                CB_STATE['leds'][1] = 1
                break
            time.sleep(2)

        if CB_STATE['leds'][1] == 0:            # Reset authorization requirement
            CB_STATE['leds'][1] = 9
            CB_STATE['auth']['face'] = ''
            CB_STATE['auth']['disp'] = False
            logger.info("Authorization: RFID re-authorization failed, resetting to unauthorized!")


def main_loop():
    global server_stream, server_ctrl

    # Start all threads

    # LED driver
    """Start multiple threads to handle LED, LCD, authorization, and socket communication processes.
    Parameters:
        None
    Returns:
        None"""
    led_thread = threading.Thread(target=run_leds)
    led_thread.daemon = True
    led_thread.start()

    # LCD driver
    display_thread = threading.Thread(target=run_display)
    display_thread.daemon = True
    display_thread.start()
    time.sleep(2)

    # Authorization
    auth_thread = threading.Thread(target=run_auth)
    auth_thread.daemon = True
    auth_thread.start()

    # Stream sockets
    HOST = '0.0.0.0'  # Localhost
    server_stream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_stream.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_stream.bind((HOST, PORT_STREAM))
    server_stream.listen(5)
    logger.info(f"Control computer listening for streaming on {PORT_STREAM}")

    # Control sockets
    server_ctrl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_ctrl.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_ctrl.bind((HOST, PORT_CTRL))
    server_ctrl.listen(5)
    logger.info(f"Control computer listening for messages on {PORT_STREAM}")

    # Socket connection threads
    threading.Thread(target=accept_connections, args=(server_stream, "stream_instr", "stream_instr"), daemon=True).start()
    threading.Thread(target=accept_connections, args=(server_stream, "stream_display", "stream_display"), daemon=True).start()
    threading.Thread(target=accept_connections, args=(server_ctrl, "ctrl_instr", "ctrl_instr"), daemon=True).start()
    threading.Thread(target=accept_connections, args=(server_ctrl, "ctrl_display", "ctrl_display"), daemon=True).start()

    # Socket communication threads
    threading.Thread(target=forward_stream, args=("stream_instr", "stream_display"), daemon=True).start()
    threading.Thread(target=forward_stream, args=("stream_display", "stream_instr"), daemon=True).start()
    threading.Thread(target=forward_ctrl, args=("ctrl_instr", "ctrl_display"), daemon=True).start()
    threading.Thread(target=forward_ctrl, args=("ctrl_display", "ctrl_instr"), daemon=True).start()

    while True:
        time.sleep(5)
        pass


if __name__ == "__main__":
    logger.info("*** ATHENA rods Control Box started ***")
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("Ctrl+C detected, shutting down sockets and threads...")
        try:
            server_stream.close()
            server_ctrl.close()
        except Exception as e:
            logger.warning(f"Error closing sockets: {e}")
        # Optionally join threads here if they are not daemon
        logger.info("Shutdown complete.")
