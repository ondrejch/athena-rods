#!/usr/bin/env python3
"""
Main loop for the instrumentation box RPi5
Ondrej Chvala <ochvala@utexas.edu>
"""

import logging
import socket
import queue
import time
import struct
import json
import threading
import numpy as np
from arod_control import PORT_CTRL, PORT_STREAM, CONTROL_IP
from devices import get_dht, get_distance, speed_of_sound, motor, sonar, rod_engage, rod_scram, limit_switch
from pke import PointKineticsEquationSolver, ReactorPowerCalculator
from arod_control.socket_utils import SocketManager, StreamingPacket

# LOGGER
logger = logging.getLogger('AIBox')  # ATHENA rods Instrumentation Box
logger.setLevel(logging.DEBUG)

# Formatter for logging messages
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler logs DEBUG and above
file_handler = logging.FileHandler('ATHENA_instrument.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Console handler logs INFO and above
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Sockets
stream_socket = SocketManager(CONTROL_IP, PORT_STREAM, "stream_instr")
ctrl_socket = SocketManager(CONTROL_IP, PORT_CTRL, "ctrl_instr")

# Communication queues
ctrl_status_q = queue.Queue(maxsize=100)  # Limit size to prevent memory issues


def limit_switch_pressed():
    """Handler for when limit switch is pressed"""
    motor.stop()
    switch_msg = {"type": "limit_switch", "value": "pressed"}
    ctrl_socket.send_json(switch_msg)
    logger.info("Limit switch pressed, motor stopped")


def limit_switch_released():
    """Handler for when limit switch is released"""
    switch_msg = {"type": "limit_switch", "value": "released"}
    ctrl_socket.send_json(switch_msg)
    logger.info("Limit switch released")


# Set up switch callbacks
limit_switch.when_pressed = limit_switch_pressed
limit_switch.when_released = limit_switch_released


def process_ctrl_status():
    """Process control messages from the queue"""
    while True:
        try:
            # Try to get a message with timeout
            ctrl_status = ctrl_status_q.get(timeout=1)
            logger.info(f"Processing control message: {ctrl_status}")

            # Handle different message types
            if 'type' in ctrl_status:
                message_type = ctrl_status.get('type')

                if message_type == 'settings':
                    # Process settings message
                    motor_set = ctrl_status.get('motor_set', 0)
                    servo_set = ctrl_status.get('servo_set', 0)
                    source_set = ctrl_status.get('source_set', 0)

                    logger.info(f"Received settings: motor={motor_set}, servo={servo_set}, source={source_set}")

                    # Add implementation for handling these settings
                    # Example:
                    if motor_set == 1:
                        motor.up()
                    elif motor_set == -1:
                        motor.down()
                    else:
                        motor.stop()

                    if servo_set == 1:
                        rod_engage()
                    else:
                        rod_scram()

            # Mark task as done
            ctrl_status_q.task_done()

        except queue.Empty:
            # No messages in queue, just continue
            pass
        except Exception as e:
            logger.error(f"Error processing control status: {e}")

        time.sleep(0.1)


def rod_lift():
    """Temporarily overwrites limit switch to lift the rod reliably"""
    try:
        rod_engage()
        original_callback = limit_switch.when_pressed
        limit_switch.when_pressed = None
        motor.up()
        time.sleep(0.7)
        motor.stop()
        limit_switch.when_pressed = original_callback
        logger.info("Rod lifted successfully")
    except Exception as e:
        logger.error(f"Error during rod_lift: {e}")
        motor.stop()  # Safety stop
        limit_switch.when_pressed = limit_switch_pressed  # Restore callback


class Reactivity:
    """Control rod reactivity class"""

    def __init__(self):
        super().__init__()
        self.cr_min: float = 5.0  # Rod minimum controlled position [cm]
        self.cr_max: float = 15.0  # Rod maximum controlled position [cm]
        self.delta_rho: float = 800.0e-5  # Range of reactivity covered, 800 pcm by default
        self.cr_pos = get_distance  # CR position from sonar
        self.distance: float = -999.9  # Current CR position [cm]
        assert self.cr_min < self.cr_max

    @property
    def cr_zero_rho(self) -> float:
        """Returns CR position at zero reactivity"""
        return (self.cr_min + self.cr_max) / 2.0

    @property
    def cr_delta(self) -> float:
        """Return the control rod range"""
        return self.cr_max - self.cr_min

    def get_reactivity(self) -> float:
        """Reads sonar distance, turns it into reactivity"""
        try:
            self.distance = self.cr_pos()
            return (self.distance - self.cr_zero_rho) * self.delta_rho / self.cr_delta
        except Exception as e:
            logger.error(f"Error getting reactivity: {e}")
            return 0.0  # Safe default


def set_speed_of_sound():
    """Checks temperature and humidity, and updates sonar's speed of sound in air"""
    my_speed_of_sound: float = -999.9
    retry_count = 0
    max_retries = 10

    while my_speed_of_sound < 0 and retry_count < max_retries:
        try:
            tempC, humid_pct = get_dht()
            if tempC > -273.15 and humid_pct >= 0.0:
                logger.info(f'Temperature: {tempC:.2f} C, Humidity: {humid_pct:.2f} %')
                my_speed_of_sound = speed_of_sound(tempC, humid_pct)
                sonar.speed_of_sound = my_speed_of_sound
                logger.info(f'Speed of sound set to {my_speed_of_sound}')
                return True
        except Exception as e:
            logger.warning(f"Error setting speed of sound: {e}")
            retry_count += 1

        time.sleep(1)

    if retry_count >= max_retries:
        logger.error("Failed to set speed of sound after multiple attempts")
        return False

    return True


def update_speed_of_sound(wait: float = 10 * 60):
    """Periodically update the speed of sound based on temperature and humidity"""
    while True:
        try:
            success = set_speed_of_sound()
            if success:
                # Wait for the specified time before next update
                time.sleep(wait)
            else:
                # If failed, retry sooner
                time.sleep(60)
        except Exception as e:
            logger.error(f"Error in update_speed_of_sound: {e}")
            time.sleep(60)  # Retry after short delay on error


def ctrl_receiver():
    """Receive and process control messages"""
    while True:
        try:
            # Receive a complete JSON message
            data, success = ctrl_socket.receive_json()

            if success and data:
                logger.debug(f"Received control data: {data}")
                # Put in queue for processing by main thread
                try:
                    ctrl_status_q.put_nowait(data)
                except queue.Full:
                    # Make room by removing oldest item
                    try:
                        ctrl_status_q.get_nowait()
                        ctrl_status_q.put_nowait(data)
                    except (queue.Empty, queue.Full):
                        logger.warning("Control queue management error")
            else:
                time.sleep(1)  # Wait before retry

        except Exception as e:
            logger.error(f"Control receiver error: {e}")
            time.sleep(1)


def stream_sender(power_calculator, cr_reactivity, update_event):
    """Send stream data to control box"""
    while True:
        try:
            # Wait for signal that new data is available
            update_event.wait(timeout=1.0)

            if update_event.is_set():
                # Get current values
                neutron_density = power_calculator.current_neutron_density
                rho = power_calculator.current_rho
                distance = cr_reactivity.distance

                # Pack and send the data
                data = StreamingPacket.pack_float_triplet(neutron_density, rho, distance)
                success = stream_socket.send_binary(data)

                if not success:
                    logger.warning("Failed to send stream data, will retry")

                # Reset the event for next update
                update_event.clear()

        except Exception as e:
            logger.error(f"Stream sender error: {e}")
            time.sleep(1)


def main():
    """Main function that initializes all components and starts threads"""
    # Start speed of sound update thread
    threading.Thread(target=update_speed_of_sound, daemon=True).start()

    # Initialize socket connections with retries
    stream_socket.connect_with_backoff()
    ctrl_socket.connect_with_backoff()

    # Start control message receiver
    threading.Thread(target=ctrl_receiver, daemon=True).start()

    # Initialize reactivity calculation
    cr_reactivity = Reactivity()
    update_event = threading.Event()

    # Start power calculator
    power_calculator = ReactorPowerCalculator(cr_reactivity.get_reactivity, dt=0.1, update_event=update_event)
    power_calculator.start()

    # Start stream sender
    threading.Thread(target=stream_sender, args=(power_calculator, cr_reactivity, update_event), daemon=True).start()

    # Start control message processor
    threading.Thread(target=process_ctrl_status, daemon=True).start()

    logger.info("All threads started, entering main loop")

    # Main loop - could implement additional monitoring or management here
    try:
        while True:
            time.sleep(5)  # Optional: Add health checking logic here
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt detected, shutting down...")
        return


if __name__ == "__main__":
    logger.info("Instrumentation computer started.")
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutting down on keyboard interrupt...")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
    finally:
        # Clean shutdown
        logger.info("Closing sockets and cleaning up...")
        stream_socket.close()
        ctrl_socket.close()
        logger.info("Shutdown complete.")
