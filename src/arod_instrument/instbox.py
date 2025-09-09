#!/usr/bin/env python3
"""
Main loop for the instrumentation box RPi5
Ondrej Chvala <ochvala@utexas.edu>
"""

import logging
import queue
import time
import threading
import os
import ssl
from arod_control import PORT_CTRL, PORT_STREAM, CONTROL_IP
from devices import get_dht, get_distance, speed_of_sound, motor, sonar, rod_engage, rod_scram, limit_switch
from pke import ReactorPowerCalculator
from arod_control.socket_utils import SocketManager, StreamingPacket
from arod_control import USE_SSL, AUTH_ETC_PATH

# Where the SSL certificates are
CERT_DIR: str = os.path.join(os.path.expanduser("~"), AUTH_ETC_PATH, "certs")

# External source for PKE
SOURCE_STRENGTH: float = 5.0  # Default external neutron source strength when enabled

# Limit on rod extension, 17 cm
MAX_ROD_DISTANCE: float = 17.0

# LOGGER
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("ATHENA_instrument.log"), logging.StreamHandler()])
logger = logging.getLogger('AIBox')  # ATHENA rods Instrumentation Box

# Initialize socket connections with SSL support
stream_socket = SocketManager(
    CONTROL_IP, PORT_STREAM, "stream_instr",
    use_ssl=USE_SSL, cert_dir=CERT_DIR
)
ctrl_socket = SocketManager(
    CONTROL_IP, PORT_CTRL, "ctrl_instr",
    use_ssl=USE_SSL, cert_dir=CERT_DIR
)

# Communication queues
ctrl_status_q = queue.Queue(maxsize=100)  # Limit size to prevent memory issues
stop_event = threading.Event()
current = threading.current_thread()


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


def rod_protection(cr_reactivity):
    """ Continuously checks rod distance and stops motor if overextended """
    while not stop_event.is_set():
        try:
            distance = cr_reactivity.distance
            # Poll the sonar for latest value
            if hasattr(cr_reactivity, 'get_reactivity'):
                cr_reactivity.get_reactivity()
                distance = cr_reactivity.distance
            if distance >= MAX_ROD_DISTANCE:
                if motor.status == 1:  # Only stop if trying to extend further
                    motor.stop()
                    logger.warning(f"Rod overextended! Motor stopped at {distance:.2f} cm.")
            stop_event.wait(timeout=0.1)  # Poll every 100ms, interruptible
        except Exception as e:
            logger.error(f"Error in rod_protection: {e}")
            stop_event.wait(timeout=1)


def process_ctrl_status():
    """Process control messages from the queue"""
    while not stop_event.is_set():
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

                    if motor_set == 1:
                        if limit_switch.is_pressed:
                            rod_lift()
                        motor.up()
                    elif motor_set == -1:
                        if not limit_switch.is_pressed:
                            motor.down()
                    else:
                        motor.stop()

                    if servo_set == 1:
                        rod_engage()
                    else:
                        rod_scram()

                    if 'power_calculator' in globals():
                        if source_set == 1:
                            # Enable external neutron source
                            power_calculator.set_source(SOURCE_STRENGTH)
                            logger.info(f"External neutron source enabled with strength {SOURCE_STRENGTH}")
                        else:
                            # Disable external neutron source
                            power_calculator.set_source(0.0)
                            logger.info("External neutron source disabled")

            # Mark task as done
            ctrl_status_q.task_done()

        except queue.Empty:
            # No messages in queue, just continue
            pass
        except Exception as e:
            logger.error(f"Error processing control status: {e}")

        time.sleep(0.01)


def rod_lift():
    """ Temporarily overwrites limit switch to lift the rod reliably """
    try:
        rod_engage()
        original_callback = limit_switch.when_pressed
        limit_switch.when_pressed = None
        motor.up()
        time.sleep(0.7)
        motor.stop()
        limit_switch.when_pressed = original_callback
        logger.info(f"Rod lifted successfully: {limit_switch.is_pressed}")
    except Exception as e:
        logger.error(f"Error during rod_lift: {e}")
        motor.stop()  # Safety stop
        limit_switch.when_pressed = limit_switch_pressed  # Restore callback


