""" Test face recongnition """

import time
import cv2
import face_recognition
import pickle
from picamera2 import Picamera2

with open('encodings.pickle', 'rb') as f:
    data = pickle.load(f)

picam2 = Picamera2()
picam2.start()

while True:
    frame = picam2.capture_array()
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb_frame)
    encodings = face_recognition.face_encodings(rgb_frame, boxes)

    for (box, encoding) in zip(boxes, encodings):
        matches = face_recognition.compare_faces(data["encodings"], encoding)
        name = "Unknown"
        if True in matches:
            matchedIdxs = [i for (i, b) in enumerate(matches) if b]
            counts = {}
            for i in matchedIdxs:
                counts[data["names"][i]] = counts.get(data["names"][i], 0) + 1
            name = max(counts, key=counts.get)
        print(f'{name}')
    time.sleep(5)

cv2.destroyAllWindows()
picam2.close()

