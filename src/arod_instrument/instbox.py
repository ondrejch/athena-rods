#!/usr/bin/env python3
"""
Main loop for the instrumentation box RPi5
Ondrej Chvala <ochvala@utexas.edu>
"""

import logging
import socket
import time
import random
import struct
import json
import threading
from arod_control import PORT_CTRL, PORT_STREAM, CONTROL_IP

# LOGGER
logger = logging.getLogger('AIBox')  # ATHENA rods Control Box
logger.setLevel(logging.DEBUG)

# Formatter for logging messages
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler logs DEBUG and above
file_handler = logging.FileHandler('ATHENA_instrument.log')
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


def connect_with_retry(host, port, handshake, delay=5):
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            s.sendall(handshake.encode('utf-8') + b'\n')
            return s
        except Exception as e:
            logger.info(f"Retrying connection to {handshake} on {host}:{port}. Reason: {e}")
            time.sleep(delay)


def stream_sender(sock):
    while True:
        neutron_density = random.uniform(0, 100)
        position = random.uniform(-10, 10)
        sock.sendall(struct.pack('!ff', neutron_density, position))
        time.sleep(1)


def ctrl_sender(sock):
    while True:
        if random.random() < 0.1:
            switch_msg = {"type": "switch", "value": random.choice([True, False])}
            sock.sendall((json.dumps(switch_msg) + '\n').encode('utf-8'))
        time.sleep(1)


def ctrl_receiver(sock):
    buffer = b""
    while True:
        msg = sock.recv(1024)
        if not msg:
            break
        buffer += msg
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            try:
                logger.info("Received control setting:", json.loads(line.decode('utf-8')))
            except json.JSONDecodeError:
                logger.info(f"Invalid JSON received: {line}")
                continue
            except Exception as e:
                logger.info(f"Unexpected exception in ctrl_receiver: {e}")
                continue


def main():
    stream_sock = connect_with_retry(CONTROL_IP, PORT_STREAM, "stream_instr")
    ctrl_sock = connect_with_retry(CONTROL_IP, PORT_CTRL, "ctrl_instr")

    threading.Thread(target=stream_sender, args=(stream_sock,), daemon=True).start()
    threading.Thread(target=ctrl_sender, args=(ctrl_sock,), daemon=True).start()
    threading.Thread(target=ctrl_receiver, args=(ctrl_sock,), daemon=True).start()

    logger.info("Instrumentation computer running.")
    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()
