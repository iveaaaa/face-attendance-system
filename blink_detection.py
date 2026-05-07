import cv2
import mediapipe as mp
import math

mp_face_mesh = mp.solutions.face_mesh

# Eye landmark indexes
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

def distance(p1, p2):
    return math.dist((p1.x, p1.y), (p2.x, p2.y))

def eye_aspect_ratio(landmarks, eye_points):
    # vertical distances
    v1 = distance(landmarks[eye_points[1]], landmarks[eye_points[5]])
    v2 = distance(landmarks[eye_points[2]], landmarks[eye_points[4]])

    # horizontal distance
    h = distance(landmarks[eye_points[0]], landmarks[eye_points[3]])

    return (v1 + v2) / (2.0 * h)

cap = cv2.VideoCapture(0)

blink_count = 0
eyes_closed = False

EAR_THRESHOLD = 0.20

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

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb_frame)

        status_text = "No face detected"

        if results.multi_face_landmarks:
            face_landmarks = results.multi_face_landmarks[0]
            landmarks = face_landmarks.landmark

            left_ear = eye_aspect_ratio(landmarks, LEFT_EYE)
            right_ear = eye_aspect_ratio(landmarks, RIGHT_EYE)
            avg_ear = (left_ear + right_ear) / 2.0

            if avg_ear < EAR_THRESHOLD:
                eyes_closed = True
                status_text = "Eyes Closed"
            else:
                if eyes_closed:
                    blink_count += 1
                    eyes_closed = False
                status_text = "Eyes Open"

            cv2.putText(frame, f"EAR: {avg_ear:.2f}", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        cv2.putText(frame, f"Status: {status_text}", (30, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

        cv2.putText(frame, f"Blinks: {blink_count}", (30, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

        cv2.imshow("Blink Detection Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

cap.release()
cv2.destroyAllWindows()