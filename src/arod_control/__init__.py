# ATHENA-rods communication setup
USE_SSL = True                              # Use SSL in communication
AUTH_ETC_PATH: str = "git/athena-rods/etc"  # Path to CtrBox configuration, in home directory
PORT_STREAM = 65432             # Port for streaming data
PORT_CTRL = 65433               # Port for control data
CONTROL_IP = '192.168.1.56'     # IP of the CtrBox machine
