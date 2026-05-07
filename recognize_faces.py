import cv2
import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="face_attendance_db"
    )

def create_attendance_session(class_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        INSERT INTO attendance_sessions (session_name, date, start_time, end_time, class_id)
        VALUES (%s, CURDATE(), CURTIME(), CURTIME(), %s)
    """
    cursor.execute(query, ("Live Recognition Session", class_id))
    conn.commit()

    session_id = cursor.lastrowid

    cursor.close()
    conn.close()

    return session_id

def get_student_id_by_name(name):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT id FROM students WHERE name = %s"
    cursor.execute(query, (name,))
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return result[0] if result else None

def student_belongs_to_class(student_id, class_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT id FROM class_students
        WHERE class_id = %s AND student_id = %s
    """
    cursor.execute(query, (class_id, student_id))
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return result is not None

def mark_attendance(student_id, session_id, confidence):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT id FROM attendance_records
        WHERE student_id = %s AND session_id = %s
    """
    cursor.execute(query, (student_id, session_id))
    result = cursor.fetchone()

    if not result:
        insert_query = """
            INSERT INTO attendance_records
            (student_id, session_id, timestamp, recognition_confidence, status)
            VALUES (%s, %s, NOW(), %s, %s)
        """
        cursor.execute(insert_query, (student_id, session_id, confidence, "Present"))
        conn.commit()
        print("Attendance marked.")
    else:
        print("Attendance already marked for this session.")

    cursor.close()
    conn.close()

CONFIDENCE_THRESHOLD = 80

# TEMPORARY: selected class
# class_id = 1 means Final Year Project / TMF3943
class_id = 1

face_cascade = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")

if face_cascade.empty():
    raise RuntimeError(
        "Failed to load haarcascade_frontalface_default.xml. "
        "Check the file path."
    )

recognizer = cv2.face.LBPHFaceRecognizer_create()
recognizer.read("trainer.yml")

label_map = {}
with open("labels.txt", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            label_id, name = line.split(",", 1)
            label_map[int(label_id)] = name

session_id = create_attendance_session(class_id)
print("Session started:", session_id)
print("Selected class ID:", class_id)

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
    )

    for (x, y, w, h) in faces:
        face_region = gray[y:y+h, x:x+w]
        face_region = cv2.resize(face_region, (200, 200))

        label_id, confidence = recognizer.predict(face_region)

        if confidence < CONFIDENCE_THRESHOLD:
            name = label_map.get(label_id, "Unknown")

            if name != "Unknown":
                student_id = get_student_id_by_name(name)

                if student_id:
                    if student_belongs_to_class(student_id, class_id):
                        mark_attendance(student_id, session_id, confidence)
                    else:
                        print(f"{name} is recognized but not registered in this class.")
                else:
                    print(f"{name} is recognized but not found in students table.")
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