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
from arod_control.socket_utils import StreamingPacket  # For packet size (now 4 floats)

FAKE_FACE_AUTH: bool = True  # FAKE face authorization, use for development only!!
CB_STATE: dict = {  # Control box machine state
    'auth': {       # Authorization status
        'face': '',
        'rfid': '',
        'disp': False   # Is display computer allowed to connect?
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
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)
# SOCKET communications setup
connections = {
    "stream_instr": None,
    "stream_display": [],  # Changed to list
    "ctrl_instr": None,
    "ctrl_display": []     # Changed to list
}
connection_lock = threading.Lock()
servers = {
    "stream": None,
    "ctrl": None
}
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
                conn.close()
                continue

            if handshake == "stream_display" and not CB_STATE['auth']['disp']:
                logger.info(f"Rejected {handshake} connection from {addr} due to AUTH=False")
                conn.close()
                continue

            with connection_lock:
                if handshake == "stream_display":
                    # Add to list of display clients
                    conn.settimeout(3.0)
                    connections[handshake].append(conn)
                    logger.info(f"Socket connection: {handshake} connected from {addr}. Total clients: {len(connections[handshake])}")
                else: # stream_instr
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
                if handshake == "ctrl_display":
                    # Add to list of display clients
                    conn.settimeout(3.0)
                    connections[handshake].append(conn)
                    logger.info(f"Socket connection: {handshake} connected from {addr}. Total clients: {len(connections[handshake])}")
                else: # ctrl_instr
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
    with robust error handling and reconnection logic.
    Supports one-to-many broadcasting for stream_display.
    """
    buffer = b""  # Buffer to accumulate partial messages
    packet_size = StreamingPacket.PACKET_SIZE_TIME64  # 3*F32 + 1*F64 (20 bytes)
    is_broadcast = (dst_key == "stream_display")

    while not stop_event.is_set():
        with connection_lock:
            src_sock = connections.get(src_key)
            dst_socks = connections[dst_key] if is_broadcast else [connections.get(dst_key)]
            dst_socks = [s for s in dst_socks if s]  # Filter out None

        if not src_sock or not dst_socks:
            time.sleep(0.1)
            continue

        try:
            src_sock.settimeout(1.0)
            try:
                chunk = src_sock.recv(1024)
                if not chunk:
                    raise ConnectionResetError(f"Connection closed from {src_key}")
                buffer += chunk
            except socket.timeout:
                continue

            while len(buffer) >= packet_size:
                packet, buffer = buffer[:packet_size], buffer[packet_size:]

                failed_dsts = []
                for dst_sock in dst_socks:
                    try:
                        dst_sock.sendall(packet)
                    except Exception as e:
                        logger.error(f"Error forwarding packet to a {dst_key} client: {e}")
                        failed_dsts.append(dst_sock)

                if failed_dsts and is_broadcast:
                    with connection_lock:
                        for sock in failed_dsts:
                            try:
                                connections[dst_key].remove(sock)
                                sock.close()
                            except (ValueError, Exception):
                                pass # Ignore if already removed or closed
                        logger.info(f"Removed {len(failed_dsts)} failed {dst_key} clients. Remaining: {len(connections[dst_key])}")

        except (ConnectionResetError, BrokenPipeError) as e:
            logger.info(f"Stream {src_key} to {dst_key} connection error: {e}")
            buffer = b""
            with connection_lock:
                if connections.get(src_key) == src_sock:
                    try:
                        src_sock.close()
                    except: pass
                    connections[src_key] = None
            time.sleep(0.5)
        except socket.timeout:
            continue
        except Exception as e:
            if stop_event.is_set():
                break
            logger.error(f"Unexpected error in forward_stream between {src_key} and {dst_key}: {e}")
            time.sleep(0.5)


def forward_ctrl(src_key, dst_key):
    """
    Socket communication: Forwarding JSON-formatted messages between control sockets.
    Supports many-to-one and one-to-many forwarding.
    """
    is_src_broadcast = (src_key == "ctrl_display")
    is_dst_broadcast = (dst_key == "ctrl_display")

    # We need a separate buffer for each source socket in a many-to-one scenario
    buffers = {} # socket -> buffer bytes

    while not stop_event.is_set():
        with connection_lock:
            src_socks = connections[src_key] if is_src_broadcast else [connections.get(src_key)]
            src_socks = [s for s in src_socks if s]
            dst_socks = connections[dst_key] if is_dst_broadcast else [connections.get(dst_key)]
            dst_socks = [s for s in dst_socks if s]

        if not src_socks or not dst_socks:
            time.sleep(0.1)
            continue

        failed_srcs = []
        for src_sock in src_socks:
            try:
                src_sock.settimeout(0.01) # non-blocking
                chunk = src_sock.recv(1024)
                if not chunk:
                    raise ConnectionResetError(f"Connection closed from a {src_key} client")

                # Get or create buffer for this source socket
                if src_sock not in buffers:
                    buffers[src_sock] = b""
                buffers[src_sock] += chunk

            except socket.timeout:
                continue
            except (ConnectionResetError, BrokenPipeError) as e:
                logger.info(f"Control connection error with a {src_key} client: {e}")
                failed_srcs.append(src_sock)
                if src_sock in buffers:
                    del buffers[src_sock] # Clean up buffer for disconnected client
                continue
            except Exception as e:
                if stop_event.is_set(): break
                logger.error(f"Unexpected error receiving from a {src_key} client: {e}")
                failed_srcs.append(src_sock)
                if src_sock in buffers:
                    del buffers[src_sock]
                continue

            # Process buffer for this source socket
            buffer = buffers[src_sock]
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                if not line.strip():
                    continue

                try:
                    # Validate JSON
                    json.loads(line.decode('utf-8'))

                    failed_dsts = []
                    for dst_sock in dst_socks:
                        try:
                            dst_sock.sendall(line + b'\n')
                        except Exception as e:
                            logger.error(f"Error forwarding message to a {dst_key} client: {e}")
                            failed_dsts.append(dst_sock)

                    if failed_dsts and is_dst_broadcast:
                        with connection_lock:
                            for sock in failed_dsts:
                                try:
                                    connections[dst_key].remove(sock)
                                    sock.close()
                                except (ValueError, Exception): pass
                            logger.info(f"Removed {len(failed_dsts)} failed {dst_key} clients. Remaining: {len(connections[dst_key])}")

                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from {src_key}: {e}, data: {line[:100]}")
                    continue
            buffers[src_sock] = buffer # Put remaining part back

        if failed_srcs and is_src_broadcast:
            with connection_lock:
                for sock in failed_srcs:
                    try:
                        connections[src_key].remove(sock)
                        sock.close()
                    except (ValueError, Exception): pass
                logger.info(f"Removed {len(failed_srcs)} failed {src_key} clients. Remaining: {len(connections[src_key])}")

        time.sleep(0.01)


def run_leds():
    """Thread that manages state of LEDs"""
    leds = LEDs()
    logger.info('LEDs thread initialized')
    while not stop_event.is_set():
        time.sleep(CB_STATE['refresh']['leds'])

        # Set blue and led status
        global connections
        if connections["stream_instr"] and connections["ctrl_instr"]:
            CB_STATE['leds'][2] = 1
        else:
            CB_STATE['leds'][2] = 0
        if connections["stream_display"] and connections["ctrl_display"]:
            CB_STATE['leds'][0] = 1
        else:
            CB_STATE['leds'][0] = 0

        # Set LEDS accordingly
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
    comm_threads = [
        threading.Thread(target=forward_stream, args=("stream_instr", "stream_display"), daemon=True),
        threading.Thread(target=forward_ctrl, args=("ctrl_instr", "ctrl_display"), daemon=True),
        threading.Thread(target=forward_ctrl, args=("ctrl_display", "ctrl_instr"), daemon=True)
    ]

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
        with connection_lock:
            for conn_name, conns in connections.items():
                if isinstance(conns, list):
                    for conn in conns:
                        if conn:
                            try:
                                conn.close()
                            except Exception: pass
                else:
                    if conns:
                        try:
                            conns.close()
                        except Exception: pass
            logger.info("All connections closed.")

        logger.info("Shutdown complete.")
