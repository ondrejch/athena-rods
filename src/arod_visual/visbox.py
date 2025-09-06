#!/usr/bin/env python3
"""
Main loop for the external visualization and control of ATHENA-rods
Ondrej Chvala <ochvala@utexas.edu>
"""

import logging
import threading
import time
import queue
from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objs as go
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

# History storage for plotting
neutron_history = []
time_history = []
rho_history = []
position_history = []
max_history = 100  # Maximum number of points to store


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
            try:
                neutron_density, rho, position = StreamingPacket.unpack_float_triplet(data)
            except ValueError as e:
                logger.error(f"Error unpacking stream data: {e}")
                continue

            # Validate data before adding to queue
            if not all(isinstance(x, float) for x in [neutron_density, rho, position]):
                logger.warning(f"Invalid data types in stream: {neutron_density}, {rho}, {position}")
                continue

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
            logger.error(f"Stream receiver error: {type(e).__name__}: {e}")
            time.sleep(1)


def ctrl_receiver():
    """Receives messages from a socket and updates a queue with JSON-decoded status."""
    while True:
        try:
            data, success = ctrl_socket.receive_json()
            if success and data:
                logger.debug(f"Received control data: {data}")
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
                time.sleep(0.2)  # Wait before retrying
        except Exception as e:
            logger.error(f"Control receiver error: {type(e).__name__}: {e}")
            time.sleep(1)


# Dashboard layout
app = Dash(__name__)
app.layout = html.Div([html.H1("ATHENA Rods Visualization"),

    # First row: Neutron density graph
    html.Div([html.Div([html.H2("Live Neutron Density"), dcc.Graph(id="neutron-graph"), ], className='six columns'),

        html.Div([html.H2("Control Rod Position"), dcc.Graph(id="position-graph"), ], className='six columns'), ],
        className='row'),

    # Second row: Reactivity graph and controls
    html.Div([html.Div([html.H2("Reactivity"), dcc.Graph(id="reactivity-graph"), ], className='six columns'),

        html.Div([html.H3("Control Settings"), html.Div([html.Label("Motor Control:"), dcc.RadioItems(id='motor-set',
            options=[{'label': 'Down (-1)', 'value': -1}, {'label': 'Stop (0)', 'value': 0},
                {'label': 'Up (1)', 'value': 1}, ], value=0, inline=True), ]), html.Div([html.Label("Servo Control:"),
            dcc.RadioItems(id='servo-set',
                options=[{'label': 'Disengage (0)', 'value': 0}, {'label': 'Engage (1)', 'value': 1}, ], value=0,
                inline=True), ]), html.Div([html.Label("Source Control:"), dcc.RadioItems(id='source-set',
            options=[{'label': 'Off (0)', 'value': 0}, {'label': 'On (1)', 'value': 1}, ], value=0, inline=True), ]),
            html.Button('Send', id='send-btn', n_clicks=0,
                        style={'margin-top': '20px', 'background-color': '#4CAF50', 'color': 'white'}),
            html.Div(id='send-status')], className='six columns'), ], className='row'),

    # Status row
    html.Div(
        [html.Div(id="connection-status", style={'margin': '10px', 'padding': '10px', 'border': '1px solid #ddd'}), ],
        className='row'),

    # Update interval
    dcc.Interval(id="interval", interval=500, n_intervals=0),

], style={'padding': '20px', 'fontFamily': 'Arial'})


def start_connections():
    """Initialize socket connections and start receiver threads"""
    # Initialize connections with retry
    logger.info("Starting connections to control box...")
    stream_socket.connect_with_backoff()
    ctrl_socket.connect_with_backoff()

    # Start receiver threads
    threading.Thread(target=stream_receiver, daemon=True).start()
    threading.Thread(target=ctrl_receiver, daemon=True).start()

    logger.info("Socket connections and receiver threads started")


@app.callback(
    [Output("neutron-graph", "figure"), Output("position-graph", "figure"), Output("reactivity-graph", "figure"),
        Output("connection-status", "children"), Output("connection-status", "style")],
    Input("interval", "n_intervals"), )
