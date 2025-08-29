#!/bin/bash

# Setup for ATHENA rods

sudo apt update
sudo apt install -y python3-venv python3-setuptools libcamera-dev python3-libcamera


echo "Creating Python virtual environment..."
python3 -m venv venv --system-site-packages
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing ATHENA rods..."
pip install -e .

echo "Setup completed."

