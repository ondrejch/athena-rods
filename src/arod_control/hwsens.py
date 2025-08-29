#!/usr/bin/env python3
"""
Handles hardware sensors information on RPi5
Ondrej Chvala <ochvala@utexas.edu>
"""
import sensors


def get_sensors(do_print: bool = False) -> dict:
    sensors.init()
    data: dict = {}
    for chip in sensors.iter_detected_chips():
        for feature in chip:
            if feature.label.lower() == 'fan1':
                data['fan1'] = feature.get_value()
                if do_print:
                    print(f"{feature.label}: {feature.get_value():.0f} RPM")
            if chip.prefix == b'cpu_thermal' and feature.label.lower() == 'temp1':
                data['temp1'] = feature.get_value()
                if do_print:
                    print(f"{feature.label}: {feature.get_value():.0f} C")
    sensors.cleanup()
    return data


if __name__ == '__main__':
    _ = get_sensors(do_print=True)
