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
from arod_control import PORT_CTRL, PORT_STREAM  # Socket settings
from socket_utils import StreamingPacket

# Configuration
FAKE_FACE_AUTH: bool = True  # FAKE face authorization, use for development only!!
APPROVED_USER_NAMES: list[str] = ['Ondrej Chvala']

# Control box machine state
CB_STATE: dict = {'auth': {  # Authorization status
    'face': '', 'rfid': '', 'disp': False  # Is display computer allowed to connect?
}, 'refresh': {  # Refresh rate for loops [s]
    'leds': 1,  # LED
    'display': 1,  # LCD
    'rfid': 15 * 60,  # RFID authorization
    'as_1': 0.1  #
}, 'leds': [9, 9, 9],  # 0 - off, 1 - on, 9 - flashing
    'message': {'text': '',  # Text to show
        'timer': 2  # for how long [s]
    }, 'as_1': {  # Synchronized machine state with actuator/sensor box1
        'distance': -1.0,  # Ultrasound distance measurement [float]
        'motor': 0,  # AROD motor down, stop, up [-1, 0, 1]
        'servo': 0,  # Servo engaging [0, 1]
        'bswitch': 0  # Bottom switch pressed [0, 1]
    }}

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
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# SOCKET communications setup
connections = {"stream_instr": None, "stream_display": None, "ctrl_instr": None, "ctrl_display": None}
connection_lock = threading.Lock()
servers = {"stream": None, "ctrl": None}
stop_event = threading.Event()  # Global event for clean shutdown


def accept_stream_connections():
    """Accept connections on the stream server and route them based on handshake"""
    server = servers["stream"]
    server.settimeout(1.0)

    while not stop_event.is_set():
        try:
            conn, addr = server.accept()
            conn.settimeout(10.0)
            logger.info(f"Incoming stream connection from {addr}")

            handshake_data = conn.recv(128)
            if not handshake_data:
                logger.warning(f"Empty handshake from {addr}, closing connection")
                conn.close()
                continue

            try:
                handshake = handshake_data.decode('utf-8').strip()
                if handshake.endswith('\n'):
                    handshake = handshake[:-1]
            except UnicodeDecodeError:
                logger.warning(f"Invalid handshake encoding from {addr}, closing connection")
                conn.close()
                continue

            valid = {"stream_instr", "stream_display"}
            if handshake not in valid:
                logger.warning(f"Invalid stream handshake '{handshake}' from {addr}, expected one of {sorted(valid)}")
                # IMPORTANT: do not send any bytes on stream sockets (binary channel)
                conn.close()
                continue

            if handshake == "stream_display" and not CB_STATE['auth']['disp']:
                logger.info(f"Rejected {handshake} connection from {addr} due to AUTH=False")
                # IMPORTANT: close silently; no text on stream channel
                conn.close()
                continue

            # IMPORTANT: no 'OK:CONNECTED' on stream sockets (keep channel strictly binary)

            with connection_lock:
                old = connections.get(handshake)
                if old is not None:
                    logger.info(f"Closing previous {handshake} connection")
                    try:
                        old.shutdown(socket.SHUT_RDWR)
                        old.close()
                    except Exception as e:
                        logger.warning(f"Error closing old connection: {e}")

                conn.settimeout(3.0)
                connections[handshake] = conn
                logger.info(f"Socket connection: {handshake} connected from {addr}")

        except socket.timeout:
            pass
        except Exception as e:
            if stop_event.is_set():
                break
            logger.error(f"Error in accept_stream_connections: {e}")
            time.sleep(1)


def accept_ctrl_connections():
    """Accept connections on the control server and route them based on handshake"""
    server = servers["ctrl"]
    server.settimeout(1.0)

    while not stop_event.is_set():
        try:
            conn, addr = server.accept()
            conn.settimeout(10.0)
            logger.info(f"Incoming control connection from {addr}")

            handshake_data = conn.recv(128)
            if not handshake_data:
                logger.warning(f"Empty handshake from {addr}, closing connection")
                conn.close()
                continue

            try:
                handshake = handshake_data.decode('utf-8').strip()
                if handshake.endswith('\n'):
                    handshake = handshake[:-1]
            except UnicodeDecodeError:
                logger.warning(f"Invalid handshake encoding from {addr}, closing connection")
                conn.close()
                continue

            valid = {"ctrl_instr", "ctrl_display"}
            if handshake not in valid:
                logger.warning(f"Invalid control handshake '{handshake}' from {addr}, expected one of {sorted(valid)}")
                # Avoid sending text; clients expect JSON only
                conn.close()
                continue

            if handshake == "ctrl_display" and not CB_STATE['auth']['disp']:
                logger.info(f"Rejected {handshake} connection from {addr} due to AUTH=False")
                # Avoid sending text here as well
                conn.close()
                continue

            # No 'OK:CONNECTED' either; keep channel JSON-only

            with connection_lock:
                old = connections.get(handshake)
                if old is not None:
                    logger.info(f"Closing previous {handshake} connection")
                    try:
                        old.shutdown(socket.SHUT_RDWR)
                        old.close()
                    except Exception as e:
                        logger.warning(f"Error closing old connection: {e}")

                conn.settimeout(3.0)
                connections[handshake] = conn
                logger.info(f"Socket connection: {handshake} connected from {addr}")

        except socket.timeout:
            pass
        except Exception as e:
            if stop_event.is_set():
                break
            logger.error(f"Error in accept_ctrl_connections: {e}")
            time.sleep(1)