class Reactivity:
    """ Control rod reactivity class """
    def __init__(self):
        super().__init__()
        self.cr_min: float = 5.0  # Rod minimum controlled position [cm]
        self.cr_max: float = 15.0  # Rod maximum controlled position [cm]
        self.delta_rho: float = 800.0e-5  # Range of reactivity covered, 800 pcm by default
        self.cr_pos = get_distance  # CR position from sonar
        self.distance: float = -999.9  # Current CR position [cm], the single source of truth
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
        """Reads sonar distance, updates the internal state, and turns it into reactivity"""
        try:
            # This method now updates the authoritative state
            self.distance = self.cr_pos()
            return (self.distance - self.cr_zero_rho) * self.delta_rho / self.cr_delta
        except Exception as e:
            logger.error(f"Error getting reactivity: {e}")
            self.distance = -999.9 # Ensure distance is reset on error
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

        stop_event.wait(timeout=1)

    if retry_count >= max_retries:
        logger.error("Failed to set speed of sound after multiple attempts")
        return False

    return True


def update_speed_of_sound(wait: float = 10 * 60):
    """Periodically update the speed of sound based on temperature and humidity"""
    while not stop_event.is_set():
        try:
            success = set_speed_of_sound()
            if success:     # Wait for the specified time before next update
                stop_event.wait(timeout=wait)
            else:           # If failed, retry sooner
                stop_event.wait(timeout=60)
        except Exception as e:
            logger.error(f"Error in update_speed_of_sound: {e}")
            stop_event.wait(timeout=60)


def ctrl_receiver():
    """Receive and process control messages"""
    while not stop_event.is_set():
        try:
            # Receive a complete JSON message
            data, success = ctrl_socket.receive_json()

            if success:
                if data:  # Only process if we have actual data
                    # logger.debug(f"Received control data: {data}")
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
                # Don't wait if we had a successful read, even without data
                # This allows more responsive processing of partial messages
                time.sleep(0.01)
            else:
                # Connection issue, wait longer before retry
                stop_event.wait(timeout=1)

        except Exception as e:
            logger.error(f"Control receiver error: {e}")
            stop_event.wait(timeout=1)


def stream_sender(cr_reactivity, update_event):
    """Send stream data to control box"""
    global power_calculator
    counter: int = 0
    while not stop_event.is_set():
        try:
            # Wait for signal that new data is available
            update_event.wait(timeout=1.0)

            if update_event.is_set():
                # Get current values
                neutron_density = power_calculator.current_neutron_density
                rho = power_calculator.current_rho
                # Access distance directly from the reactivity object
                distance = cr_reactivity.distance
                ts_ms = time.time() * 1000.0  # milliseconds since epoch (float64)

                if counter % 10 == 0:
                    logger.info(f"CR pos: {distance:4.1f} cm, rho: {1e5*rho:.0f} pcm, N: {neutron_density:.2e}, t: {ts_ms:.1f} ms")
                counter += 1

                # Pack and send the data (3x float32 + 1x float64 timestamp in ms)
                data = StreamingPacket.pack_triplet_plus_time64(neutron_density, rho, distance, ts_ms)
                success = stream_socket.send_binary(data)

                if not success:
                    logger.warning("Failed to send stream data, will retry")

                # Reset the event for next update
                update_event.clear()

        except Exception as e:
            logger.error(f"Stream sender error: {e}")
            stop_event.wait(timeout=1)


