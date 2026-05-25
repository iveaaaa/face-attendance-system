import cv2
import mysql.connector
import mediapipe as mp
import math
import sys

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="face_attendance_db"
    )


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

def stop_attendance_session(session_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE attendance_sessions
        SET end_time = CURTIME()
        WHERE id = %s
    """, (session_id,))

    conn.commit()

    cursor.close()
    conn.close()

# =========================
# BLINK DETECTION SETTINGS
# =========================

mp_face_mesh = mp.solutions.face_mesh

LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

EAR_THRESHOLD = 0.20
blink_count = 0
eyes_closed = False
blink_verified = False


def distance(p1, p2):
    return math.dist((p1.x, p1.y), (p2.x, p2.y))


def eye_aspect_ratio(landmarks, eye_points):
    v1 = distance(landmarks[eye_points[1]], landmarks[eye_points[5]])
    v2 = distance(landmarks[eye_points[2]], landmarks[eye_points[4]])
    h = distance(landmarks[eye_points[0]], landmarks[eye_points[3]])

    return (v1 + v2) / (2.0 * h)


def detect_blink(landmarks):
    global blink_count, eyes_closed, blink_verified

    left_ear = eye_aspect_ratio(landmarks, LEFT_EYE)
    right_ear = eye_aspect_ratio(landmarks, RIGHT_EYE)
    avg_ear = (left_ear + right_ear) / 2.0

    if avg_ear < EAR_THRESHOLD:
        eyes_closed = True
    else:
        if eyes_closed:
            blink_count += 1
            eyes_closed = False
            blink_verified = True

    return blink_verified


# =========================
# FACE RECOGNITION SETTINGS
# =========================

CONFIDENCE_THRESHOLD = 65

# TEMPORARY: selected class
class_id = int(sys.argv[1])
session_id = int(sys.argv[2])

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

print("Session started:", session_id)
print("Selected class ID:", class_id)

cap = cv2.VideoCapture(0)

with mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
) as face_mesh:

    while True:
        ret, frame = cap.read()

        if not ret:
            print("Failed to access webcam.")
            break

        # Mirror camera for cleaner display
        frame = cv2.flip(frame, 1)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb_frame)

        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark
            detect_blink(landmarks)

        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4
        )

        for (x, y, w, h) in faces:
            face_region = gray[y:y+h, x:x+w]
            face_region = cv2.resize(face_region, (200, 200))

            label_id, confidence = recognizer.predict(face_region)

            if confidence < CONFIDENCE_THRESHOLD:
                name = label_map.get(label_id, "Unknown")
            else:
                name = "Unknown"

            if name != "Unknown":
                student_id = get_student_id_by_name(name)

                if student_id:
                    if student_belongs_to_class(student_id, class_id):
                        if blink_verified:
                            mark_attendance(student_id, session_id, confidence)
                        else:
                            print(f"{name} recognized. Blink required before attendance is marked.")
                    else:
                        print(f"{name} is recognized but not registered in this class.")
                else:
                    print(f"{name} is recognized but not found in students table.")

            # Professional face box
            box_color = (50, 205, 50) if name != "Unknown" else (0, 165, 255)

            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                box_color,
                3
            )

            cv2.rectangle(
                frame,
                (x, y - 35),
                (x + w, y),
                box_color,
                -1
            )

            display_name = name.title() if name != "Unknown" else "UNKNOWN"

            cv2.putText(
                frame,
                display_name,
                (x + 10, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )

        # Clean liveness status
        if blink_verified:
            status_text = "Liveness Verified"
            status_color = (50, 205, 50)
        else:
            status_text = "Waiting for Verification"
            status_color = (0, 165, 255)

        overlay = frame.copy()

        cv2.rectangle(
            overlay,
            (0, 0),
            (frame.shape[1], 70),
            (30, 30, 30),
            -1
        )

        alpha = 0.6
        frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

        cv2.putText(
            frame,
            "UniAttend - Live Attendance Session",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )

        cv2.putText(
            frame,
            status_text,
            (20, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            status_color,
            2
        )

        cv2.imshow("UniAttend - Live Attendance Session", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):

            stop_attendance_session(session_id)

            print("Attendance session stopped.")
            
            break


cap.release()
cv2.destroyAllWindows()