def update_plots(n):
    """Update all plots with the latest data retrieved from queues"""
    global neutron_history, time_history, rho_history, position_history

    # Get all available data points without blocking
    data_count = 0
    while not stream_data_q.empty() and data_count < 10:  # Process up to 10 points at a time
        try:
            dens, rho, pos = stream_data_q.get_nowait()

            # Update history lists
            current_time = time.time()
            neutron_history.append(dens)
            rho_history.append(rho)
            position_history.append(pos)
            time_history.append(current_time)

            # Trim history if it gets too long
            if len(neutron_history) > max_history:
                neutron_history = neutron_history[-max_history:]
                rho_history = rho_history[-max_history:]
                position_history = position_history[-max_history:]
                time_history = time_history[-max_history:]

            stream_data_q.task_done()
            data_count += 1
        except queue.Empty:
            break

    # Create relative time values for x-axis (seconds from start)
    if time_history:
        rel_times = [(t - time_history[0]) for t in time_history]
    else:
        rel_times = []

    # Create neutron density figure
    neutron_fig = {'data': [go.Scatter(x=rel_times, y=neutron_history, mode='lines+markers', name='Neutron Density',
        line={'color': 'blue', 'width': 2})],
        'layout': {'title': 'Live Neutron Density', 'xaxis': {'title': 'Time (seconds)'},
            'yaxis': {'title': 'Neutron Density'}, 'margin': {'l': 50, 'r': 50, 'b': 50, 't': 50}}}

    # Create position figure
    position_fig = {'data': [go.Scatter(x=rel_times, y=position_history, mode='lines+markers', name='Rod Position',
        line={'color': 'green', 'width': 2})],
        'layout': {'title': 'Control Rod Position', 'xaxis': {'title': 'Time (seconds)'},
            'yaxis': {'title': 'Position (cm)'}, 'margin': {'l': 50, 'r': 50, 'b': 50, 't': 50}}}

    # Create reactivity figure
    reactivity_fig = {'data': [go.Scatter(x=rel_times, y=rho_history, mode='lines+markers', name='Reactivity',
        line={'color': 'red', 'width': 2})],
        'layout': {'title': 'Reactivity', 'xaxis': {'title': 'Time (seconds)'}, 'yaxis': {'title': 'Reactivity (ρ)'},
            'margin': {'l': 50, 'r': 50, 'b': 50, 't': 50}}}

    # Connection status
    if stream_socket.connected and ctrl_socket.connected:
        status = "✓ Connected to control box"
        status_style = {'margin': '10px', 'padding': '10px', 'border': '1px solid #ddd', 'backgroundColor': '#dff0d8',
            'color': '#3c763d'}
    else:
        status = "⚠ Reconnecting to control box..."
        status_style = {'margin': '10px', 'padding': '10px', 'border': '1px solid #ddd', 'backgroundColor': '#fcf8e3',
            'color': '#8a6d3b'}

    return neutron_fig, position_fig, reactivity_fig, status, status_style


@app.callback(Output('send-status', 'children'), Input('send-btn', 'n_clicks'),
    [State('motor-set', 'value'), State('servo-set', 'value'), State('source-set', 'value')], )
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
            return html.Div("Error: Invalid values provided", style={'color': 'red'})

        msg = {"type": "settings", "motor_set": motor_val, "servo_set": servo_val, "source_set": source_val}

        logger.info(f"Sending settings: {msg}")
        success = ctrl_socket.send_json(msg)

        if success:
            logger.info(f"Settings sent successfully")
            return html.Div("Settings sent successfully!", style={'color': 'green'})
        else:
            logger.warning("Failed to send settings")
            return html.Div("Failed to send settings. Check connection.", style={'color': 'red'})

    return ""


if __name__ == "__main__":
    try:
        # Start socket connections
        start_connections()

        # Run the dashboard application
        logger.info("Starting Dash application...")
        app.run(debug=False, host='127.0.0.1', port=8050)
    except KeyboardInterrupt:
        logger.info("Shutting down on keyboard interrupt...")
    except Exception as e:
        logger.error(f"Unhandled exception: {type(e).__name__}: {e}")
    finally:
        # Clean shutdown
        logger.info("Closing sockets...")
        stream_socket.close()
        ctrl_socket.close()
        logger.info("Application terminated")
