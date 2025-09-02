#!/bin/python3
""" DHT11 reading in RPi5
from: https://forums.raspberrypi.com/viewtopic.php?t=366269 """

import time

device0 = "/sys/bus/iio/devices/iio:device0"


#function to read first line and return integer

def readFirstLine(filename):
    try:
        f = open(filename,"rt")
        value =  int(f.readline())
        f.close()
        return True, value
    except ValueError:
        f.close()
        return False,-1
    except OSError:
        return False,0


try:
    while True:
        Flag, Temperature = readFirstLine(device0+"/in_temp_input")
        print("Temperature:",end="")
        if Flag:
            print(Temperature // 1000,"\u2103",end="\t")
        else:
            print("N.A.",end="\t")

        Flag, Humidity = readFirstLine(device0+"/in_humidityrelative_input")
        print("Humidity:",end="")
        if Flag:
            print(Humidity // 1000,"%")
        else:
            print("N.A.")
        time.sleep(2.0)
except KeyboardInterrupt:
    pass
