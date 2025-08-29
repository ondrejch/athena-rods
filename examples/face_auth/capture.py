import os
import cv2
from picamera2 import Picamera2

person_name: str = input('Your name: ').strip()

picam2 = Picamera2()
picam2.start()
face_dir: str = f'data/{person_name}'
os.makedirs(face_dir, exist_ok=True)

ic: int = -1
count: int = 0
while count < 20:  # capture 20 photos
    frame = picam2.capture_array()
    print(f'Capture #{count:02.0f}. Focus the image and press spacebar; q to quit')
    cv2.imshow('Face Capture', frame)
    key = cv2.waitKey(100)
    if key == ord(' '):  # Press Space to capture image
        image_file: str = f"{face_dir}/img_{count}.jpg"
        cv2.imwrite(image_file, frame)
        print(f'Wrote: {image_file}')
        count += 1
    elif key == ord('q'):
        break

cv2.destroyAllWindows()
picam2.close()

