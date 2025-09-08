#!/bin/bash
set -e

# This script builds the Debian packages for the RPi and Visualization components.
# It temporarily renames the appropriate setup script to `setup.py` for the build process.

# Check for required argument
if [ -z "$1" ]; then
    echo "Usage: ./build.sh [rpi|vis]"
    echo "  rpi - Build the package for the Raspberry Pi"
    echo "  vis - Build the package for the Visualization client"
    exit 1
fi

TARGET=$1
ORIGINAL_SETUP_FILE=""
TEMP_SETUP_FILE="setup.py"

# Determine which setup file to use
if [ "$TARGET" == "rpi" ]; then
    ORIGINAL_SETUP_FILE="setup_rpi.py"
    echo "--- Building ATHENA-rods RPi package ---"
elif [ "$TARGET" == "vis" ]; then
    ORIGINAL_SETUP_FILE="setup_vis.py"
    echo "--- Building ATHENA-rods Visualization package ---"
else
    echo "Error: Invalid target '$TARGET'. Use 'rpi' or 'vis'."
    exit 1
fi

# Check if the setup file exists
if [ ! -f "$ORIGINAL_SETUP_FILE" ]; then
    echo "Error: Setup file '$ORIGINAL_SETUP_FILE' not found."
    exit 1
fi

# Temporarily rename the setup file
mv "$ORIGINAL_SETUP_FILE" "$TEMP_SETUP_FILE"
echo "Temporarily renamed $ORIGINAL_SETUP_FILE to $TEMP_SETUP_FILE"

# Run the build command
# The trap command ensures the setup file is renamed back even if the build fails
trap "mv '$TEMP_SETUP_FILE' '$ORIGINAL_SETUP_FILE'; echo 'Renamed $TEMP_SETUP_FILE back to $ORIGINAL_SETUP_FILE'" EXIT

echo "Running stdeb to create Debian package..."
python3 setup.py --command-packages=stdeb.command bdist_deb

echo "-------------------------------------"
echo "Build successful!"
echo "Package created in the deb_dist/ directory."
echo "-------------------------------------"

# The trap will handle renaming the file back
