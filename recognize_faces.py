import cv2
import mysql.connector
import math
import sys
import os
import threading
from collections import defaultdict
from deepface import DeepFace

# =========================
# DATABASE
# =========================

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
    cursor.execute("SELECT id FROM students WHERE name = %s", (name,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None


def student_belongs_to_class(student_id, class_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM class_students
        WHERE class_id = %s AND student_id = %s
    """, (class_id, student_id))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result is not None


def mark_attendance(student_id, session_id, confidence):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE attendance_records
        SET status = 'Present',
            timestamp = NOW(),
            recognition_confidence = %s
        WHERE student_id = %s
        AND session_id = %s
        AND status = 'Absent'
    """, (confidence, student_id, session_id))
    conn.commit()
    if cursor.rowcount > 0:
        print(f"[MARKED PRESENT] student_id={student_id}, confidence={confidence:.4f}")
    else:
        print(f"[ALREADY PRESENT] student_id={student_id}")
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
# SETTINGS
# =========================

DATASET_PATH          = "dataset"
MODEL_NAME            = "ArcFace"
DETECTOR_BACKEND      = "yunet"
DISTANCE_METRIC       = "cosine"
DISTANCE_THRESHOLD    = 0.40
VOTE_THRESHOLD        = 15
DOMINANT_RATIO        = 0.75
REGION_DIST_THRESHOLD = 200
REGION_MAX_IDLE       = 30
SMOOTHING_ALPHA       = 0.25
RECOGNITION_INTERVAL  = 10

# =========================
# REGION TRACKER
# =========================

class FaceRegionTracker:
    def __init__(self):
        self.regions  = {}
        self.next_id  = 1

    def _find_region(self, cx, cy):
        best_id   = None
        best_dist = float("inf")
        for rid, data in self.regions.items():
            rx, ry = data["center"]
            d = math.dist((cx, cy), (rx, ry))
            if d < REGION_DIST_THRESHOLD and d < best_dist:
                best_dist = d
                best_id   = rid
        return best_id

    def update(self, cx, cy, name):
        rid = self._find_region(cx, cy)
        if rid is None:
            rid = self.next_id
            self.next_id += 1
            self.regions[rid] = {
                "center"      : (cx, cy),
                "votes"       : defaultdict(int),
                "total_frames": 0,
                "idle_frames" : 0,
            }

        r = self.regions[rid]
        ox, oy = r["center"]
        r["center"] = (
            int(ox * (1 - SMOOTHING_ALPHA) + cx * SMOOTHING_ALPHA),
            int(oy * (1 - SMOOTHING_ALPHA) + cy * SMOOTHING_ALPHA),
        )
        r["total_frames"] += 1
        r["idle_frames"]   = 0

        if name != "Unknown":
            r["votes"][name] += 1

        if r["total_frames"] >= VOTE_THRESHOLD:
            votes = r["votes"]
            if votes:
                top_name    = max(votes, key=votes.get)
                top_votes   = votes[top_name]
                total_votes = sum(votes.values())
                ratio       = top_votes / total_votes
                if ratio >= DOMINANT_RATIO:
                    r["votes"]        = defaultdict(int)
                    r["total_frames"] = 0
                    return rid, True, top_name, ratio
            r["votes"]        = defaultdict(int)
            r["total_frames"] = 0

        return rid, False, None, 0.0

    def tick_idle(self, active_region_ids):
        to_delete = []
        for rid in list(self.regions.keys()):
            if rid not in active_region_ids:
                self.regions[rid]["idle_frames"] += 1
                if self.regions[rid]["idle_frames"] > REGION_MAX_IDLE:
                    to_delete.append(rid)
        for rid in to_delete:
            del self.regions[rid]


# =========================
# RECOGNITION THREAD
# =========================

recognition_cache  = {}
processing_lock    = threading.Lock()
processing_regions = set()


def recognize_face_async(frame_rgb, region_id, x, y, w, h):
    global recognition_cache, processing_regions

    try:
        face_crop = frame_rgb[y:y+h, x:x+w]
        if face_crop.size == 0:
            return

        results = DeepFace.find(
            img_path         = face_crop,
            db_path          = DATASET_PATH,
            model_name       = MODEL_NAME,
            detector_backend = "skip",
            distance_metric  = DISTANCE_METRIC,
            enforce_detection= False,
            silent           = True,
        )

        if results and len(results[0]) > 0:
            top_result = results[0].iloc[0]

            # Find distance column dynamically
            dist_col = None
            for col in top_result.index:
                if 'cosine' in col.lower() or 'distance' in col.lower():
                    dist_col = col
                    break

            distance = top_result[dist_col] if dist_col else 1.0

            if distance < DISTANCE_THRESHOLD:
                identity = top_result["identity"]
                name     = os.path.basename(os.path.dirname(identity))
            else:
                name     = "Unknown"
                distance = 1.0
        else:
            name     = "Unknown"
            distance = 1.0

        with processing_lock:
            recognition_cache[region_id] = (name, distance, x, y, w, h)

    except Exception as e:
        print(f"[Recognition error] {e}")
        with processing_lock:
            recognition_cache[region_id] = ("Unknown", 1.0, x, y, w, h)
    finally:
        with processing_lock:
            processing_regions.discard(region_id)


# =========================
# MAIN
# =========================

class_id   = int(sys.argv[1])
session_id = int(sys.argv[2])

print(f"Session started : {session_id}")
print(f"Selected class  : {class_id}")
print(f"Loading ArcFace model — please wait...")

# Pre-build embeddings
try:
    for person in os.listdir(DATASET_PATH):
        person_path = os.path.join(DATASET_PATH, person)
        if os.path.isdir(person_path):
            images = os.listdir(person_path)
            if images:
                sample_img = os.path.join(person_path, images[0])
                DeepFace.find(
                    img_path         = sample_img,
                    db_path          = DATASET_PATH,
                    model_name       = MODEL_NAME,
                    detector_backend = DETECTOR_BACKEND,
                    distance_metric  = DISTANCE_METRIC,
                    enforce_detection= False,
                    silent           = True,
                )
                print("Embeddings loaded successfully!")
                break
except Exception as e:
    print(f"Embedding preload warning: {e}")

tracker        = FaceRegionTracker()
already_marked = set()
frame_counter  = 0
stable_boxes   = {}  # Persists between frames — prevents blinking

cap = cv2.VideoCapture(1)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to access webcam.")
        break

    frame         = cv2.flip(frame, 1)
    frame_rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame_counter += 1

    # --- Run detection every N frames only ---
    if frame_counter % RECOGNITION_INTERVAL == 0:
        try:
            detected_faces = DeepFace.extract_faces(
                img_path         = frame_rgb,
                detector_backend = DETECTOR_BACKEND,
                enforce_detection= False,
                align            = True,
            )
        except Exception:
            detected_faces = []

        active_rids = set()

        # Filter overlapping detections — keep only the largest box per face
        def filter_overlapping_faces(faces, overlap_threshold=0.5):
            if not faces:
                return faces
            
            # Sort by box area (largest first)
            faces = sorted(faces, key=lambda f: f["facial_area"]["w"] * f["facial_area"]["h"], reverse=True)
            
            kept = []
            for face in faces:
                r = face["facial_area"]
                x1, y1, w1, h1 = r["x"], r["y"], r["w"], r["h"]
                
                is_duplicate = False
                for kept_face in kept:
                    kr = kept_face["facial_area"]
                    x2, y2, w2, h2 = kr["x"], kr["y"], kr["w"], kr["h"]
                    
                    # Calculate overlap
                    ix = max(0, min(x1+w1, x2+w2) - max(x1, x2))
                    iy = max(0, min(y1+h1, y2+h2) - max(y1, y2))
                    intersection = ix * iy
                    union = w1*h1 + w2*h2 - intersection
                    iou = intersection / union if union > 0 else 0
                    
                    if iou > overlap_threshold:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    kept.append(face)
            
            return kept

        detected_faces = filter_overlapping_faces(detected_faces)

        for face_obj in detected_faces:
            region = face_obj["facial_area"]
            x, y, w, h = region["x"], region["y"], region["w"], region["h"]
            confidence  = face_obj.get("confidence", 0)

            if confidence < 0.75:
                continue

            cx, cy = x + w // 2, y + h // 2

            with processing_lock:
                rid = tracker._find_region(cx, cy)
                if rid is None:
                    rid = tracker.next_id
                cached   = recognition_cache.get(rid, ("Unknown", 1.0, x, y, w, h))
                name     = cached[0]
                distance = cached[1]

            with processing_lock:
                is_processing = rid in processing_regions
                too_many = len(processing_regions) >= 5  # max 5 faces at once

            if not is_processing and not too_many:
                with processing_lock:
                    processing_regions.add(rid)
                t = threading.Thread(
                    target = recognize_face_async,
                    args   = (frame_rgb.copy(), rid, x, y, w, h),
                    daemon = True,
                )
                t.start()

            rid, should_mark, winning_name, ratio = tracker.update(cx, cy, name)
            active_rids.add(rid)

            # Update stable box — persists every frame
            stable_boxes[rid] = {
                "x": x, "y": y, "w": w, "h": h,
                "name": name,
                "distance": distance,
                "vote_progress": tracker.regions.get(rid, {}).get("total_frames", 0)
            }

            # Attendance marking
            if should_mark and winning_name is not None:
                student_id = get_student_id_by_name(winning_name)
                if student_id and student_id not in already_marked:
                    if student_belongs_to_class(student_id, class_id):
                        mark_attendance(student_id, session_id, round(distance, 4))
                        already_marked.add(student_id)
                        print(f"[ACCEPTED] {winning_name} | ratio={ratio:.2f} | distance={distance:.4f}")
                    else:
                        print(f"[NOT IN CLASS] {winning_name} skipped.")
                elif student_id in already_marked:
                    pass
                else:
                    print(f"[NOT IN DB] {winning_name} not found.")

        tracker.tick_idle(active_rids)

        # Remove boxes for expired regions
        for rid in list(stable_boxes.keys()):
            if rid not in tracker.regions:
                del stable_boxes[rid]

    # --- DRAW stable boxes EVERY frame — no blinking ---
    for rid, box in stable_boxes.items():
        x, y, w, h    = box["x"], box["y"], box["w"], box["h"]
        name          = box["name"]
        distance      = box["distance"]
        vote_progress = box.get("vote_progress", 0)

        box_color = (50, 205, 50) if name != "Unknown" else (0, 165, 255)

        cv2.rectangle(frame, (x, y), (x + w, y + h), box_color, 3)
        cv2.rectangle(frame, (x, y - 35), (x + w, y), box_color, -1)

        display_name = name.title() if name != "Unknown" else "UNKNOWN"
        cv2.putText(
            frame, display_name,
            (x + 8, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.65,
            (255, 255, 255), 2,
        )

        if name != "Unknown":
            cv2.putText(
                frame, f"dist:{distance:.2f}",
                (x + 8, y + h + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (200, 200, 200), 1,
            )

        if vote_progress > 0:
            bar_width = min(int(w * (vote_progress / VOTE_THRESHOLD)), w)
            cv2.rectangle(frame, (x, y + h + 25), (x + bar_width, y + h + 32), (0, 255, 200), -1)
            cv2.rectangle(frame, (x, y + h + 25), (x + w, y + h + 32), (100, 100, 100), 1)

    # --- HUD ---
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], 55), (20, 20, 20), -1)
    frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)

    cv2.putText(
        frame,
        f"UniAttend - Live Attendance  |  Model: ArcFace  |  Marked: {len(already_marked)}",
        (15, 33),
        cv2.FONT_HERSHEY_SIMPLEX, 0.60,
        (255, 255, 255), 2,
    )

    cv2.imshow("UniAttend - Live Attendance Session", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        stop_attendance_session(session_id)
        print("Attendance session stopped.")
        break

cap.release()
cv2.destroyAllWindows()