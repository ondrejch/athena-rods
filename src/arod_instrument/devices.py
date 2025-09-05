""" Management of sensors and actuators connected to the Intrumentation box """

import time
import numpy as np
from gpiozero import DistanceSensor
from gpiozero import Motor as OriginalMotor
from gpiozero import AngularServo
from gpiozero import Button


class Motor(OriginalMotor):
    """ Adding methods to move the rod intiutively """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def up(self):
        self.backward()

    def down(self):
        self.forward()


sonar = DistanceSensor(echo=24, trigger=23)  # Ultrasound sonar to measure distance
motor = Motor(forward=17, backward=27, enable=22)  # Motor that drives the rod
servo = AngularServo(15, initial_angle=180, min_angle=0, max_angle=180,  # Rod engagement servo
                     min_pulse_width=1.0/1000.0, max_pulse_width=25.0/10000.0)
limit_switch = Button(20)  # Limit switch at the bottom of the control rod slider
limit_switch.when_pressed = motor.stop  # Switch motor off when limit switch is hit


def rod_scram():
    servo.angle = 0


def rod_engage():
    servo.angle = 180


def speed_of_sound(tempC: float, rel_humidity: float) -> float:
    """ Returns speed of sound in air [m/s], C_S from https://doi.org/10.1016/j.pisc.2016.06.024 """
    assert -20.0 < tempC < 100.0
    assert 0.0 <= rel_humidity <= 100.0
    return (331.296 + 0.606 * tempC) * (1.0 +  (rel_humidity * 9.604e-6 * 10 ** (0.032 * (tempC - 0.004 * tempC**2))))


def get_distance() -> float:
    """ Returns the distance measurement [cm] """
    return sonar.distance * 100.0


def readFirstLine(filename):
    """ Function to read first line and return integer, for DHT11 """
    try:
        f = open(filename, "rt")
        value = int(f.readline())
        f.close()
        return True, value
    except ValueError:
        f.close()
        return False, -1
    except OSError:
        return False, 0


def get_dht() -> tuple[float, float]:
    """ Reads DHT11 sensor and returns temperature [C] and humidity [%]
        Note this is different for RPi5 than other Pis!
        See: https://forums.raspberrypi.com/viewtopic.php?t=366269 """
    tempC: float = -9999.9
    humidity_pct: float = -1.0
    device0: str = "/sys/bus/iio/devices/iio:device0"
    Flag, Temperature = readFirstLine(device0 + "/in_temp_input")
    if Flag:
        tempC = float(Temperature) / 1000.0

    Flag, Humidity = readFirstLine(device0 + "/in_humidityrelative_input")
    if Flag:
        humidity_pct = float(Humidity) / 1000.0
    return tempC, humidity_pct

# TRIG = 23
# ECHO = 24
# CHIP = 4
#
# h = lgpio.gpiochip_open(CHIP)
# lgpio.gpio_claim_output(h, TRIG)
# lgpio.gpio_claim_input(h, ECHO)
#
#
# def get_distance():
#     # Ensure TRIG is low
#     lgpio.gpio_write(h, TRIG, 0)
#     time.sleep(0.0002)
#
#     # Send 10us pulse
#     lgpio.gpio_write(h, TRIG, 1)
#     time.sleep(0.00001)  # 10 microseconds
#     lgpio.gpio_write(h, TRIG, 0)
#
#     # Wait for ECHO going high
#     t0 = time.time()
#     while lgpio.gpio_read(h, ECHO) == 0:
#         if time.time() - t0 > 0.02:
#             return None  # Timeout
#
#     start = time.time()
#
#     # Wait for ECHO going low
#     while lgpio.gpio_read(h, ECHO) == 1:
#         if time.time() - start > 0.02:
#             return None  # Timeout
#
#     end = time.time()
#
#     duration = end - start
#     distance = (duration * 34300) / 2  # in centimeters
#
#     return distance