def forward_stream(src_key, dst_key):
    """
    Socket communication: forwarding stream data between connections
    with robust error handling and reconnection logic
    """
    buffer = b""  # Buffer to accumulate partial messages

    while not stop_event.is_set():
        # Get current connections under lock
        with connection_lock:
            src_sock = connections.get(src_key)
            dst_sock = connections.get(dst_key)

        # Skip if either connection is missing
        if not src_sock or not dst_sock:
            time.sleep(0.1)
            continue

        try:
            # Set a reasonable timeout
            src_sock.settimeout(1.0)

            # Try to receive data into buffer
            try:
                chunk = src_sock.recv(1024)
                if not chunk:  # Connection closed
                    raise ConnectionResetError(f"Connection closed from {src_key}")

                buffer += chunk
            except socket.timeout:
                # Timeout is not fatal, just continue
                continue

            # Process complete packets of 12 bytes (3 floats)
            while len(buffer) >= 12:
                packet, buffer = buffer[:12], buffer[12:]

                # Try to forward the packet
                try:
                    dst_sock.sendall(packet)
                except Exception as e:
                    logger.error(f"Error forwarding packet to {dst_key}: {e}")
                    # Mark destination as failed
                    with connection_lock:
                        if dst_key in connections and connections[dst_key] == dst_sock:
                            try:
                                dst_sock.close()
                            except:
                                pass
                            connections[dst_key] = None
                    break

        except (ConnectionResetError, BrokenPipeError) as e:
            logger.info(f"Stream {src_key} to {dst_key} connection error: {e}")
            # Reset buffer when connection is lost
            buffer = b""

            # Clean up the affected connection(s)
            with connection_lock:
                if src_key in connections and connections[src_key] == src_sock:
                    try:
                        src_sock.close()
                    except:
                        pass
                    connections[src_key] = None

            time.sleep(0.5)

        except socket.timeout:
            # Timeout is not fatal, just continue
            continue

        except Exception as e:
            if stop_event.is_set():
                break
            logger.error(f"Unexpected error in forward_stream between {src_key} and {dst_key}: {e}")
            time.sleep(0.5)


def forward_ctrl(src_key, dst_key):
    """
    Socket communication: Forwarding JSON-formatted messages between control sockets
    with improved buffer management and error handling
    """
    buffer = b""

    while not stop_event.is_set():
        # Get current connections under lock
        with connection_lock:
            src_sock = connections.get(src_key)
            dst_sock = connections.get(dst_key)

        # Skip if either connection is missing
        if not src_sock or not dst_sock:
            time.sleep(0.1)
            continue

        try:
            # Set a reasonable timeout
            src_sock.settimeout(1.0)

            # Receive data
            try:
                chunk = src_sock.recv(1024)
                if not chunk:  # Connection closed
                    raise ConnectionResetError(f"Connection closed from {src_key}")

                buffer += chunk
            except socket.timeout:
                # Timeout is not fatal, just continue
                continue

            # Process complete messages
            while b'\n' in buffer:
                try:
                    line, buffer = buffer.split(b'\n', 1)
                except ValueError:
                    # This shouldn't happen given the check above, but just in case
                    break

                # Skip empty lines
                if not line.strip():
                    continue

                try:
                    # Validate JSON before forwarding
                    message = json.loads(line.decode('utf-8'))

                    # Forward valid JSON to destination
                    try:
                        dst_sock.sendall(line + b'\n')
                    except Exception as e:
                        logger.error(f"Error forwarding message to {dst_key}: {e}")
                        # Mark destination as failed
                        with connection_lock:
                            if dst_key in connections and connections[dst_key] == dst_sock:
                                try:
                                    dst_sock.close()
                                except:
                                    pass
                                connections[dst_key] = None
                        break

                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from {src_key}: {e}, data: {line[:100]}")
                    # Skip this line, don't forward invalid JSON
                    continue

        except (ConnectionResetError, BrokenPipeError) as e:
            logger.info(f"Control {src_key} to {dst_key} connection error: {e}")

            # Clean up the affected connection
            with connection_lock:
                if src_key in connections and connections[src_key] == src_sock:
                    try:
                        src_sock.close()
                    except:
                        pass
                    connections[src_key] = None

            # Reset buffer for new connection
            buffer = b""

            time.sleep(0.5)

        except socket.timeout:
            # Timeout is not fatal, just continue
            continue

        except Exception as e:
            if stop_event.is_set():
                break
            logger.error(f"Unexpected error in forward_ctrl between {src_key} and {dst_key}: {e}")
            time.sleep(0.5)


