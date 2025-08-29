#!/usr/bin/env python3

"""
Adopted from https://github.com/Dennis-89/MFRC522-python-SimpleMFRC522.git
"""

from . import MFRC522
from itertools import chain

DEFAULT_KEYS = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]


class SimpleMFRC522:
    KEYS = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
    BLOCK_ADDRESSES = [8, 9, 10]

    def __init__(self):
        self.reader = MFRC522()

    def read(self):
        while True:
            tag_id, text = self._read_no_block()
            if tag_id:
                return tag_id, text

    def write(self, text):
        while True:
            tag_id, text_in = self._write_no_block(text)
            if tag_id:
                return tag_id, text_in

    def _read_id(self):
        while True:
            id_tag = self._read_id_no_block()
            if id_tag:
                return id_tag

    def _read_id_no_block(self):
        status, _ = self.reader.mfrc522_request(self.reader.PICC_REQIDL)
        if status != self.reader.MI_OK:
            return None
        status, uid = self.reader.mfrc522_anticoll()
        return None if status != self.reader.MI_OK else self._uid_to_number(uid)

    def _read_no_block(self):
        status, _ = self.reader.mfrc522_request(self.reader.PICC_REQIDL)
        if status != self.reader.MI_OK:
            return None, None
        status, uid = self.reader.mfrc522_anticoll()
        if status != self.reader.MI_OK:
            return None, None
        tag_id = self._uid_to_number(uid)
        self.reader.mfrc522_select_tag(uid)
        status = self.reader.mfrc522_auth(
            self.reader.PICC_AUTHENT1A, 11, self.KEYS, uid
        )
        text_read = ""
        if status == self.reader.MI_OK:
            data = list(
                chain.from_iterable(
                    self.reader.mfrc522_read(address)
                    for address in self.BLOCK_ADDRESSES
                    if self.reader.mfrc522_read(address)
                )
            )
            text_read = "".join(chr(i) for i in data)
        self.reader.mfrc522_stop_crypto1()
        return tag_id, text_read

    def _write_no_block(self, text):
        status, _ = self.reader.mfrc522_request(self.reader.PICC_REQIDL)
        if status != self.reader.MI_OK:
            return None, None
        status, uid = self.reader.mfrc522_anticoll()
        if status != self.reader.MI_OK:
            return None, None
        tag_id = self._uid_to_number(uid)
        self.reader.mfrc522_select_tag(uid)
        status = self.reader.mfrc522_auth(
            self.reader.PICC_AUTHENT1A, 11, self.KEYS, uid
        )
        self.reader.mfrc522_read(11)
        if status == self.reader.MI_OK:
            data = bytearray()
            data.extend(
                bytearray(text.ljust(len(self.BLOCK_ADDRESSES) * 16).encode("ascii"))
            )
            for index, block_num in enumerate(self.BLOCK_ADDRESSES):
                self.reader.mfrc522_write(
                    block_num, data[(index * 16) : (index + 1) * 16]
                )
        self.reader.mfrc522_stop_crypto1()
        return tag_id, text[: len(self.BLOCK_ADDRESSES) * 16]

    @staticmethod
    def _uid_to_number(uid):
        number = 0
        for index, character in enumerate(uid):
            number = number * 256 + character
            if index == 4:
                return number


