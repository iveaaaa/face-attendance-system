import cv2
import os
import numpy as np

dataset_path = "dataset"
face_cascade = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")
recognizer = cv2.face.LBPHFaceRecognizer_create()

faces = []
labels = []
label_map = {}
current_id = 0

for person_name in os.listdir(dataset_path):
    person_path = os.path.join(dataset_path, person_name)

    if not os.path.isdir(person_path):
        continue

    label_map[current_id] = person_name

    for image_name in os.listdir(person_path):
        image_path = os.path.join(person_path, image_name)
        print(f"Processing: {image_path}")

        try:
            img = cv2.imread(image_path)
            if img is None:
                print(f"Skipped unreadable image: {image_path}")
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            detected_faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4
            )

            if len(detected_faces) == 0:
                print(f"No face detected in: {image_path}")
                continue

            # Use only the largest face per image
            largest_face = max(detected_faces, key=lambda rect: rect[2] * rect[3])
            x, y, w, h = largest_face
            face_region = gray[y:y+h, x:x+w]

            faces.append(face_region)
            labels.append(current_id)

        except Exception as e:
            print(f"Error processing {image_path}: {e}")
            continue

    current_id += 1

if len(faces) == 0:
    print("No faces found for training.")
else:
    recognizer.train(faces, np.array(labels))
    recognizer.save("trainer.yml")

    with open("labels.txt", "w", encoding="utf-8") as f:
        for label_id, name in label_map.items():
            f.write(f"{label_id},{name}\n")

    print("Model trained successfully!")
    print(f"Total faces used for training: {len(faces)}")