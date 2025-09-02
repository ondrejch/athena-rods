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


def connect_with_retry(host, port, handshake, delay=5):
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
    try:
        while True:
            data = sock.recv(8)
            if not data or len(data) < 8:
                break
            neutron_density, position = struct.unpack('!ff', data)
            stream_data_q.put((neutron_density, position))
    except Exception as e:
        print("Stream receive error:", e)


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
    global stream_sock, ctrl_sock
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
    neutron_vals = []
    x_vals = []
    while not stream_data_q.empty():
        dens, pos = stream_data_q.get()
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
    start_connections()
    app.run_server(debug=False)
