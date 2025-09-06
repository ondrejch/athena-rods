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
connections = {"stream_instr": None, "stream_display": None, "ctrl_instr": None, "ctrl_display": None, }
connection_lock = threading.Lock()
servers = {"stream": None, "ctrl": None}


def accept_connections(server_socket, role, conn_key):
    """Socket communication: accepting client connections with improved error handling"""
    while True:
        try:
            # Accept new connections with a timeout
            server_socket.settimeout(5.0)
            conn, addr = server_socket.accept()
            server_socket.settimeout(None)  # Reset to blocking mode

            # Set a generous initial timeout for handshake
            conn.settimeout(10.0)
            logger.info(f"Incoming connection for {role} from {addr}")

            # Receive handshake with clear size limit
            try:
                handshake_data = conn.recv(128)  # Increased buffer for handshake
                if not handshake_data:
                    logger.warning(f"Empty handshake from {addr}, closing connection")
                    conn.close()
                    continue
            except socket.timeout:
                logger.warning(f"Handshake timeout from {addr}, closing connection")
                conn.close()
                continue

            # Process handshake
            try:
                handshake = handshake_data.decode('utf-8').strip()
                # Remove any trailing newline that may be part of the handshake
                if handshake.endswith('\n'):
                    handshake = handshake[:-1]
            except UnicodeDecodeError:
                logger.warning(f"Invalid handshake encoding from {addr}, closing connection")
                conn.close()
                continue

            # Authorization check for display clients only
            if role.startswith("stream_display") or role.startswith("ctrl_display"):
                if not CB_STATE['auth']['disp']:
                    logger.info(f"Rejected {role} connection from {addr} due to AUTH=False")
                    try:
                        conn.sendall(b'REJECT:UNAUTHORIZED\n')
                        conn.close()
                    except Exception as e:
                        logger.warning(f"Error sending rejection message: {e}")
                    continue

            # Verify handshake matches expected role
            if handshake != role:
                logger.warning(f"Invalid handshake '{handshake}' from {addr}, expected '{role}'")
                try:
                    conn.sendall(b'REJECT:INVALID_HANDSHAKE\n')
                    conn.close()
                except Exception as e:
                    logger.warning(f"Error sending handshake rejection: {e}")
                continue

            # Handshake OK, send acknowledgment
            try:
                conn.sendall(b'OK:CONNECTED\n')
            except Exception as e:
                logger.warning(f"Error sending connection acknowledgment: {e}")
                conn.close()
                continue

            # Connection accepted, update connection dict with lock
            with connection_lock:
                old_conn = connections.get(conn_key)
                if old_conn is not None:
                    logger.info(f"Closing previous {conn_key} connection")
                    try:
                        old_conn.shutdown(socket.SHUT_RDWR)
                        old_conn.close()
                    except Exception as e:
                        logger.warning(f"Error closing old connection: {e}")

                # Use a more reasonable timeout for normal operation
                conn.settimeout(3.0)
                connections[conn_key] = conn
                logger.info(f"Socket connection: {role} connected from {addr}")

        except socket.timeout:
            # Accept timeout, just continue
            continue

        except OSError as e:
            if e.errno == 9:  # Bad file descriptor, socket likely closed
                logger.info(f"Accept thread for {role} exiting due to socket close")
                break
            else:
                logger.warning(f"OSError in accept_connections: {e}")
                time.sleep(1)

        except Exception as e:
            logger.error(f"Unexpected error in accept_connections: {e}")
            time.sleep(1)


def forward_stream(src_key, dst_key):
    """
    Socket communication: forwarding stream data between connections
    with robust error handling and reconnection logic
    """
    buffer = b""  # Buffer to accumulate partial messages

    while True:
        # Get current connections under lock
        with connection_lock:
            src_sock = connections.get(src_key)
            dst_sock = connections.get(dst_key)

        # Skip if either connection is missing
        if not src_sock or not dst_sock:
            time.sleep(0.1)
            continue

        try:
            # Set a reasonable timeout - not too short
            src_sock.settimeout(3.0)  # Increased timeout

            # Try to receive data into buffer
            try:
                chunk = src_sock.recv(1024)  # Receive a larger chunk for efficiency
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
                                connections[dst_key].close()
                            except:
                                pass
                            connections[dst_key] = None
                    break  # Exit inner loop, reset connections

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

            # Longer delay before retry to allow reconnection
            time.sleep(1.0)

        except socket.timeout:
            # Timeout is not fatal, just continue
            continue

        except Exception as e:
            logger.error(f"Unexpected error in forward_stream between {src_key} and {dst_key}: {e}")
            # Don't clear connections on unexpected errors, just wait
            time.sleep(1.0)


