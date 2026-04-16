import cv2

CONFIDENCE_THRESHOLD = 80

# Load Haar Cascade for face detection
face_cascade = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")

# FIX: Guard against missing/broken cascade file
if face_cascade.empty():
    raise RuntimeError(
        "Failed to load haarcascade_frontalface_default.xml. "
        "Check the file path."
    )

# Load trained LBPH model
recognizer = cv2.face.LBPHFaceRecognizer_create()
recognizer.read("trainer.yml")

# Load labels
label_map = {}
with open("labels.txt", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            label_id, name = line.split(",", 1)
            label_map[int(label_id)] = name

# Open webcam
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to access webcam.")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=4,
       # minSize=(60, 60)
    )

    for (x, y, w, h) in faces:
        face_region = gray[y:y+h, x:x+w]

        # FIX: Resize to match the size used during training
        face_region = cv2.resize(face_region, (200, 200))

        label_id, confidence = recognizer.predict(face_region)

        if confidence < CONFIDENCE_THRESHOLD:
            name = label_map.get(label_id, "Unknown")
        else:
            name = "Unknown"

        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
        cv2.putText(
            frame,
            f"{name} ({int(confidence)})",
            (x, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

    cv2.imshow("Face Recognition", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()