def run_leds():
    """Thread that manages state of LEDs"""
    leds = LEDs()
    logger.info('LEDs thread initialized')
    while not stop_event.is_set():
        time.sleep(CB_STATE['refresh']['leds'])
        for i, led_set in enumerate(CB_STATE['leds']):
            if led_set == 1:  # The LEDs are flipped polarity
                leds.turn_off(i_led=i)
            elif led_set == 0:
                leds.turn_on(i_led=i)
            elif led_set == 9:
                if leds.state[i]:
                    leds.turn_off(i_led=i)
                else:
                    leds.turn_on(i_led=i)


def run_display():
    """Thread that manages the LCD display"""
    display = Display()
    logger.info('LCD display thread initialized')
    while not stop_event.is_set():
        message = CB_STATE['message']['text']
        time.sleep(CB_STATE['refresh']['display'])
        if message:
            display.show_message(message)
            message = message.replace("\n", " \\\\ ")
            logger.info(f"LCD display: show message {message} for {CB_STATE['message']['timer']} sec")
            CB_STATE['message']['text'] = ''
            time.sleep(max(0.1, CB_STATE['message']['timer'] - CB_STATE['refresh']['display']))
        else:
            display.show_sensors()


def run_auth():
    """Thread that manages authorization"""
    rfid_auth = RFID_Authorization()
    face_auth = FaceAuthorization()
    logger.info('Authorization thread initialized')

    # For development: start already authorized
    if FAKE_FACE_AUTH:
        detected_name = APPROVED_USER_NAMES[0]
        CB_STATE['auth']['face'] = detected_name
        CB_STATE['auth']['rfid'] = "fake_rfid_tag"
        CB_STATE['auth']['disp'] = True
        logger.info(f'FAKE Authorization: authorized user {detected_name}')

    while not stop_event.is_set():
        if not CB_STATE['auth']['face']:  # 1. Wait for face authorization
            if not FAKE_FACE_AUTH:
                detected_name = face_auth.scan_face()
                if detected_name in APPROVED_USER_NAMES:
                    CB_STATE['auth']['face'] = detected_name
                    logger.info(f'Authorization: authorized user {detected_name} by face')
                else:
                    if stop_event.wait(timeout=2):  # Wait with early exit
                        return
                    continue
            else:
                detected_name = APPROVED_USER_NAMES[0]
                CB_STATE['auth']['face'] = detected_name
                logger.info(f'FAKE Authorization: authorized user {detected_name} by face')

        CB_STATE['message']['text'] = f"Authorized user\n{CB_STATE['auth']['face']}"
        CB_STATE['message']['timer'] = 5
        CB_STATE['leds'][1] = 0

        logger.info(f"RFID: {CB_STATE['auth']['rfid']}")
        while not CB_STATE['auth']['rfid'] and not stop_event.is_set():  # 2. Wait for RFID authorization
            if FAKE_FACE_AUTH:
                CB_STATE['auth']['rfid'] = "fake_rfid_tag"
                logger.info("FAKE RFID authorization")
                break

            (tag_id, tag_t) = rfid_auth.read_tag()
            logger.debug(f"tag_id, tag_t: {tag_id}, {tag_t}")
            if rfid_auth.auth_tag():
                CB_STATE['auth']['rfid'] = tag_id
                logger.debug(f"auth ok, tag {tag_id}")
            else:
                logger.info('Authorization: RFID failed')
                if stop_event.wait(timeout=2):  # Wait with early exit
                    return

        logger.info(
            f"Authorization: RFID {CB_STATE['auth']['rfid']} token authorized, OK for {CB_STATE['refresh']['rfid'] // 60} minutes!")
        CB_STATE['message']['text'] = f"RFID authorized\nOK for {CB_STATE['refresh']['rfid'] // 60} mins!"
        CB_STATE['message']['timer'] = 5
        CB_STATE['leds'][1] = 1
        CB_STATE['auth']['disp'] = True

        # Wait for auth timeout with early exit check
        auth_timeout = time.time() + CB_STATE['refresh']['rfid']
        while time.time() < auth_timeout and not stop_event.is_set():
            if stop_event.wait(timeout=1.0):
                return

        # 3. Auth re-checking
        attempts = 5  # RFID re-authenticate trials

        CB_STATE['leds'][1] = 0
        for i in range(attempts):
            if stop_event.is_set():
                return

            if FAKE_FACE_AUTH or rfid_auth.auth_tag():
                CB_STATE['auth']['disp'] = True
                CB_STATE['leds'][1] = 1
                break

            if stop_event.wait(timeout=2):
                return

        if CB_STATE['leds'][1] == 0:  # Reset authorization requirement
            CB_STATE['leds'][1] = 9
            CB_STATE['auth']['face'] = ''
            CB_STATE['auth']['rfid'] = ''
            CB_STATE['auth']['disp'] = False
            logger.info("Authorization: RFID re-authorization failed, resetting to unauthorized!")


