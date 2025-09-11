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

setup(
    name="athena-rods",
    version="0.1.2",
    description="ATHENA-rods: A hardware control and visualization system for nuclear reactor simulation",
    long_description=long_description,
    long_description_content_type='text/markdown',
    author="Ondrej Chvala",
    author_email="ochvala@utexas.edu",
    license="MIT",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=common_deps,
    extras_require={
        'rpi': rpi_deps,
        'vis': vis_deps,
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 3 - Alpha",
        "Topic :: System :: Hardware",
        "Topic :: Scientific/Engineering :: Physics",
        "Framework :: Dash",
    ],
    python_requires=">=3.8",
)