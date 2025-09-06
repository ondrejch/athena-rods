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
from dash import Dash, dcc, html, Input, Output, State, ctx
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
time_points = []
neutron_values = []
rho_values = []
position_values = []
max_history = 500  # Maximum number of points to store

# Value bounds for validation
VALUE_BOUNDS = {
    "neutron": (-1.0, 1000.0),      # Expected neutron density range
    "rho": (-0.01, 0.01),           # Expected reactivity range
    "position": (0.0, 30.0)         # Expected position range in cm
}


def is_value_reasonable(name, value):
    """Check if a value is within reasonable bounds"""
    if name not in VALUE_BOUNDS:
        return True  # No bounds defined, accept any value
        
    min_val, max_val = VALUE_BOUNDS[name]
    return min_val <= value <= max_val and isinstance(value, (int, float))


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

            try:
                neutron_density, rho, position = StreamingPacket.unpack_float_triplet(data)
                
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

                counter += 1
                if counter % 100 == 0:
                    logger.info(f"Stream data: n={neutron_density:.2f}, rho={rho:.6f}, pos={position:.2f}")
                    
                # Only queue valid data points
                stream_data_q.put_nowait((neutron_density, rho, position))
                
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


# Dashboard layout
app = Dash(__name__)

app.layout = html.Div([
    html.H1("ATHENA Rods Visualization"),

    # Control bar
    html.Div([
        html.Button('Clear Plots', id='reset-btn', n_clicks=0,
                   style={'margin-right': '20px', 'background-color': '#f44336', 'color': 'white'}),
        html.Div(id="connection-status", 
                style={'display': 'inline-block', 'margin': '10px', 'padding': '10px', 
                       'border': '1px solid #ddd', 'min-width': '200px'}),
    ], style={'margin-bottom': '20px'}),

    # First row: Neutron density graph and rod position
    html.Div([
        html.Div([
            html.H2("Live Neutron Density"), 
            dcc.Graph(id="neutron-graph"),
        ], className='six columns'),

        html.Div([
            html.H2("Control Rod Position"), 
            dcc.Graph(id="position-graph"),
        ], className='six columns'),
    ], className='row'),

    # Second row: Reactivity graph and controls
    html.Div([
        html.Div([
            html.H2("Reactivity"), 
            dcc.Graph(id="reactivity-graph"),
        ], className='six columns'),

        html.Div([
            html.H3("Control Settings"), 
            html.Div([
                html.Label("Motor Control:"), 
                dcc.RadioItems(id='motor-set',
                    options=[
                        {'label': 'Down (-1)', 'value': -1}, 
                        {'label': 'Stop (0)', 'value': 0},
                        {'label': 'Up (1)', 'value': 1},
                    ], value=0, inline=True),
            ]),
            html.Div([
                html.Label("Servo Control:"), 
                dcc.RadioItems(id='servo-set',
                    options=[
                        {'label': 'Disengage (0)', 'value': 0}, 
                        {'label': 'Engage (1)', 'value': 1},
                    ], value=1, inline=True),
            ]),
            html.Div([
                html.Label("Source Control:"), 
                dcc.RadioItems(id='source-set',
                    options=[
                        {'label': 'Off (0)', 'value': 0}, 
                        {'label': 'On (1)', 'value': 1},
                    ], value=0, inline=True),
            ]),
            html.Button('Send', id='send-btn', n_clicks=0,
                        style={'margin-top': '20px', 'background-color': '#4CAF50', 'color': 'white'}),
            html.Div(id='send-status')
        ], className='six columns'),
    ], className='row'),

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


def format_time():
    """Get current time formatted for display"""
    return datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]


@app.callback(
    [Output("neutron-graph", "figure"), 
     Output("position-graph", "figure"), 
     Output("reactivity-graph", "figure"),
     Output("connection-status", "children"), 
     Output("connection-status", "style")],
    [Input("interval", "n_intervals"),
     Input("reset-btn", "n_clicks")]
)
def update_plots(n_intervals, reset_clicks):
    """Update all plots with the latest data retrieved from queues"""
    global time_points, neutron_values, rho_values, position_values
    
    # Check if reset button was clicked
    if ctx.triggered_id == "reset-btn":
        time_points = []
        neutron_values = []
        rho_values = []
        position_values = []
        logger.info("Plots cleared by user")
    
    # Process all available data from the queue
    new_data_count = 0
    current_time = format_time()
    
    while not stream_data_q.empty() and new_data_count < 10:
        try:
            density, rho, position = stream_data_q.get_nowait()
            
            # Add to our data lists
            time_points.append(current_time)
            neutron_values.append(density)
            rho_values.append(rho)
            position_values.append(position)
            
            # Limit the number of points we keep
            if len(time_points) > max_history:
                time_points = time_points[-max_history:]
                neutron_values = neutron_values[-max_history:]
                rho_values = rho_values[-max_history:]
                position_values = position_values[-max_history:]
            
            stream_data_q.task_done()
            new_data_count += 1
            
        except queue.Empty:
            break
        except Exception as e:
            logger.error(f"Error processing data point: {e}")
            break
    
    # Create default empty figures
    neutron_fig = {
        'data': [],
        'layout': {
            'title': 'Live Neutron Density',
            'xaxis': {'title': 'Time'},
            'yaxis': {'title': 'Neutron Density'},
            'margin': {'l': 50, 'r': 50, 'b': 50, 't': 50}
        }
    }
    
    position_fig = {
        'data': [],
        'layout': {
            'title': 'Control Rod Position',
            'xaxis': {'title': 'Time'},
            'yaxis': {'title': 'Position (cm)'},
            'margin': {'l': 50, 'r': 50, 'b': 50, 't': 50}
        }
    }
    
    reactivity_fig = {
        'data': [],
        'layout': {
            'title': 'Reactivity',
            'xaxis': {'title': 'Time'},
            'yaxis': {'title': 'Reactivity (ρ)'},
            'margin': {'l': 50, 'r': 50, 'b': 50, 't': 50}
        }
    }
    
    # Add data if available
    if time_points:
        neutron_fig['data'] = [go.Scatter(
            x=time_points,
            y=neutron_values,
            mode='lines',
            name='Neutron Density',
            line={'color': 'blue', 'width': 2}
        )]
        
        position_fig['data'] = [go.Scatter(
            x=time_points,
            y=position_values,
            mode='lines',
            name='Rod Position',
            line={'color': 'green', 'width': 2}
        )]
        
        reactivity_fig['data'] = [go.Scatter(
            x=time_points,
            y=rho_values,
            mode='lines',
            name='Reactivity',
            line={'color': 'red', 'width': 2}
        )]
    
    # Connection status
    now = datetime.datetime.now().strftime('%H:%M:%S')
    if stream_socket.connected and ctrl_socket.connected:
        status = f"✓ Connected to control box at {now}"
        status_style = {
            'display': 'inline-block',
            'margin': '10px',
            'padding': '10px',
            'border': '1px solid #ddd',
            'backgroundColor': '#dff0d8',
            'color': '#3c763d'
        }
    else:
        status = f"⚠ Reconnecting to control box... ({now})"
        status_style = {
            'display': 'inline-block',
            'margin': '10px',
            'padding': '10px',
            'border': '1px solid #ddd',
            'backgroundColor': '#fcf8e3',
            'color': '#8a6d3b'
        }
    
    return neutron_fig, position_fig, reactivity_fig, status, status_style


@app.callback(
    Output('send-status', 'children'),
    [Input('send-btn', 'n_clicks')],
    [State('motor-set', 'value'),
     State('servo-set', 'value'),
     State('source-set', 'value')],
)
def send_settings(n_clicks, motor_set, servo_set, source_set):
    """Send configuration settings via a socket connection."""
    if not n_clicks or n_clicks <= 0:
        return ""
    
    # Input validation
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
    
    logger.info(f"Sending settings: {msg}")
    success = ctrl_socket.send_json(msg)
    
    if success:
        logger.info(f"Settings sent successfully")
        return html.Div("Settings sent successfully!", style={'color': 'green'})
    else:
        logger.warning("Failed to send settings")
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
