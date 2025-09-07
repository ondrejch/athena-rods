# ATHENA-rods
Automated Teaching Hardware for Explaining Nuclear Absorption Rod(s)

ATHENA-rods is a hands-on teaching platform built around two Raspberry Pi 5 units and a small visualization app. It demonstrates how a reactor’s neutron population responds to control-rod motion using a real-time Point Kinetics Equation (PKE) simulation, live sensors, actuators, and simple displays.

- Instrument Box (RPi5): motor + servo moving a physical “control rod,” ultrasonic distance sensor, limit switch, and an 8×8 MAX7219 LED matrix. 
It also calibrates the ultrasonic ranging by adjusting the speed of sound using temperature and humidity from a DHT11 sensor.
- Control Box (RPi5): LCD1602 display, status LEDs, camera-based face recognition and RFID authorization.
- Visualization Box (any computer, or the Control Box): a Dash web app for live plots and sending control commands.

Most of the code is MIT-licensed unless otherwise noted.

---

## Repository layout

```
athena-rods/
├─ hardware/                         # 3D models (FreeCAD + STL) and assembly docs
│  ├─ arod_instrument/               # Instrument tower and slider mechanics
│  └─ arod_control/                  # Control box mounts (RFID, Camera+LCD)
├─ examples/                         # Small example scripts (RFID, face auth, instrument demos)
├─ src/
│  ├─ arod_instrument/               # Instrument Box runtime
│  │  ├─ instbox.py                  # Main loop: sensors, motor/servo, LED matrix, PKE
│  │  ├─ devices.py                  # GPIO bindings, Motor subclass (status/Condition)
│  │  ├─ matrixled.py                # LED matrix primitives
│  │  ├─ pke.py                      # ReactorPowerCalculator thread (real-time PKE)
│  │  └─ solver.py                   # General PKE solver (SciPy RK45)
│  ├─ arod_control/                  # Control Box runtime
│  │  ├─ ctrlbox.py                  # Main loop: auth, LCD, LEDs, sockets (hub)
│  │  ├─ authorization.py            # Face + RFID authorization
│  │  ├─ display.py, leds.py, LCD1602.py, hwsens.py
│  │  └─ socket_utils.py             # Socket helpers and StreamingPacket formats
│  ├─ arod_visual/
│  │  └─ visbox.py                   # Dash app for live plots and controls
│  └─ mfrc522/                       # Local MFRC522 driver (for RFID)
├─ requirements.txt
├─ setup.py                          # Python packaging (src layout)
├─ setup.sh                          # Optional system setup script (RPi)
└─ LICENSE
```

Hardware build instructions and models:
- See hardware/README.md
- Camera + LCD bracket details: hardware/arod_control/Camera_LCD/README.md
- Assembly image: hardware/arod_instrument/assembly-main_components.png

---

## What it does

- Reads rod position with an ultrasonic sensor and converts it to reactivity.
- Calibrates ultrasonic distance in real time by computing the speed of sound from DHT11 temperature and humidity (or onboard RPi5 iio readings) and updating the sonar accordingly.
- Runs a real-time PKE simulation to compute neutron density.
- Streams telemetry (neutron density, reactivity, position, timestamp) to the Control/Visualization box.
- Displays motion and position on an 8×8 LED matrix; animates an “explosion” when power exceeds a threshold and resets the simulation.
- Enforces safety: limit switch stop, and a watchdog thread that prevents overextension.
- Operator authorization using face recognition and RFID.

---

## Hardware (summary)

Instrument Box (RPi5):
- Ultrasonic DistanceSensor: trigger BCM 23, echo BCM 24
- DHT11 temperature/humidity sensor for speed-of-sound calibration
- DC Motor (H-bridge): forward BCM 17, backward BCM 27, enable BCM 22
- Limit switch: Button on BCM 20 (immediate motor stop on press)
- Angular servo: BCM 15 (pulse widths set in code)
- MAX7219 8×8 LED matrix on SPI0 (rotate=1), low contrast

Control Box (RPi5):
- LCD1602 I2C display (auto-detect 0x27/0x3f)
- 3 status LEDs (GPIOs in src/arod_control/leds.py)
- RPi camera for face recognition
- MFRC522 RFID reader (SPI/I2C per driver variant)

Full hardware details and printable parts are in the hardware/ directory.

---

## Installation

On each Raspberry Pi (or your dev machine where applicable):

1) System packages (examples, adjust as needed):
```bash
sudo apt update
sudo apt install -y python3-pip python3-numpy python3-scipy python3-opencv \
    python3-gpiozero python3-smbus lm-sensors \
    libopenblas0 libatlas-base-dev libcap-dev
# Optional for face_recognition (may require cmake, dlib, etc.)
# sudo apt install -y cmake build-essential
```

2) Enable interfaces (on RPis):
- raspi-config → Interface Options:
  - Enable SPI (for MAX7219 LED and MFRC522 variants)
  - Enable I2C (for LCD1602)
  - Enable Camera (for face auth)

3) Python dependencies:
```bash
pip3 install -r requirements.txt
# or editable install
pip3 install -e .
```

4) Optional helper:
```bash
# If provided, to install additional system deps:
sudo ./setup.sh
```

---

## Configuration

Socket endpoints are defined in arod_control/__init__.py:
- CONTROL_IP: IP address of the Control Box (hub/server)
- PORT_STREAM and PORT_CTRL: stream/control TCP ports

Other parameters:
- Instrument Box: src/arod_instrument/instbox.py
  - MAX_ROD_DISTANCE (default 17.0 cm)
  - SOURCE_STRENGTH for the external neutron source
  - Logging to ATHENA_instrument.log
  - update_speed_of_sound thread: uses get_dht() to read DHT11 temperature/humidity and sets sonar.speed_of_sound
