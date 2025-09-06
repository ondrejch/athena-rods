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
from dash import Dash, dcc, html, Input, Output, State
import queue
from arod_control import PORT_CTRL, PORT_STREAM, CONTROL_IP


stream_data_q = queue.Queue()
ctrl_status_q = queue.Queue()
stream_sock: (socket.socket, None) = None
ctrl_sock: (socket.socket, None) = None


def connect_with_retry(host, port, handshake, delay=5):
    """Connect to a server with retry logic until successful.
    Parameters:
        - host (str): The server's hostname or IP address to connect to.
        - port (int): The server's port number to connect to.
        - handshake (str): The handshake message to be sent upon connection.
        - delay (int, optional): The number of seconds to wait before retrying a failed connection attempt. Defaults to 5.
    Returns:
        - socket.socket: The connected socket object upon a successful connection."""
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            s.sendall(handshake.encode('utf-8') + b'\n')
            return s
        except Exception as e:
            print(f"Retrying connection to {handshake} on {host}:{port}. Reason: {e}")
            time.sleep(delay)


def stream_receiver(sock):
    """Receives and processes continuous data stream from a socket.
    Parameters:
        - sock (socket): A socket object from which to receive the data.
    Returns:
        - None: This function does not return anything. It processes data as it is received, unpacking and queuing it."""
    try:
        while True:
            data = sock.recv(12)
            if not data or len(data) < 12:
                break
            neutron_density, rho, position = struct.unpack('!fff', data)
            stream_data_q.put((neutron_density, rho,  position))
            print(neutron_density, rho,  position)
    except Exception as e:
        print("Stream receive error:", e)


def ctrl_receiver(sock):
    """Receives messages from a socket and updates a queue with JSON-decoded status.
    Parameters:
        - sock (socket.socket): The socket object from which to receive messages.
    Returns:
        - None: This function does not return a value; it processes incoming data continuously until the connection is closed."""
    buffer = b""
    while True:
        msg = sock.recv(1024)
        if not msg:
            break
        buffer += msg
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            try:
                ctrl_status_q.put(json.loads(line.decode('utf-8')))
            except:
                continue


app = Dash(__name__)
app.layout = html.Div([
    html.H2("Live Neutron Density"),
    dcc.Graph(id="live-graph"),
    dcc.Interval(id="interval", interval=1000, n_intervals=0),
    html.Div(id="connection-status"),
    html.H3("Send Settings"),
    dcc.Input(id='motor-set', type='number', value=0),
    dcc.Input(id='servo-set', type='number', value=0),
    dcc.Input(id='source-set', type='number', value=0),
    html.Button('Send', id='send-btn', n_clicks=0),
    html.Div(id='send-status')
])


def start_connections():
    stream_sock = connect_with_retry(CONTROL_IP, PORT_STREAM, "stream_display")
    ctrl_sock = connect_with_retry(CONTROL_IP, PORT_CTRL, "ctrl_display")
    threading.Thread(target=stream_receiver, args=(stream_sock,), daemon=True).start()
    threading.Thread(target=ctrl_receiver, args=(ctrl_sock,), daemon=True).start()


@app.callback(
    Output("live-graph", "figure"),
    Output("connection-status", "children"),
    Input("interval", "n_intervals"),
)
def update_plot(n):
    """Update the plot with the latest neutron density data retrieved from a queue.
    Parameters:
        - n (int): Not directly used in the function body.
    Returns:
        - tuple: A tuple containing the plot figure (dcc.Graph figure) updated with neutron density data and a status string indicating socket connection status."""
    neutron_vals = []
    x_vals = []
    while not stream_data_q.empty():
        dens, rho, pos = stream_data_q.get()
        neutron_vals.append(dens)
        x_vals.append(len(neutron_vals))
    fig = dcc.Graph(
        figure={
        "data": [{"x": x_vals, "y": neutron_vals, "type": "line", "name": "neutron_density"}],
        "layout": {"title": "Live Neutron Density"}
        }
    ).figure
    status = "Connected." if stream_sock and ctrl_sock else "Waiting on socket(s)…"
    return fig, status


@app.callback(
    Output('send-status', 'children'),
    Input('send-btn', 'n_clicks'),
    State('motor-set', 'value'), State('servo-set', 'value'), State('source-set', 'value'),
)
def send_settings(n_clicks, motor_set, servo_set, source_set):
    """Send configuration settings via a socket connection.
    Parameters:
        - n_clicks (int): Number of clicks to trigger sending of settings.
        - motor_set (Any): Configuration value for motor settings.
        - servo_set (Any): Configuration value for servo settings.
        - source_set (Any): Configuration value for source settings.
    Returns:
        - str: Confirmation message if settings are sent, otherwise an empty string."""
    if n_clicks > 0:
        msg = {
            "type": "settings",
            "motor_set": int(motor_set),
            "servo_set": int(servo_set),
            "source_set": int(source_set),
        }
        ctrl_sock.sendall((json.dumps(msg)+'\n').encode('utf-8'))
        return "Settings sent!"
    return ""


if __name__ == "__main__":
    try:
        start_connections()
        app.run(debug=False)
    except KeyboardInterrupt:
        print("Ctrl+C detected, closing sockets...")
        try:
            stream_sock.close()
            ctrl_sock.close()
        except Exception as e:
            print("Error closing sockets:", e)
