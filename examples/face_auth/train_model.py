import face_recognition
import os
import pickle

data = []
labels = []

dataset_dir = "data"
for person in os.listdir(dataset_dir):
    person_dir = os.path.join(dataset_dir, person)
    for img in os.listdir(person_dir):
        image_path = os.path.join(person_dir, img)
        image = face_recognition.load_image_file(image_path)
        face_encodings = face_recognition.face_encodings(image)
        if face_encodings:
            data.append(face_encodings[0])
            labels.append(person)

with open('encodings.pickle', 'wb') as f:
    pickle.dump({"encodings": data, "names": labels}, f)

