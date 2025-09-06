#!/usr/bin/env python3
"""
Main loop for the external visualization and control of ATHENA-rods
Ondrej Chvala <ochvala@utexas.edu>
"""

import logging
import threading
import time
import queue
import datetime
import json
from typing import List

from dash import Dash, dcc, html, Input, Output, State, no_update, ctx
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
time_points: List[datetime.datetime] = []
neutron_values: List[float] = []
rho_values: List[float] = []
position_values: List[float] = []
max_history = 5000  # Maximum number of points to store

# Value bounds for validation
VALUE_BOUNDS = {
    "neutron": (-1.0, 1e38),    # Expected neutron density range
    "rho": (-1.0, 1.0),         # Expected reactivity range
    "position": (0.0, 60.0)     # Expected position range in cm
}

# Store global application state
app_state = {
    "reset_count": 0,
    "connection_status": "Initializing...",
    "last_update": datetime.datetime.now().strftime('%H:%M:%S')
}

# --- Styles ---
CARD_STYLE = {
    'border': '1px solid #e0e0e0',
    'borderRadius': '10px',
    'boxShadow': '0 2px 8px rgba(0, 0, 0, 0.08)',
    'padding': '15px',
    'backgroundColor': '#ffffff',
    'marginBottom': '20px'
}

SECTION_TITLE_STYLE = {
    'margin': '0 0 10px 0',
    'padding': '5px 0',
    'borderBottom': '1px solid #eee'
}

SLIDER_STYLE = {
    'marginTop': '10px',
    'marginBottom': '20px'
}

# --- Helpers ---

def is_value_reasonable(name, value):
    """Check if a value is within reasonable bounds"""
    if name not in VALUE_BOUNDS:
        return True  # No bounds defined, accept any value
    min_val, max_val = VALUE_BOUNDS[name]
    return min_val <= value <= max_val and isinstance(value, (int, float))


def moving_average(values: List[float], window: int = 20) -> List[float]:
    """Simple trailing moving average used as a trend line."""
    if not values:
        return []
    window = max(1, window)
    result: List[float] = []
    s = 0.0
    q: List[float] = []
    for v in values:
        q.append(v)
        s += v
        if len(q) > window:
            s -= q.pop(0)
        result.append(s / len(q))
    return result


def stream_receiver():
    """Receives and processes continuous data stream from a socket."""
    counter = 0
    while True:
        try:
            # Receive exactly 16 bytes (4 floats: neutron, rho, position, timestamp_ms)
            data, success = stream_socket.receive_exactly(StreamingPacket.PACKET_SIZE_QUAD)
            if not success:
                logger.debug("No data received, waiting...")
                time.sleep(0.5)
                continue

            try:
                neutron_density, rho, position, ts_ms = StreamingPacket.unpack_float_quad(data)

                # Validate data before adding to queue
                if not is_value_reasonable("neutron", neutron_density):
                    logger.warning(f"Ignoring unreasonable neutron density: {neutron_density}")
                    continue

                if not is_value_reasonable("rho", rho):
                    logger.warning(f"Ignoring unreasonable reactivity: {rho}")
                    continue

                if not is_value_reasonable("position", position):
                    logger.warning(f"Ignoring unreasonable position: {position}")
                    continue

                # Convert timestamp_ms to datetime (UTC)
                try:
                    dt = datetime.datetime.utcfromtimestamp(ts_ms / 1000.0)
                except (OverflowError, OSError, ValueError):
                    dt = datetime.datetime.utcnow()

                counter += 1
                if counter % 100 == 0:
                    logger.info(f"Stream data: t={dt.isoformat()}Z, n={neutron_density:.2f}, rho={rho:.6f}, pos={position:.2f}")

                # Only queue valid data points (include timestamp)
                try:
                    stream_data_q.put_nowait((neutron_density, rho, position, dt))
                except queue.Full:
                    # Make room by removing oldest item
                    try:
                        stream_data_q.get_nowait()
                        stream_data_q.put_nowait((neutron_density, rho, position, dt))
                    except (queue.Empty, queue.Full):
                        pass

            except Exception as e:
                logger.error(f"Error processing stream data: {e}")
                time.sleep(0.1)

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