def matrix_led_driver(cr_reactivity, explosion_event):
    """ Driver for matrix LED display; both motor and stop_event are global scope """
    from matrixled import arrowUp, arrowDown, notMoving, displayRectangle
    from matrixled import startUp as matrix_led_start_up
    from matrixled import ledsOff as matrix_led_shut_down
    logger.info("Matrix LED display thread started")
    h_min: float = 3.0
    h_max: float = MAX_ROD_DISTANCE
    dh: float = h_max - h_min
    matrix_led_start_up()

    while not stop_event.is_set():
        # Check for explosion event first, with a short timeout
        if explosion_event.wait(timeout=0.01):
            logger.info("Explosion event triggered, showing animation.")
            for i in range(1, 5):
                if stop_event.is_set(): break
                displayRectangle(i, do_fill=True)
                stop_event.wait(0.2)
            for i in range(1, 5):
                if stop_event.is_set(): break
                displayRectangle(i, do_fill=False)
                stop_event.wait(0.2)

            if not stop_event.is_set():
                explosion_event.clear()  # Reset the event

        if stop_event.is_set():  # If the wait was interrupted by the stop_event, exit the loop
            break

        new_status = motor.status
        old_status = new_status

        pic_jiggle: int = 0  # Offsets the arrow pictures to indicate movement
        while old_status == new_status and not explosion_event.is_set():
            # logger.debug(f'motor status:  {new_status}')
            ih: int = int(7.0 * (cr_reactivity.distance - h_min) / dh)
            if ih < 0:
                ih = 0
            if ih > 8:
                ih = 8
            if motor.status == 0:
                notMoving(pic_jiggle, ih)
            elif motor.status == -1:
                arrowDown(pic_jiggle, ih)
            elif motor.status == 1:
                arrowUp(pic_jiggle, ih)
            else:
                logger.error(f"Motor status: {motor.status}")

            stop_event.wait(timeout=0.2)
            if stop_event.is_set():  # If the wait was interrupted by the stop_event, exit the loop
                break

            if pic_jiggle == 0:
                pic_jiggle = 1
            else:
                pic_jiggle = 0
            new_status = motor.status

    matrix_led_shut_down()


def main():
    """Main function that initializes all components and starts threads"""
    # Start speed of sound update thread
    threading.Thread(target=update_speed_of_sound, daemon=True).start()

    # Initialize socket connections with retries
    stream_socket.connect_with_backoff()
    ctrl_socket.connect_with_backoff()
    logger.info(f"Stream socket connected: {stream_socket.connected}")
    logger.info(f"Control socket connected: {ctrl_socket.connected}")

    # Start control message receiver
    threading.Thread(target=ctrl_receiver, daemon=True).start()

    # Initialize reactivity calculation - this object now holds the state
    cr_reactivity = Reactivity()
    update_event = threading.Event()
    explosion_event = threading.Event()

    # Start matrix LED thread
    threading.Thread(target=matrix_led_driver, args=(cr_reactivity, explosion_event), daemon=True).start()

    # Start power calculator
    global power_calculator
    power_calculator = ReactorPowerCalculator(cr_reactivity.get_reactivity, dt=0.05, update_event=update_event, explosion_event=explosion_event)
    power_calculator.start()

    # Start rod protection thread
    threading.Thread(target=rod_protection, args=(cr_reactivity,), daemon=True).start()

    # Start control message processor, passing the state-holding object
    threading.Thread(target=process_ctrl_status, daemon=True).start()

    # Start stream sender, passing the state-holding object
    threading.Thread(target=stream_sender, args=(cr_reactivity, update_event), daemon=True).start()

    logger.info("All threads started, entering main loop")

    # Main loop - could implement additional monitoring or management here
    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=5.0)
    except KeyboardInterrupt:
        logger.info(f"Threads: {threading.active_count()}\nKeyboard interrupt detected, shutting down...")
        return


if __name__ == "__main__":
    logger.info("Instrumentation computer started.")
    try:
        main()
    except KeyboardInterrupt:
        stop_event.set()
        logger.info("Shutting down on keyboard interrupt...")
    except Exception as e:
        stop_event.set()
        logger.error(f"Unhandled exception in main: {e}")
    finally:
        # Clean shutdown
        logger.info("Closing sockets and cleaning up...")
        stop_event.set()

        global power_calculator
        # Safely stop power calculator
        if 'power_calculator' in globals() and power_calculator is not None:
            try:
                power_calculator.stop()  # Don't call join() - could deadlock if thread is stuck
            except Exception as e:
                logger.warning(f"Error stopping power calculator: {e}")

        time.sleep(0.1)  # wait a little
        # Close sockets with some timeout protection
        try:
            stream_socket.close()
        except Exception as e:
            logger.warning(f"Error closing stream socket: {e}")

        try:
            ctrl_socket.close()
        except Exception as e:
            logger.warning(f"Error closing ctrl socket: {e}")

        logger.info("Shutdown complete.")
