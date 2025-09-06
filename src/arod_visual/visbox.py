#!/usr/bin/env python3
"""
Main loop for the external visualization and control of ATHENA-rods
Ondrej Chvala <ochvala@utexas.edu>
"""

import socket
import struct
import json
import threading
import time
import logging
from dash import Dash, dcc, html, Input, Output, State
import queue
from arod_control import PORT_CTRL, PORT_STREAM, CONTROL_IP
from arod_control.socket_utils import SocketManager, StreamingPacket

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("visbox.log"), logging.StreamHandler()])
logger = logging.getLogger('VisBox')

# Data queues for thread communication
stream_data_q = queue.Queue(maxsize=1000)  # Limit queue size to prevent memory issues
ctrl_status_q = queue.Queue(maxsize=100)

# Socket managers
stream_socket = SocketManager(CONTROL_IP, PORT_STREAM, "stream_display")
ctrl_socket = SocketManager(CONTROL_IP, PORT_CTRL, "ctrl_display")


def stream_receiver():
    """Receives and processes continuous data stream from a socket."""
    counter = 0
    while True:
        try:
            # Receive exactly 12 bytes (3 floats)
            data, success = stream_socket.receive_exactly(12)
            if not success:
                logger.warning("Failed to receive stream data, reconnecting...")
                time.sleep(1)
                continue

            counter += 1
            neutron_density, rho, position = StreamingPacket.unpack_float_triplet(data)

            # Try to add to queue, but don't block if full (discard old data)
            try:
                stream_data_q.put_nowait((neutron_density, rho, position))
            except queue.Full:
                # Queue is full, get the oldest item to make space
                try:
                    stream_data_q.get_nowait()
                    stream_data_q.put_nowait((neutron_density, rho, position))
                except (queue.Empty, queue.Full):
                    pass  # Rare race condition, just continue

            if counter % 100 == 0:
                logger.info(f"Stream data: n={neutron_density:.2f}, rho={rho:.6f}, pos={position:.2f}")

        except Exception as e:
            logger.error(f"Stream receiver error: {e}")
            time.sleep(1)


def ctrl_receiver():
    """Receives messages from a socket and updates a queue with JSON-decoded status."""
    while True:
        try:
            data, success = ctrl_socket.receive_json()
            if success:
                try:
                    ctrl_status_q.put_nowait(data)
                except queue.Full:
                    # Make room by removing oldest item
                    try:
                        ctrl_status_q.get_nowait()
                        ctrl_status_q.put_nowait(data)
                    except (queue.Empty, queue.Full):
                        pass
            else:
                time.sleep(1)  # Wait before retrying
        except Exception as e:
            logger.error(f"Control receiver error: {e}")
            time.sleep(1)


app = Dash(__name__)
app.layout = html.Div([html.H2("Live Neutron Density"), dcc.Graph(id="live-graph"),
    dcc.Interval(id="interval", interval=1000, n_intervals=0), html.Div(id="connection-status"),
    html.H3("Send Settings"), dcc.Input(id='motor-set', type='number', value=0),
    dcc.Input(id='servo-set', type='number', value=0), dcc.Input(id='source-set', type='number', value=0),
    html.Button('Send', id='send-btn', n_clicks=0), html.Div(id='send-status')])


def start_connections():
    """Initialize socket connections and start receiver threads"""
    # Initialize connections with retry
    stream_socket.connect_with_backoff()
    ctrl_socket.connect_with_backoff()

    # Start receiver threads
    threading.Thread(target=stream_receiver, daemon=True).start()
    threading.Thread(target=ctrl_receiver, daemon=True).start()

    logger.info("Socket connections and receiver threads started")


@app.callback(Output("live-graph", "figure"), Output("connection-status", "children"),
    Input("interval", "n_intervals"), )
def update_plot(n):
    """Update the plot with the latest neutron density data retrieved from a queue."""
    neutron_vals = []
    x_vals = []

    # Get all available data points without blocking
    while not stream_data_q.empty():
        try:
            dens, rho, pos = stream_data_q.get_nowait()
            neutron_vals.append(dens)
            x_vals.append(len(neutron_vals))
            stream_data_q.task_done()
        except queue.Empty:
            break

    # Create figure (fixed from original which had a nested dcc.Graph)
    figure = {"data": [{"x": x_vals, "y": neutron_vals, "type": "line", "name": "neutron_density"}],
        "layout": {"title": "Live Neutron Density"}}

    # Connection status
    status = "Connected" if stream_socket.connected and ctrl_socket.connected else "Reconnecting..."

    return figure, status


@app.callback(Output('send-status', 'children'), Input('send-btn', 'n_clicks'), State('motor-set', 'value'),
    State('servo-set', 'value'), State('source-set', 'value'), )
def send_settings(n_clicks, motor_set, servo_set, source_set):
    """Send configuration settings via a socket connection."""
    if n_clicks > 0:
        # Input validation
        try:
            motor_val = int(motor_set) if motor_set is not None else 0
            servo_val = int(servo_set) if servo_set is not None else 0
            source_val = int(source_set) if source_set is not None else 0
        except (TypeError, ValueError) as e:
            logger.error(f"Invalid settings values: {e}")
            return "Error: Invalid values provided"

        msg = {"type": "settings", "motor_set": motor_val, "servo_set": servo_val, "source_set": source_val, }

        success = ctrl_socket.send_json(msg)
        if success:
            logger.info(f"Settings sent: {msg}")
            return "Settings sent successfully!"
        else:
            return "Failed to send settings. Check connection."
    return ""


if __name__ == "__main__":
    try:
        start_connections()
        app.run(debug=False, host='127.0.0.1')
    except KeyboardInterrupt:
        logger.info("Shutting down on keyboard interrupt...")
    finally:
        logger.info("Closing sockets...")
        stream_socket.close()
        ctrl_socket.close()
        logger.info("Application terminated")
