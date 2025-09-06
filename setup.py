from setuptools import setup, find_packages

setup(
    name="athena_rods",
    version="0.1.1",
    description="ATHENA rods hardware control system",
    author="Ondrej Chvala",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "face_recognition",
        "opencv-python",
        "picamera2",
        "python-sensors",
        "gpiozero",
        "spidev",
        "scipy",
        "numpy"
    ],
)