# Create default empty figures to ensure consistent initialization
def create_empty_figure(title, y_axis_title):
    return {
        'data': [],
        'layout': {
            'title': {'text': title, 'font': {'size': 22}},
            'xaxis': {
                'title': {'text': 'Time (UTC)', 'font': {'size': 18}},
                'type': 'date',
                'tickfont': {'size': 14},
                'gridcolor': '#f0f0f0',
                'zerolinecolor': '#e6e6e6'
            },
            'yaxis': {
                'title': {'text': y_axis_title, 'font': {'size': 18}},
                'tickfont': {'size': 14},
                'gridcolor': '#f0f0f0',
                'zerolinecolor': '#e6e6e6'
            },
            'margin': {'l': 60, 'r': 30, 'b': 60, 't': 60},
            'paper_bgcolor': '#ffffff',
            'plot_bgcolor': '#ffffff',
            'legend': {'font': {'size': 14}}
        }
    }


# Initialize app with configuration to handle callback exceptions
app = Dash(__name__)
app.config.suppress_callback_exceptions = True

# Dashboard layout with pre-initialized components
app.layout = html.Div([
    html.H1("ATHENA Rods Visualization"),

    # Control bar
    html.Div([
        html.Button(
            'Clear Plots',
            id='reset-btn',
            n_clicks=0,
            style={'margin-right': '20px', 'background-color': '#f44336', 'color': 'white', 'border': 'none',
                   'padding': '10px 16px', 'borderRadius': '6px', 'cursor': 'pointer'}
        ),
        html.Div(
            "Connecting to control box...", id="connection-status",
            style={'display': 'inline-block', 'margin': '10px', 'padding': '10px',
                   'border': '1px solid #ddd', 'min-width': '260px', 'borderRadius': '6px'}
        ),
    ], style={'margin-bottom': '20px'}),

    # First row: Neutron density graph and rod position
    html.Div([
        html.Div([
            html.H2("Live Neutron Density", style=SECTION_TITLE_STYLE),
            html.Div([
                dcc.Graph(id="neutron-graph", figure=create_empty_figure("Live Neutron Density", "Neutron Density")),
            ], style=CARD_STYLE),
        ], className='six columns', style={'paddingRight': '10px'}),

        html.Div([
            html.H2("Control Rod Position", style=SECTION_TITLE_STYLE),
            html.Div([
                dcc.Graph(id="position-graph", figure=create_empty_figure("Control Rod Position", "Position (cm)")),
            ], style=CARD_STYLE),
        ], className='six columns', style={'paddingLeft': '10px'}),
    ], className='row'),

    # Second row: Reactivity graph and controls
    html.Div([
        html.Div([
            html.H2("Reactivity", style=SECTION_TITLE_STYLE),
            html.Div([
                dcc.Graph(id="reactivity-graph", figure=create_empty_figure("Reactivity", "Reactivity (ρ)")),
            ], style=CARD_STYLE),
        ], className='six columns', style={'paddingRight': '10px'}),

        html.Div([
            html.H3("Control Settings", style=SECTION_TITLE_STYLE),

            html.Div([
                html.Label("Motor Control (3-position switch):"),
                dcc.Slider(
                    id='motor-set',
                    min=-1, max=1, step=1, value=0,
                    marks={-1: {'label': 'Down (-1)'}, 0: {'label': 'Stop (0)'}, 1: {'label': 'Up (1)'}},
                    updatemode='mouseup',
                    tooltip={'always_visible': False, 'placement': 'bottom'}
                ),
            ], style=SLIDER_STYLE),

            html.Div([
                html.Label("Servo Control:"),
                dcc.Slider(
                    id='servo-set',
                    min=0, max=1, step=1, value=1,
                    marks={0: {'label': 'Disengage (0)'}, 1: {'label': 'Engage (1)'}},
                    updatemode='mouseup',
                    tooltip={'always_visible': False, 'placement': 'bottom'}
                ),
            ], style=SLIDER_STYLE),

            html.Div([
                html.Label("Source Control:"),
                dcc.Slider(
                    id='source-set',
                    min=0, max=1, step=1, value=0,
                    marks={0: {'label': 'Off (0)'}, 1: {'label': 'On (1)'}},
                    updatemode='mouseup',
                    tooltip={'always_visible': False, 'placement': 'bottom'}
                ),
            ], style=SLIDER_STYLE),

            html.Div(id='send-status', style={'minHeight': '24px', 'marginTop': '10px'}),
        ], className='six columns', style={'paddingLeft': '10px', **CARD_STYLE}),
    ], className='row'),

    # Hidden div for storing intermediate state
    html.Div(id='app-state', style={'display': 'none'}),

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


# First callback to manage application state
@app.callback(
    Output('app-state', 'children'),
    [Input("interval", "n_intervals"),
     Input("reset-btn", "n_clicks")]
)
def update_app_state(n_intervals, reset_clicks):
    """Update the application state and process incoming data"""
    global app_state, time_points, neutron_values, rho_values, position_values

    # Update connection status
    now = datetime.datetime.now().strftime('%H:%M:%S')
    app_state['last_update'] = now

    if stream_socket.connected and ctrl_socket.connected:
        app_state['connection_status'] = f"✓ Connected to control box at {now}"
    else:
        app_state['connection_status'] = f"⚠ Reconnecting to control box... ({now})"

    # Check if reset button was clicked (compare with stored value)
    reset_clicks = reset_clicks or 0
    if reset_clicks > app_state.get('reset_count', 0):
        app_state['reset_count'] = reset_clicks
        time_points = []
        neutron_values = []
        rho_values = []
        position_values = []
        logger.info("Plots cleared by user")

    # Process data from queue
    new_data_count = 0

    while not stream_data_q.empty() and new_data_count < 10:
        try:
            # Get data point from queue (now includes dt)
            density, rho, position, dt = stream_data_q.get_nowait()

            # Add timestamp and data to our lists
            time_points.append(dt)
            neutron_values.append(density)
            rho_values.append(rho)
            position_values.append(position)

            # Enforce maximum history length
            if len(time_points) > max_history:
                time_points = time_points[-max_history:]
                neutron_values = neutron_values[-max_history:]
                rho_values = rho_values[-max_history:]
                position_values = position_values[-max_history:]

            stream_data_q.task_done()
            new_data_count += 1

        except queue.Empty:
            break  # No more data in queue
        except Exception as e:
            logger.error(f"Error processing data point: {e}")
            break  # Stop processing on error

    # Return the current state serialized as JSON (meta only)
    try:
        return json.dumps({
            'reset_count': app_state['reset_count'],
            'connection_status': app_state['connection_status'],
            'last_update': app_state['last_update'],
            'data_count': len(time_points)
        })
    except Exception as e:
        logger.error(f"Error serializing app state: {e}")
        return json.dumps({'error': str(e)})


# Second callback to update UI elements based on app state
@app.callback(
    [Output("neutron-graph", "figure"),
     Output("position-graph", "figure"),
     Output("reactivity-graph", "figure"),
     Output("connection-status", "children"),
     Output("connection-status", "style")],
    [Input('app-state', 'children')]
)
def update_plots(app_state_json):
    """Update all plots with the latest data (points + semi-transparent dashed trend line)"""
    global time_points, neutron_values, rho_values, position_values

    try:
        # Parse app state
        state = json.loads(app_state_json) if app_state_json else {}

        # Create default empty figures
        neutron_fig = create_empty_figure("Live Neutron Density", "Neutron Density")
        position_fig = create_empty_figure("Control Rod Position", "Position (cm)")
        reactivity_fig = create_empty_figure("Reactivity", "Reactivity (ρ)")

        # Add data if available
        if time_points:
            # Trend lines
            n_trend = moving_average(neutron_values, window=20)
            p_trend = moving_average(position_values, window=20)
            r_trend = moving_average(rho_values, window=20)

            # Neutron
            neutron_fig['data'] = [
                go.Scatter(
                    x=time_points,
                    y=neutron_values,
                    mode='markers',
                    name='Neutron Density (points)',
                    marker={'color': 'rgba(33, 150, 243, 0.9)', 'size': 5},
                ),
                go.Scatter(
                    x=time_points,
                    y=n_trend,
                    mode='lines',
                    name='Trend',
                    line={'color': 'rgba(33, 150, 243, 1.0)', 'width': 2, 'dash': 'dash'},
                    opacity=0.5
                )
            ]

            # Position
            position_fig['data'] = [
                go.Scatter(
                    x=time_points,
                    y=position_values,
                    mode='markers',
                    name='Rod Position (points)',
                    marker={'color': 'rgba(76, 175, 80, 0.9)', 'size': 5},
                ),
                go.Scatter(
                    x=time_points,
                    y=p_trend,
                    mode='lines',
                    name='Trend',
                    line={'color': 'rgba(76, 175, 80, 1.0)', 'width': 2, 'dash': 'dash'},
                    opacity=0.5
                )
            ]

            # Reactivity
            reactivity_fig['data'] = [
                go.Scatter(
                    x=time_points,
                    y=rho_values,
                    mode='markers',
                    name='Reactivity (points)',
                    marker={'color': 'rgba(244, 67, 54, 0.9)', 'size': 5},
                ),
                go.Scatter(
                    x=time_points,
                    y=r_trend,
                    mode='lines',
                    name='Trend',
                    line={'color': 'rgba(244, 67, 54, 1.0)', 'width': 2, 'dash': 'dash'},
                    opacity=0.5
                )
            ]

        # Set connection status and style
        connection_status = state.get('connection_status', "Checking connection...")

        if "✓ Connected" in connection_status:
            status_style = {
                'display': 'inline-block',
                'margin': '10px',
                'padding': '10px',
                'border': '1px solid #ddd',
                'backgroundColor': '#dff0d8',
                'color': '#3c763d',
                'borderRadius': '6px'
            }
        else:
            status_style = {
                'display': 'inline-block',
                'margin': '10px',
                'padding': '10px',
                'border': '1px solid #ddd',
                'backgroundColor': '#fcf8e3',
                'color': '#8a6d3b',
                'borderRadius': '6px'
            }

        return neutron_fig, position_fig, reactivity_fig, connection_status, status_style

    except Exception as e:
        logger.error(f"Error updating plots: {e}")
        # Return no_update for all outputs to maintain previous state
        return no_update, no_update, no_update, no_update, no_update


# Send settings automatically when controls change (no extra button)
@app.callback(
    Output('send-status', 'children'),
    [Input('motor-set', 'value'),
     Input('servo-set', 'value'),
     Input('source-set', 'value')],
    prevent_initial_call=True
)
def send_settings_on_change(motor_set, servo_set, source_set):
    """Send configuration settings whenever any control changes."""
    # Validate and sanitize inputs
    try:
        motor_val = int(motor_set) if motor_set is not None else 0
        servo_val = int(servo_set) if servo_set is not None else 1  # Default to engaged for safety
        source_val = int(source_set) if source_set is not None else 0
    except (TypeError, ValueError) as e:
        logger.error(f"Invalid settings values: {e}")
        return html.Div("Error: Invalid values provided", style={'color': 'red'})

    msg = {
        "type": "settings",
        "motor_set": motor_val,
        "servo_set": servo_val,
        "source_set": source_val
    }

    changed = ctx.triggered_id  # Which control triggered
    logger.info(f"Control changed ({changed}), sending settings: {msg}")
    success = ctrl_socket.send_json(msg)

    if success:
        return html.Div(f"Settings applied (motor={motor_val}, servo={servo_val}, source={source_val})",
                        style={'color': 'green'})
    else:
        return html.Div("Failed to send settings. Check connection.", style={'color': 'red'})


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
        logger.error(f"Unhandled exception: {type(e).__name__}: {e}", exc_info=True)
    finally:
        # Clean shutdown
        logger.info("Closing sockets...")
        stream_socket.close()
        ctrl_socket.close()
        logger.info("Application terminated")