def setup_socket_servers():
    """Initialize and configure socket servers with proper error handling"""
    try:
        # Stream socket server
        stream_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        stream_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        stream_server.bind(('0.0.0.0', PORT_STREAM))
        stream_server.listen(10)  # Increased from 5 to handle more pending connections
        servers["stream"] = stream_server
        logger.info(f"Stream server listening on port {PORT_STREAM}")

        # Control socket server
        ctrl_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ctrl_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ctrl_server.bind(('0.0.0.0', PORT_CTRL))
        ctrl_server.listen(10)
        servers["ctrl"] = ctrl_server
        logger.info(f"Control server listening on port {PORT_CTRL}")

        return True

    except OSError as e:
        if e.errno == 98:  # Address already in use
            logger.error(f"Socket port already in use: {e}")
        else:
            logger.error(f"Socket server setup error: {e}")
        return False

    except Exception as e:
        logger.error(f"Unexpected error setting up socket servers: {e}")
        return False


def main_loop():
    """Main program loop that starts all threads and manages socket servers"""
    global stop_event
    stop_event = threading.Event()
    threads = []

    # LED driver
    led_thread = threading.Thread(target=run_leds, daemon=True)
    led_thread.start()
    threads.append(led_thread)

    # LCD driver
    display_thread = threading.Thread(target=run_display, daemon=True)
    display_thread.start()
    threads.append(display_thread)
    time.sleep(2)

    # Authorization
    auth_thread = threading.Thread(target=run_auth, daemon=True)
    auth_thread.start()
    threads.append(auth_thread)

    # Setup socket servers
    if not setup_socket_servers():
        logger.error("Failed to setup socket servers, exiting")
        return

    # Socket connection threads - ONE thread per server
    socket_threads = [threading.Thread(target=accept_stream_connections, daemon=True),
        threading.Thread(target=accept_ctrl_connections, daemon=True)]

    for t in socket_threads:
        t.start()
        threads.append(t)

    # Socket communication threads
    comm_threads = [threading.Thread(target=forward_stream, args=("stream_instr", "stream_display"), daemon=True),
        threading.Thread(target=forward_stream, args=("stream_display", "stream_instr"), daemon=True),
        threading.Thread(target=forward_ctrl, args=("ctrl_instr", "ctrl_display"), daemon=True),
        threading.Thread(target=forward_ctrl, args=("ctrl_display", "ctrl_instr"), daemon=True)]

    for t in comm_threads:
        t.start()
        threads.append(t)

    logger.info("All threads started, entering main loop")
    try:
        # Main thread just keeps the program alive
        while True:
            time.sleep(5)  # Optional: Health check could go here
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down")
        stop_event.set()


if __name__ == "__main__":
    logger.info("*** ATHENA rods Control Box started ***")
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("Ctrl+C detected, shutting down sockets and threads...")
        stop_event.set()
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
        stop_event.set()
    finally:
        # Clean shutdown of socket servers
        for server_name, server in servers.items():
            if server:
                try:
                    server.close()
                    logger.info(f"{server_name} server socket closed")
                except Exception as e:
                    logger.warning(f"Error closing {server_name} server socket: {e}")

        # Clean shutdown of client connections
        for conn_name, conn in connections.items():
            if conn:
                try:
                    conn.close()
                    logger.info(f"{conn_name} connection closed")
                except Exception as e:
                    logger.warning(f"Error closing {conn_name} connection: {e}")

        logger.info("Shutdown complete.")
