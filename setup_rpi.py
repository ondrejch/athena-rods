import os
from setuptools import setup, find_packages

# Read the contents of README.md
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# This setup is for the Raspberry Pi components (Control Box and Instrument Box)
setup(
    name="athena-rods-rpi",
    version="0.1.2",
    description="ATHENA-rods hardware control system for Raspberry Pi",
    long_description=long_description,
    long_description_content_type='text/markdown',
    author="Ondrej Chvala",
    author_email="ochvala@utexas.edu",
    packages=find_packages(where="src", include=['arod_control', 'arod_instrument', 'mfrc522']),
    package_dir={"": "src"},
    install_requires=[
        "face_recognition",
        "opencv-python",
        "picamera2",
        "python-sensors",
        "gpiozero",
        "spidev",
        "scipy",
        "numpy<2",
        "luma.led_matrix",
        "smbus2"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Topic :: System :: Hardware",
    ],
)
