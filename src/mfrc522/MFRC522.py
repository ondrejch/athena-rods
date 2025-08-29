#!/usr/bin/env python3

#    Refactored by straub.dennis1@web.de
#
#    Original comments:
#    Copyright 2014,2018 Mario Gomez <mario.gomez@teubi.co>
#
#    This file is part of MFRC522-Python
#    MFRC522-Python is a simple Python implementation for
#    the MFRC522 NFC Card Reader for the Raspberry Pi.
#
#    MFRC522-Python is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    MFRC522-Python is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with MFRC522-Python.  If not, see <http://www.gnu.org/licenses/>.
#
import logging

import spidev
from gpiozero import DigitalOutputDevice


class MFRC522:
    MAX_LEN = 16

    PCD_IDLE = 0x00
    PCD_AUTHENT = 0x0E
    PCD_RECEIVE = 0x08
    PCD_TRANSMIT = 0x04
    PCD_TRANSCEIVE = 0x0C
    PCD_RESETPHASE = 0x0F
    PCD_CALCCRC = 0x03

    PICC_REQIDL = 0x26
    PICC_REQALL = 0x52
    PICC_ANTICOLL = 0x93
    PICC_SElECTTAG = 0x93
    PICC_AUTHENT1A = 0x60
    PICC_AUTHENT1B = 0x61
    PICC_READ = 0x30
    PICC_WRITE = 0xA0
    PICC_DECREMENT = 0xC0
    PICC_INCREMENT = 0xC1
    PICC_RESTORE = 0xC2
    PICC_TRANSFER = 0xB0
    PICC_HALT = 0x50

    MI_OK = 0
    MI_NOTAGERR = 1
    MI_ERR = 2

    RESERVED_00 = 0x00
    COMMAND_REG = 0x01
    COMMIEN_REG = 0x02
    DIVLEN_REG = 0x03
    COMMIRQ_REG = 0x04
    DIVIRQ_REG = 0x05
    ERROR_REG = 0x06
    STATUS1_REG = 0x07
    STATUS2_REG = 0x08
    FIFO_DATA_REG = 0x09
    FIFO_LEVEL_REG = 0x0A
    WATER_LEVEL_REG = 0x0B
    CONTROL_REG = 0x0C
    BIT_FRAMING_REG = 0x0D
    COLL_REG = 0x0E
    RESERVED_01 = 0x0F

    RESERVED_10 = 0x10
    MODE_REG = 0x11
    TX_MODE_REG = 0x12
    RX_MODE_REG = 0x13
    TX_CONTROL_REG = 0x14
    TX_AUTO_REG = 0x15
    TX_SEL_REG = 0x16
    RX_SEL_REG = 0x17
    RX_THRESHOLD_REG = 0x18
    DEMOD_REG = 0x19
    RESERVED_11 = 0x1A
    RESERVED_12 = 0x1B
    MIFARE_REG = 0x1C
    RESERVED_13 = 0x1D
    RESERVED_14 = 0x1E
    SERIAL_SPEED_REG = 0x1F

    RESERVED_20 = 0x20
    CRC_RESULT_REG_M = 0x21
    CRC_RESULT_REG_L = 0x22
    RESERVED_21 = 0x23
    MOD_WIDTH_REG = 0x24
    RESERVED_22 = 0x25
    RFCFG_REG = 0x26
    GSN_REG = 0x27
    CWGSP_REG = 0x28
    MOD_GSP_REG = 0x29
    T_MODE_REG = 0x2A
    T_PRESCALER_REG = 0x2B
    TRELOAD_REG_H = 0x2C
    TRELOAD_REG_L = 0x2D
    T_COUNTER_VALUE_REG_H = 0x2E
    T_COUNTER_VALUE_REG_L = 0x2F

    RESERVED_30 = 0x30
    TEST_SEL1_REG = 0x31
    TEST_SEL2_REG = 0x32
    TEST_PINEN_REG = 0x33
    TEST_PIN_VALUE_REG = 0x34
    TEST_BUS_REG = 0x35
    AUTO_TEST_REG = 0x36
    VERSION_REG = 0x37
    ANALOG_TEST_REG = 0x38
    TEST_DAC1_REG = 0x39
    TEST_DAC2_REG = 0x3A
    TEST_ADC_REG = 0x3B
    RESERVED_31 = 0x3C
    RESERVED_32 = 0x3D
    RESERVED_33 = 0x3E
    RESERVED_34 = 0x3F

    SERNUM = []

    def __init__(self, bus=0, device=0, spd=1000000, pin_rst=22, debug_level="WARNING"):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = spd

        self.logger = logging.getLogger("mfrc522Logger")
        self.logger.addHandler(logging.StreamHandler())
        self.logger.setLevel(logging.getLevelName(debug_level))
        DigitalOutputDevice(pin_rst).on()
        self.mfrc522_init()

    def mfrc522_reset(self):
        self.write_mfrc522(self.COMMAND_REG, self.PCD_RESETPHASE)

    def write_mfrc522(self, addr, val):
        self.spi.xfer2([(addr << 1) & 0x7E, val])

    def read_mfrc522(self, addr):
        return self.spi.xfer2([((addr << 1) & 0x7E) | 0x80, 0])[1]


    def set_bit_mask(self, reg, mask):
        chip_values = self.read_mfrc522(reg)
        self.write_mfrc522(reg, chip_values | mask)

    def clear_bit_mask(self, reg, mask):
        chip_values = self.read_mfrc522(reg)
        self.write_mfrc522(reg, chip_values & (~mask))

    def antenna_on(self):
        chip_values = self.read_mfrc522(self.TX_CONTROL_REG)
        if ~(chip_values & 0x03):
            self.set_bit_mask(self.TX_CONTROL_REG, 0x03)

    def antenna_off(self):
        self.clear_bit_mask(self.TX_CONTROL_REG, 0x03)

    def mfrc522_to_card(self, command, send_data):
        if command == self.PCD_AUTHENT:
            irq_en = 0x12
            wait_irq = 0x10
        elif command == self.PCD_TRANSCEIVE:
            irq_en = 0x77
            wait_irq = 0x30
        else:
            return self.MI_ERR, [], 0

        self.write_mfrc522(self.COMMIEN_REG, irq_en | 0x80)
        self.clear_bit_mask(self.COMMIRQ_REG, 0x80)
        self.set_bit_mask(self.FIFO_LEVEL_REG, 0x80)
        self.write_mfrc522(self.COMMAND_REG, self.PCD_IDLE)

        for data in send_data:
            self.write_mfrc522(self.FIFO_DATA_REG, data)

        self.write_mfrc522(self.COMMAND_REG, command)

        if command == self.PCD_TRANSCEIVE:
            self.set_bit_mask(self.BIT_FRAMING_REG, 0x80)

        for index in range(2000, 0, -1):
            chip_value = self.read_mfrc522(self.COMMIRQ_REG)
            if ~((index != 0) and ~(chip_value & 0x01) and ~(chip_value & wait_irq)):
                break

        self.clear_bit_mask(self.BIT_FRAMING_REG, 0x80)

        if not self.read_mfrc522(self.ERROR_REG) & 0x1B:
            status = self.MI_NOTAGERR if chip_value & irq_en & 0x01 else self.MI_OK

            if command == self.PCD_TRANSCEIVE:
                return self.send_and_get_data(status)
            else:
                return status, [], 0
        return self.MI_ERR, [], 0

    def send_and_get_data(self, status):
        chip_value = self.read_mfrc522(self.FIFO_LEVEL_REG)
        last_bits = self.read_mfrc522(self.CONTROL_REG) & 0x07
        back_len = (
            (chip_value - 1) * 8 + last_bits if last_bits != 0 else chip_value * 8
        )
        if chip_value == 0:
            chip_value = 1
        elif chip_value > self.MAX_LEN:
            chip_value = self.MAX_LEN
        back_data = [self.read_mfrc522(self.FIFO_DATA_REG) for _ in range(chip_value)]
        return status, back_data, back_len

    def mfrc522_request(self, req_mode):
        self.write_mfrc522(self.BIT_FRAMING_REG, 0x07)
        status, _, back_bits = self.mfrc522_to_card(self.PCD_TRANSCEIVE, [req_mode])
        if (status != self.MI_OK) | (back_bits != 0x10):
            status = self.MI_ERR
        return status, back_bits

    def mfrc522_anticoll(self):
        self.write_mfrc522(self.BIT_FRAMING_REG, 0x00)
        status, back_data, _ = self.mfrc522_to_card(
            self.PCD_TRANSCEIVE, [self.PICC_ANTICOLL, 0x20]
        )
        if status != self.MI_OK:
            return status, back_data
        serial_number = 0
        try:
            for data in back_data[:4]:
                serial_number ^= data
            if serial_number != back_data[4]:
                return self.MI_ERR, back_data
        except IndexError:
            return self.MI_ERR, back_data
        return status, back_data

    def calculate_crc(self, in_data):
        self.clear_bit_mask(self.DIVIRQ_REG, 0x04)
        self.set_bit_mask(self.FIFO_LEVEL_REG, 0x80)

        for data in in_data:
            self.write_mfrc522(self.FIFO_DATA_REG, data)
        self.write_mfrc522(self.COMMAND_REG, self.PCD_CALCCRC)

        for _ in range(255, 0, -1):
            if not self.read_mfrc522(self.DIVIRQ_REG) & 0x04:
                break
        return [
            self.read_mfrc522(self.CRC_RESULT_REG_L),
            self.read_mfrc522(self.CRC_RESULT_REG_M),
        ]

    def mfrc522_select_tag(self, serial_number):
        buffer = [self.PICC_SElECTTAG, 0x70]
        buffer.extend(serial_number)
        buffer.extend(self.calculate_crc(buffer))
        status, back_data, back_len = self.mfrc522_to_card(self.PCD_TRANSCEIVE, buffer)

        if status == self.MI_OK and back_len == 0x18:
            self.logger.debug(f"Size: {back_data[0]}")
            return back_data[0]
        else:
            return 0

    def mfrc522_auth(self, auth_mode, block_address, sector_keys, serial_numbers):
        buffer = [auth_mode, block_address]
        buffer.extend(sector_keys)
        buffer.extend(serial_numbers[:4])
        status, _, _ = self.mfrc522_to_card(self.PCD_AUTHENT, buffer)
        if status != self.MI_OK:
            self.logger.error("AUTH ERROR!!")
        if self.read_mfrc522(self.STATUS2_REG) & 0x08 == 0:
            self.logger.error("AUTH ERROR(status2reg & 0x08) != 0")
        return status

    def mfrc522_stop_crypto1(self):
        self.clear_bit_mask(self.STATUS2_REG, 0x08)

    def mfrc522_read(self, block_address):
        receive_data = [self.PICC_READ, block_address]
        receive_data.extend(self.calculate_crc(receive_data))
        status, back_data, _ = self.mfrc522_to_card(self.PCD_TRANSCEIVE, receive_data)
        if status != self.MI_OK:
            self.logger.error("Error while reading!")
        if len(back_data) == 16:
            self.logger.debug(f"Sector {block_address} {back_data}")
            return back_data
        else:
            return None

    def mfrc522_write(self, block_address, write_data):
        buffer = [self.PICC_WRITE, block_address]
        buffer.extend(self.calculate_crc(buffer))
        status, back_data, back_len = self.mfrc522_to_card(self.PCD_TRANSCEIVE, buffer)
        if status != self.MI_OK or back_len != 4 or (back_data[0] & 0x0F) != 0x0A:
            status = self.MI_ERR
        self.logger.debug(f"{back_len} backdata &0x0F == 0x0A {back_data[0] & 0x0F}")
        if status == self.MI_OK:
            buffer = [data for index, data in enumerate(write_data) if index < 16]
            buffer.extend(self.calculate_crc(buffer))
            status, back_data, back_len = self.mfrc522_to_card(
                self.PCD_TRANSCEIVE, buffer
            )
            if status != self.MI_OK or back_len != 4 or back_data[0] & 0x0F != 0x0A:
                self.logger.error("Error while writing")
            else:
                self.logger.debug("Data written")


    def mfrc522_init(self):
        self.mfrc522_reset()

        self.write_mfrc522(self.T_MODE_REG, 0x8D)
        self.write_mfrc522(self.T_PRESCALER_REG, 0x3E)
        self.write_mfrc522(self.TRELOAD_REG_L, 30)
        self.write_mfrc522(self.TRELOAD_REG_H, 0)

        self.write_mfrc522(self.TX_AUTO_REG, 0x40)
        self.write_mfrc522(self.MODE_REG, 0x3D)
        self.antenna_on()

    def mfrc522_dump_classic_1K(self, key, uid):
        i = 0
        while i < 64:
            status = self.mfrc522_auth(self.PICC_AUTHENT1A, i, key, uid)
            # Check if authenticated
            if status == self.MI_OK:
                data = self.mfrc522_read(i)
                print(f"Sector {i}: {data}")

            else:
                print("Authentication error")
            i = i+1


