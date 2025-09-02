""" Ultrasonic distance measurement  """
import time
from gpiozero import DistanceSensor
from gpiozero import Motor
from gpiozero import Servo

sensor = DistanceSensor(echo=24, trigger=23)
motor = Motor(forward=17, backward=27, enable=22)
# motor.forward()
# motor.backward()
servo = Servo(15)
# servo.min()
# servo.mid()
# servo.max()


def speed_of_sound(tempC: float, rel_humidity: float) -> float:
    """ Returns speed of sound in air [m/s], C_S from https://doi.org/10.1016/j.pisc.2016.06.024 """
    assert -20.0 < tempC < 100.0
    assert 0.0 <= rel_humidity <= 100.0
    return (331.296 + 0.606 * tempC) * (1.0 +  (rel_humidity * 9.604e-6 * 10 ** (0.032 * (tempC - 0.004 * tempC**2))))


def get_distance() -> float:
    """ Returns the distance measurement [cm] """
    return sensor.distance * 100.0


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
