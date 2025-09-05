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
import numpy as np
from arod_control import PORT_CTRL, PORT_STREAM, CONTROL_IP
from devices import get_dht, get_distance, speed_of_sound, motor, sonar, rod_engage, rod_scram, rod_lift
from pke import PointKineticsEquationSolver, ReactorPowerCalculator

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


class Reactivity:
    """ Control rod reactivity class """
    def __init__(self):
        super().__init__()
        self.cr_min: float = 5.0    # Rod minimum controlled position [cm]
        self.cr_max: float = 15.0   # Rod maximum controlled position [cm]
        self.delta_rho: float = 800.0e-5  # Range of reactivity covered, 800 pcm by default
        self.cr_pos = get_distance  # CR position from sonar
        self.distance: float = -999.9  # Current CR position [cm]
        assert self.cr_min < self.cr_max

    @property
    def cr_zero_rho(self) -> float:
        """ Returns CR position at zero reactivity """
        return (self.cr_min + self.cr_max) / 2.0

    @property
    def cr_delta(self) -> float:
        return self.cr_max - self.cr_min

    def get_reactivity(self) -> float:
        """ Reads sonar distance, turns it into reactivity """
        self.distance = self.cr_pos()
        return (self.distance - self.cr_zero_rho) * self.delta_rho / self.cr_delta


def set_speed_of_sound():
    """ Checks temperature and humidity, and updates sonar's speed of sound in air """
    my_speed_of_sound: float = -999.9
    while my_speed_of_sound < 0:
        tempC, humid_pct = get_dht()
        if tempC > -273.15 and humid_pct >= 0.0:
            logger.info(f'Temperature: {tempC:.2f} C, Humidity: {humid_pct:.2f} %')
            my_speed_of_sound = speed_of_sound(tempC, humid_pct)
            sonar.speed_of_sound = my_speed_of_sound
            logger.info(f'Speed of sound set to {my_speed_of_sound}')
        time.sleep(1)


def update_speed_of_sound(wait: float = 10 * 60):
    while True:
        set_speed_of_sound()
        time.sleep(wait)


def connect_with_retry(host, port, handshake, delay=1, max_retries=None):
    """Connect to a server with retry logic using a handshake protocol.
    Parameters:
        - host (str): The server host to connect to.
        - port (int): The port number on the server host.
        - handshake (str): The handshake message to initiate the connection.
        - delay (int, optional): The delay in seconds between retry attempts (default is 5).
    Returns:
        - socket: The connected socket object upon successful connection."""
    attempts = 0
    current_delay = delay

    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            s.sendall(handshake.encode('utf-8') + b'\n')
            logger.info(f"Connected to {handshake} on {host}:{port}.")
            return s
        except Exception as e:
            logger.info(f"Retrying connection to {handshake} on {host}:{port}. Reason: {e}")
            if s:
                try:
                    s.close()
                except Exception as close_exc:
                    logger.warning(f"Error closing socket after failed connect attempt: {close_exc}")

            attempts += 1
            if max_retries is not None and attempts >= max_retries:
                logger.error(f"Max retries reached ({max_retries}), stopping connection attempts.")
                raise ConnectionError(f"Could not connect to {host}:{port} after {max_retries} attempts.") from e

            time.sleep(current_delay)
            # Exponential backoff logic:
            current_delay = min(current_delay * 2, 60)  # max 60 seconds delay after doubling


def stream_sender(sock, power_calculator, cr_reactivity, update_event):
    while True:
        update_event.wait()  # Wait until power_calculator signals data ready
        neutron_density = power_calculator.current_neutron_density
        rho = power_calculator.current_rho
        distance = cr_reactivity.distance
        try:
            sock.sendall(struct.pack('!fff', neutron_density, rho, distance))
        except Exception as e:
            logger.error(f"stream_sender error: {e}")
            # Attempt to reconnect before retrying send
            while True:
                try:  # Close current socket safely
                    sock.close()
                except Exception as close_exc:
                    logger.warning(f"Error closing socket during reconnect: {close_exc}")

                try:
                    logger.info("stream_sender attempting to reconnect...")
                    sock = connect_with_retry(CONTROL_IP, PORT_STREAM, "stream_instr")
                    logger.info("stream_sender reconnected.")
                    break  # Exit reconnect loop
                except Exception as conn_exc:
                    logger.error(f"stream_sender reconnect failed: {conn_exc}")
                    time.sleep(2)  # wait before retrying reconnection

            # After reconnect, send the current data before continuing loop
            try:
                sock.sendall(struct.pack('!fff', neutron_density, rho, distance))
            except Exception as send_exc:
                logger.error(f"stream_sender send after reconnect failed: {send_exc}")

        update_event.clear()


def ctrl_sender(sock):
    # TODO - add handling SRAM, this is just prototype
    while True:
        if random.random() < 0.1:
            switch_msg = {"type": "switch", "value": random.choice([True, False])}
            sock.sendall((json.dumps(switch_msg) + '\n').encode('utf-8'))
        time.sleep(1)


def ctrl_receiver(sock):
    """Receive and log control settings from a socket connection.
    Parameters:
        - sock (socket.socket): A socket object to receive data from.
    Returns:
        - None: This function does not return any value; it processes and logs incoming data."""
    buffer = b""
    while True:
        msg = sock.recv(1024)
        if not msg:
            break
        buffer += msg
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            try:
                data = json.loads(line.decode('utf-8'))  # TODO - use the data!
                logger.info(f"Received control setting: {data}")
            except json.JSONDecodeError:
                logger.info(f"Invalid JSON received: {line}")
                continue
            except Exception as e:
                logger.info(f"Unexpected exception in ctrl_receiver: {e}")
                continue


def main():
    """Starts multiple threads to handle the communication and updates for an instrumentation system.
    Parameters:
        None
    Returns:
        None: This function does not return any value."""
    logger.info("Instrumentation computer started.")
    threading.Thread(target=update_speed_of_sound, daemon=True).start()

    stream_sock = connect_with_retry(CONTROL_IP, PORT_STREAM, "stream_instr")
    ctrl_sock = connect_with_retry(CONTROL_IP, PORT_CTRL, "ctrl_instr")

    threading.Thread(target=ctrl_sender, args=(ctrl_sock,), daemon=True).start()
    threading.Thread(target=ctrl_receiver, args=(ctrl_sock,), daemon=True).start()

    cr_reactivity = Reactivity()
    update_event = threading.Event()
    power_calculator = ReactorPowerCalculator(cr_reactivity.get_reactivity, dt=0.1, update_event=update_event)
    power_calculator.start()
    threading.Thread(target=stream_sender, args=(stream_sock, power_calculator, cr_reactivity, update_event),
                     daemon=True).start()

    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()