def forward_ctrl(src_key, dst_key):
    """
    Socket communication: Forwarding JSON-formatted messages between control sockets
    with improved buffer management and error handling
    """
    buffer = b""

    while True:
        # Get current connections under lock
        with connection_lock:
            src_sock = connections.get(src_key)
            dst_sock = connections.get(dst_key)

        # Skip if either connection is missing
        if not src_sock or not dst_sock:
            time.sleep(0.1)
            continue

        try:
            # Set a reasonable timeout - not too short
            src_sock.settimeout(3.0)  # Increased timeout

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
                                    connections[dst_key].close()
                                except:
                                    pass
                                connections[dst_key] = None
                        break  # Exit inner loop, reset connections

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

            # Longer delay before retry
            time.sleep(1.0)

        except socket.timeout:
            # Timeout is not fatal, just continue
            continue

        except Exception as e:
            logger.error(f"Unexpected error in forward_ctrl between {src_key} and {dst_key}: {e}")
            # Shorter delay for non-connection errors
            time.sleep(0.5)


def run_leds():
    """Thread that manages state of LEDs"""
    leds = LEDs()
    logger.info('LEDs thread initialized')
    while True:
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
    while True:
        message = CB_STATE['message']['text']
        time.sleep(CB_STATE['refresh']['display'])
        if message:
            display.show_message(message)
            message = message.replace("\n", " \\\\ ")
            logger.info(f"LCD display: show message {message} for {CB_STATE['message']['timer']} sec")
            CB_STATE['message']['text'] = ''
            time.sleep(CB_STATE['message']['timer'] - CB_STATE['refresh']['display'])
        else:
            display.show_sensors()


def run_auth():
    """Thread that manages authorization"""
    rfid_auth = RFID_Authorization()
    face_auth = FaceAuthorization()
    logger.info('Authorization thread initialized')
    while True:
        if not FAKE_FACE_AUTH:
            while not CB_STATE['auth']['face']:  # 1. Wait for face authorization
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
        while not CB_STATE['auth']['rfid']:  # 2. Wait for RFID authorization
            (tag_id, tag_t) = rfid_auth.read_tag()
            logger.debug(f"tag_id, tag_t: {tag_id}, {tag_t}")
            if rfid_auth.auth_tag():
                CB_STATE['auth']['rfid'] = tag_id
                logger.debug(f"auth ok, tag {tag_id}")
            else:
                logger.info('Authorization: RFID failed')
                time.sleep(2)

        logger.info(
            f"Authorization: RFID {CB_STATE['auth']['rfid']} token authorized, OK for {CB_STATE['refresh']['rfid'] // 60} minutes!")
        CB_STATE['message']['text'] = f"RFID authorized\nOK for {CB_STATE['refresh']['rfid'] // 60} mins!"
        CB_STATE['message']['timer'] = 5
        CB_STATE['leds'][1] = 1
        CB_STATE['auth']['disp'] = True

        time.sleep(CB_STATE['refresh']['rfid'])  # 3. Auth re-checking
        attempts = 5  # RFID re-authenticate trials

        CB_STATE['leds'][1] = 0
        for i in range(attempts):
            if rfid_auth.auth_tag():
                CB_STATE['auth']['disp'] = True
                CB_STATE['leds'][1] = 1
                break
            time.sleep(2)

        if CB_STATE['leds'][1] == 0:  # Reset authorization requirement
            CB_STATE['leds'][1] = 9
            CB_STATE['auth']['face'] = ''
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
    # Start all threads
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

    # Socket connection threads
    socket_threads = [
        threading.Thread(target=accept_connections, args=(servers["stream"], "stream_instr", "stream_instr"),
                         daemon=True),
        threading.Thread(target=accept_connections, args=(servers["stream"], "stream_display", "stream_display"),
                         daemon=True),
        threading.Thread(target=accept_connections, args=(servers["ctrl"], "ctrl_instr", "ctrl_instr"), daemon=True),
        threading.Thread(target=accept_connections, args=(servers["ctrl"], "ctrl_display", "ctrl_display"),
                         daemon=True)]

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


if __name__ == "__main__":
    logger.info("*** ATHENA rods Control Box started ***")
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("Ctrl+C detected, shutting down sockets and threads...")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
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
