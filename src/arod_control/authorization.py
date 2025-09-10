#!/usr/bin/env python3
"""
User authorization to operate ATHENA rod
Ondrej Chvala <ochvala@utexas.edu>
"""

from typing import Dict, List, Any, Tuple, Optional
import os
import hashlib
import cv2
import face_recognition
import pickle
from picamera2 import Picamera2
from mfrc522 import StoreMFRC522
from arod_control import AUTH_ETC_PATH


class FaceAuthorization:
    """ Face recognition using RPi5 camera """
    def __init__(self) -> None:
        # Load known faces' embeddings
        with open(os.path.join(os.path.expanduser('~'), '%s/face_rec_encodings.pickle' % AUTH_ETC_PATH), 'rb') as f:
            self.data: Dict[str, List[Any]] = pickle.load(f)
        # Start RPi5 camera
        self.picam2: Picamera2 = Picamera2()
        self.picam2.start()

    def scan_face(self) -> str:
        """Detects and identifies a face in a captured image from a camera.
        Parameters:
            - self: Instance of the class which provides access to the camera and face encoding data.
        Returns:
            - str: The name of the identified person if a match is found, otherwise "Unknown"."""
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

    def __del__(self) -> None:
        cv2.destroyAllWindows()
        self.picam2.close()


class RFID_Authorization:
    """RFID_Authorization class for handling RFID tag operations including digest creation, reading, and authorization.
    Parameters:
        - None
    Processing Logic:
        - Initializes by reading the CA certificate fingerprint and configuring block addresses for the MFRC522 reader.
        - Calculates a hash digest using the tag ID and a fingerprint for secure storage on RFID tags.
        - Reads and optionally prints the content of an RFID tag using a reader device for diagnostic purposes.
        - Compares the read data with expected data to check the authenticity of the RFID tag.
        - Writes correct hash digest data onto the RFID tag to ensure the tag holds valid expected data."""
    def __init__(self) -> None:
        # Read fingerprint of ATHENA rod CA certificate
        """Initialize the class and configure the fingerprint and block addresses.
        Parameters:
            None
        Returns:
            None"""
        with open(os.path.join(os.path.expanduser('~'), "%s/ca-chain.txt" % AUTH_ETC_PATH), "r") as f:
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

    def get_digest(self, tag_id: str) -> str:           # Get data expected on the RFIC card
        """Get data expected on the RFIC card.
        Parameters:
            - tag_id (str or int): Tag identifier to be processed for hashing.
        Returns:
            - str: Hexadecimal digest of the hash, which is stored on the RFID tag."""
        n = int(tag_id) * self.fp           # Tag_ID * fingerprint is a secret to hash and store
        assert n / self.fp == int(tag_id)   # Check for overflow
        n_bytes = (n.bit_length() + 7) // 8                 # How many bytes we need
        n_to_hash = n.to_bytes(n_bytes, byteorder='big')    # Convert to bytes, big-endian
        hash_obj = hashlib.sha3_512()
        hash_obj.update(n_to_hash)          # Make hash
        return hash_obj.hexdigest()         # This is what should be stored on the RFID tag

    def read_tag(self) -> Tuple[str, str]:          # Read RFID tag content
        """Reads the content of an RFID tag using a reader device.
        Parameters:
            - None
        Returns:
            - tuple[str, str]: A tuple containing the tag ID and the cleaned text content."""
        if self.do_print:
            print("Hold a tag near the reader")
        tag_id, text_raw = self.reader.read()
        text = text_raw.strip()
        if self.do_print:
            print(f'ID: {tag_id}\nText: {text}')
        return tag_id, text

    def auth_tag(self) -> bool:             # Check if the RFID tag contains the correct hex digest
        tag_id, text = self.read_tag()
        return text == self.get_digest(tag_id)  # True if equals

    def write_tag(self) -> None:            # Writes the correct hex digest on the RFID tag
        tag_id, text = self.read_tag()
        self.reader.write(self.get_digest(tag_id))