- Control Box: src/arod_control/ctrlbox.py
  - FAKE_FACE_AUTH to bypass camera auth during development
  - APPROVED_USER_NAMES list
  - Logging to ATHENA_controller.log
- Visualization Box: src/arod_visual/visbox.py
  - Dash server default: http://127.0.0.1:8050, logs to visbox.log

Authorization assets:
- Face encodings pickle expected at ~/app/etc/face_rec_encodings.pickle
- CA chain fingerprint text at ~/app/etc/ca-chain.txt
- MFRC522 storage and block map handled in authorization.py

---

## Authorization and security (RFID + CA certificate fingerprint)

Two-factor authorization checks user's identity via face scanning, and the content of RFID tag. 
RFID authorization is implemented in src/arod_control/authorization.py. 
It uses a “something you have” (the RFID tag) tied to a secret derived from a CA certificate fingerprint. The design avoids storing plain tag IDs or shared secrets on the tag.

- Fingerprint source:
  - File: ~/app/etc/ca-chain.txt
  - Content: a colon-separated hex fingerprint (e.g., from an X.509 CA certificate), parsed as a big-endian integer.

- Deriving the tag’s expected data:
  1) Read numeric tag_id from the MFRC522 reader.
  2) Compute n = int(tag_id) × fp, where fp is the CA fingerprint integer.
     - The code asserts there is no overflow: n / fp == int(tag_id).
  3) Convert n to bytes (big-endian), hash with SHA3-512, and take the hex digest (128 hex chars).
  4) This 128-character hex digest is the “expected” content to be stored/read from the RFID tag.

- Storage format on the RFID tag:
  - Uses StoreMFRC522 with a reduced block map for faster IO:
    - BLOCK_ADDRESSES = { 7: [4,5,6], 11: [8,9,10], 15: [12,13,14] }
    - Total 9 data blocks × 16 bytes = 144 bytes capacity
    - Enough to store the 128-byte ASCII hex digest (plus padding/newline if present)
  - Only data blocks are written; sector trailer blocks are not modified by this code.

- Security properties and considerations:
  - The secret (fp) never leaves the Control Box filesystem; tags only hold the digest.
  - If an attacker clones a tag bit-for-bit, it will still authenticate; however, without fp they cannot produce valid digests for other tag IDs.
  - Rotating the CA certificate (changing fp) invalidates all previously written tags at once. Re-provision tags by running write_tag() again with the new fp.
  - Keep ~/app/etc/ca-chain.txt restricted (e.g., mode 600). Treat fp as sensitive material.
  - The tag_id is not secret; security relies on the secrecy of fp and the unforgeability of SHA3-512 preimages.
  - FACE + RFID can be combined: face auth gates UI access; RFID provides possession factor.
  
---

## Running

In three terminals/devices:

1) Control Box (RPi5, the hub)
```bash
python3 -m arod_control.ctrlbox
```

2) Instrument Box (RPi5, mechanics + PKE)
```bash
python3 -m arod_instrument.instbox
```

3) Visualization (same machine or laptop)
```bash
python3 -m arod_visual.visbox
# then open http://127.0.0.1:8050
```

---

## Controls and telemetry

Control messages (JSON, line-delimited over ctrl socket):
```json
{
  "type": "settings",
  "motor_set": 1,  // 1=up, 0=stop, -1=down
  "servo_set": 1,  // 1=engage, 0=scram
  "source_set": 1  // 1=external neutron source ON, 0=OFF
}
```

Streamed telemetry (binary) uses StreamingPacket.pack_triplet_plus_time64:
- 3 × float32: neutron_density, rho, distance
- 1 × float64: timestamp (milliseconds since epoch)
- Big-endian, total 20 bytes

---

## Internals (high-level)

Instrument Box (instbox.py) threads:
- update_speed_of_sound: samples DHT11 temperature/humidity and sets sonar speed of sound
- ctrl_receiver: reads JSON from Control Box and enqueues
- process_ctrl_status: applies motor/servo/source settings
- rod_protection: polls position and stops motor if distance ≥ MAX_ROD_DISTANCE while moving up
- ReactorPowerCalculator: real-time PKE integration
  - Sets explosion_event if power > threshold and resets state
- stream_sender: periodically sends latest neutron/rho/position/timestamp
- matrix_led_driver: shows arrows/height bar; runs explosion rectangle animation when explosion_event is set

Key synchronization:
- stop_event: global shutdown for all threads
- update_event: signals new PKE data to stream_sender
- explosion_event: signals the LED animation and PKE reset

Motor status notifications:
- Motor subclass (devices.Motor) uses a threading.Condition to publish status changes.
- wait_for_status_change(stop_event, timeout) returns when status changes or when the timeout expires.

Safety:
- Immediate motor.stop() on limit switch press
- Independent rod_protection watchdog
- Clean shutdown paths for sockets and threads

---

## Examples

- examples/face_auth: scripts to capture faces and train encodings
- examples/arod_control/rfid_read.py: RFID basics
- examples/arod_instrument: stand-alone LED matrix and DHT demos
- examples/mfrc522: read/write/dump tag examples

Run examples directly with python3 from the repository root.

---

## Development

Editable install:
```bash
pip3 install -e .
```

Logging:
- Instrument: ATHENA_instrument.log (in src/arod_instrument/)
- Control: ATHENA_controller.log
- Visual: visbox.log

Contributions welcome:
- Keep code thread-safe (prefer Events/Conditions over long sleeps).
- Make timeouts interruptible with stop_event.wait().
- Add clear logging and comments.

---

## License

MIT License (unless otherwise indicated in individual files).
See LICENSE.

## Acknowledgments:
- gpiozero, luma.led_matrix, NumPy, SciPy, Dash/Plotly, and MFRC522 libraries
