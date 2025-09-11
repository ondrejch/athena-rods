#!/bin/bash
set -e

# This script builds the Debian packages for the RPi and Visualization components.
# It uses the unified setup.py with extras dependencies for different targets.

# Check for required argument
if [ -z "$1" ]; then
    echo "Usage: ./build.sh [rpi|vis]"
    echo "  rpi - Build the package for the Raspberry Pi"
    echo "  vis - Build the package for the Visualization client"
    exit 1
fi

TARGET=$1

# Determine build parameters for each target
if [ "$TARGET" == "rpi" ]; then
    echo "--- Building ATHENA-rods RPi package ---"
    EXTRAS="[rpi]"
    PACKAGE_SUFFIX="-rpi"
elif [ "$TARGET" == "vis" ]; then
    echo "--- Building ATHENA-rods Visualization package ---"
    EXTRAS="[vis]"
    PACKAGE_SUFFIX="-vis"
else
    echo "Error: Invalid target '$TARGET'. Use 'rpi' or 'vis'."
    exit 1
fi

# Check if the setup file exists
if [ ! -f "setup.py" ]; then
    echo "Error: setup.py not found."
    exit 1
fi

# Create a temporary setup.py with the appropriate extras as dependencies
TEMP_SETUP="setup_temp.py"
cat > "$TEMP_SETUP" << EOF
from typing import Dict, List
import os
from setuptools import setup, find_packages

# Read the contents of README.md
this_directory: str = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Common dependencies shared by both environments
common_deps = [
    "numpy<2",
    "scipy",
]

# Raspberry Pi specific dependencies
rpi_deps = [
    "face_recognition",
    "opencv-python",
    "picamera2",
    "python-sensors",
    "gpiozero",
    "spidev",
    "luma.led_matrix",
    "smbus2"
]

# Visualization client specific dependencies  
vis_deps = [
    "dash",
    "plotly",
]

# Select dependencies based on target
if "$TARGET" == "rpi":
    install_requires = common_deps + rpi_deps
    package_name = "athena-rods-rpi"
    description = "ATHENA-rods hardware control system for Raspberry Pi"
    classifiers = [
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 3 - Alpha",
        "Topic :: System :: Hardware",
        "Topic :: Scientific/Engineering :: Physics",
    ]
elif "$TARGET" == "vis":
    install_requires = common_deps + vis_deps
    package_name = "athena-rods-vis"
    description = "ATHENA-rods visualization client"
    classifiers = [
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 3 - Alpha",
        "Topic :: Scientific/Engineering :: Physics",
        "Framework :: Dash",
    ]

setup(
    name=package_name,
    version="0.1.2",
    description=description,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author="Ondrej Chvala",
    author_email="ochvala@utexas.edu",
    license="MIT",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=install_requires,
    classifiers=classifiers,
    python_requires=">=3.8",
)
EOF

# Run the build command with cleanup
trap "rm -f '$TEMP_SETUP'; echo 'Cleaned up temporary setup file'" EXIT

echo "Running stdeb to create Debian package..."
python3 "$TEMP_SETUP" --command-packages=stdeb.command bdist_deb

echo "-------------------------------------"
echo "Build successful!"
echo "Package created in the deb_dist/ directory."
echo "-------------------------------------"