class StoreMFRC522(SimpleMFRC522):
    """ Use more storage on the RFID card """
    def __init__(self):
        super().__init__()
        self.BLOCK_ADDRESSES = {
             7: [ 4,  5,  6],
            11: [ 8,  9, 10],
            15: [12, 13, 14],
            19: [16, 17, 18],
            23: [20, 21, 22],
            27: [24, 25, 26],
            31: [28, 29, 30],
            35: [32, 33, 34],
            39: [36, 37, 38],
            43: [40, 41, 42],
            47: [44, 45, 46],
            51: [48, 49, 50],
            55: [52, 53, 54],
            59: [56, 57, 58],
            63: [60, 61, 62]
        }
        self.BLOCK_SLOTS = sum(len(lst) for lst in self.BLOCK_ADDRESSES.values())

    def _read_no_block(self):
        status, _ = self.reader.mfrc522_request(self.reader.PICC_REQIDL)
        if status != self.reader.MI_OK:
            return None, None
        status, uid = self.reader.mfrc522_anticoll()
        if status != self.reader.MI_OK:
            return None, None
        tag_id = self._uid_to_number(uid)
        self.reader.mfrc522_select_tag(uid)
        data = []
        text_read = ""
        for trailer_block in self.BLOCK_ADDRESSES.keys():
            status = self.reader.mfrc522_auth(
                self.reader.PICC_AUTHENT1A, trailer_block, self.KEYS, uid)
            if status == self.reader.MI_OK:
                data.extend(
                    list(
                        chain.from_iterable(
                            self.reader.mfrc522_read(address)
                            for address in self.BLOCK_ADDRESSES[trailer_block]
                            if self.reader.mfrc522_read(address)
                        )
                    )
                )
        if data:
            text_read = "".join(chr(i) for i in data)

        self.reader.mfrc522_stop_crypto1()
        return tag_id, text_read

    def _write_no_block(self, text):
        status, _ = self.reader.mfrc522_request(self.reader.PICC_REQIDL)
        if status != self.reader.MI_OK:
            return None, None
        status, uid = self.reader.mfrc522_anticoll()
        if status != self.reader.MI_OK:
            return None, None
        tag_id = self._uid_to_number(uid)
        self.reader.mfrc522_select_tag(uid)
        data = bytearray()
        data.extend(
            bytearray(text.ljust(self.BLOCK_SLOTS * 16).encode("ascii"))
        )
        slot_i: int = 0
        for trailer_block in self.BLOCK_ADDRESSES.keys():
            status = self.reader.mfrc522_auth(
                self.reader.PICC_AUTHENT1A, trailer_block, self.KEYS, uid
            )
            self.reader.mfrc522_read(trailer_block)
            if status == self.reader.MI_OK:
                for index, block_num in enumerate(self.BLOCK_ADDRESSES[trailer_block]):
                    self.reader.mfrc522_write(
                        block_num, data[((slot_i + index) * 16) : (slot_i + index + 1) * 16]
                    )
            slot_i += len(self.BLOCK_ADDRESSES[trailer_block])
        self.reader.mfrc522_stop_crypto1()
        return tag_id, text[: len(self.BLOCK_ADDRESSES) * 16]

    def write_password_to_blocks(self, password):
        raise NotImplementedError("Seems to brick the RFID tag, needs more work (and more tags to bricks..).")
        """
        Ideas for future - set keys A and B independently by different methods; keep the other code default for testing.

        Write a 6-byte password key as both Key A and Key B plus access bits
        into sector trailer blocks in self.BLOCK_ADDRESSES.keys().

        Args:
            password (list[int]): List of 6 integers (each 0-255) representing the key.
        """
        if not (isinstance(password, list) and len(password) == 6 and all(isinstance(b, int) and 0 <= b <= 255 for b in password)):
            raise ValueError("Password must be a list of 6 integers (0-255)")

        access_bits = [0xFF, 0x07, 0x80, 0x69]
        if password == [0, 0, 0, 0, 0, 0] or password == DEFAULT_KEYS:  # Set default password
            password = DEFAULT_KEYS
        trailer_data = bytes(password + access_bits + password)
        print(f'writing password: {password}')

        # Wait for card presence
        while True:
            status, _ = self.reader.mfrc522_request(self.reader.PICC_REQIDL)
            if status == self.reader.MI_OK:
                break

        # Get UID through anti-collision
        while True:
            status, uid = self.reader.mfrc522_anticoll()
            if status == self.reader.MI_OK:
                break

        # Set all trailing sectors
        trailer_blocks = [3]
        trailer_blocks.extend(self.BLOCK_ADDRESSES.keys())
        for block in trailer_blocks:
            # Select the tag
            self.reader.mfrc522_select_tag(uid)

            # Authenticate with current key (self.KEYS)
            status = self.reader.mfrc522_auth(self.reader.PICC_AUTHENT1A, block, self.KEYS, uid)
            if status != self.reader.MI_OK:
                raise RuntimeError(f"Authentication failed for block {block}")
            else:
                print(f'Authenticated card {uid}')

            self.reader.mfrc522_read(block)
            if status == self.reader.MI_OK:
                # Write the sector trailer block
                status = self.reader.mfrc522_write(block, trailer_data)
                if status != self.reader.MI_OK:
                    raise RuntimeError(f"Write failed for block {block}")
                else:
                    print(f'Wrote new block data {trailer_data} ')

            # Stop encryption on the card
            self.reader.mfrc522_stop_crypto1()
