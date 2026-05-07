import cv2
import os

student_name = input("Enter student name: ").strip()

folder_path = os.path.join("dataset", student_name)
os.makedirs(folder_path, exist_ok=True)

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

if face_cascade.empty():
    raise RuntimeError("Failed to load Haar Cascade classifier.")

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
count = 1

print("Press 's' to save detected face")
print("Press 'q' to quit")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to access webcam.")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.2,
        minNeighbors=5,
        minSize=(60, 60)
    )

    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    cv2.imshow("Face Capture", frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('s'):
        if len(faces) == 0:
            print("No face detected. Image not saved.")
        else:
            x, y, w, h = faces[0]
            face = gray[y:y+h, x:x+w]
            face = cv2.resize(face, (200, 200))

            img_name = f"img{count}.jpg"
            img_path = os.path.join(folder_path, img_name)
            cv2.imwrite(img_path, face)

            print(f"Saved: {img_path}")
            count += 1

    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()