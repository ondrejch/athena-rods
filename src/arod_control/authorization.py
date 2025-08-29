#!/usr/bin/env python3
"""
User authorization to operate ATHENA rod
Ondrej Chvala <ochvala@utexas.edu>
"""

import os
import hashlib
import cv2
import face_recognition
import pickle
from picamera2 import Picamera2
from mfrc522 import StoreMFRC522


class FaceAuthorization:
    """ Face recognition using RPi5 camera """
    def __init__(self):
        # Load known faces' embeddings
        with open(os.path.join(os.path.expanduser('~'), 'app/face/encodings.pickle'), 'rb') as f:
            self.data = pickle.load(f)
        # Start RPi5 camera
        self.picam2 = Picamera2()
        self.picam2.start()

    def scan_face(self) -> str:
        frame = self.picam2.capture_array()
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        boxes = face_recognition.face_locations(rgb_frame)
        encodings = face_recognition.face_encodings(rgb_frame, boxes)

        for (box, encoding) in zip(boxes, encodings):
            matches = face_recognition.compare_faces(self.data["encodings"], encoding)
            name = "Unknown"
            if True in matches:
                matchedIdxs = [i for (i, b) in enumerate(matches) if b]
                counts = {}
                for i in matchedIdxs:
                    counts[self.data["names"][i]] = counts.get(self.data["names"][i], 0) + 1
                name = max(counts, key=counts.get)
            # print(f'{name}')
            return name

    def __del__(self):
        cv2.destroyAllWindows()
        self.picam2.close()


class RFID_Authorization:
    def __init__(self):
        # Read fingerprint of ATHENA rod CA certificate
        with open(os.path.join(os.path.expanduser('~'), "app/etc/ca-chain.txt"), "r") as f:
            text = f.read()
        self.fp = int(text.replace(':', ''), 16)  # Convert base-16 to integer

        self.reader = StoreMFRC522()
        self.reader.BLOCK_ADDRESSES = {     # Only use 3 blocks we need, it is faster.
             7: [ 4,  5,  6],               # Data block 1
            11: [ 8,  9, 10],               # Data block 2
            15: [12, 13, 14],               # Data block 3
        }
        self.reader.BLOCK_SLOTS = sum(len(lst) for lst in self.reader.BLOCK_ADDRESSES.values())

        self.do_print: bool = False

    def get_digest(self, tag_id):           # Get expected data on the RFIC card
        n = int(tag_id) * self.fp           # Tag_ID * fingerprint is a secret to hash and store
        assert n / self.fp == int(tag_id)   # Check for overflow
        n_bytes = (n.bit_length() + 7) // 8                 # How many bytes we need
        n_to_hash = n.to_bytes(n_bytes, byteorder='big')    # Convert to bytes, big-endian
        hash_obj = hashlib.sha3_512()
        hash_obj.update(n_to_hash)          # Make hash
        return hash_obj.hexdigest()         # This is what should be stored on the RFID tag

    def read_tag(self) -> tuple[str, str]:
        if self.do_print:
            print("Hold a tag near the reader")
        tag_id, text_raw = self.reader.read()
        text = text_raw.strip()
        if self.do_print:
            print(f'ID: {tag_id}\nText: {text}')
        return tag_id, text

    def auth_tag(self) -> bool:
        tag_id, text = self.read_tag()
        if text == self.get_digest(tag_id):
            return True
        else:
            return False

    def write_tag(self) -> None:
        tag_id, text = self.read_tag()
        self.reader.write(self.get_digest(tag_id))
