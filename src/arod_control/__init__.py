# ATHENA-rods communication setup
USE_SSL: bool = True                        # Use SSL in communication
AUTH_ETC_PATH: str = "git/athena-rods/etc"  # Path to CtrBox configuration, in home directory
PORT_STREAM: int = 65432             # Port for streaming data
PORT_CTRL: int = 65433               # Port for control data
CONTROL_IP: str = '192.168.1.56'     # IP of the CtrBox machine
