import os

from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from functools import wraps
import subprocess
import sys

app = Flask(__name__)
app.secret_key = "secret123"

# ──────────────────────────────────────────────
# DB HELPERS
# ──────────────────────────────────────────────

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

def mark_attendance(student_id, session_id, confidence):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM attendance_records WHERE student_id = %s AND session_id = %s",
        (student_id, session_id)
    )
    if not cursor.fetchone():
        cursor.execute(
            """INSERT INTO attendance_records (student_id, session_id, timestamp, recognition_confidence, status)
               VALUES (%s, %s, NOW(), %s, %s)""",
            (student_id, session_id, confidence, "Present")
        )
        conn.commit()
        success = True
    else:
        success = False
    cursor.close()
    conn.close()
    return success

# ──────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():

    if "user" in session:

        if session.get("role") == "student":

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT face_registered
                FROM students
                WHERE id = %s
            """, (session["student_ref"],))

            student = cursor.fetchone()

            cursor.close()
            conn.close()

            if student and student["face_registered"] == 0:
                return redirect(url_for("student_register_face"))

            return redirect(url_for("student_dashboard"))

        else:
            return redirect(url_for("dashboard"))   

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
             
            if user:
                session["user"] = user["username"]
                session["role"] = user["role"]
                session["student_ref"] = user["student_ref"]

                if user["role"] == "student":

                    if user["must_change_password"] == 1:
                        flash("Please change your default password.")
                        return redirect(url_for("change_password"))

                    conn = get_db_connection()
                    cursor = conn.cursor(dictionary=True)

                    cursor.execute("""
                        SELECT face_registered
                        FROM students
                        WHERE id = %s
                    """, (session["student_ref"],))

                    student = cursor.fetchone()

                    cursor.close()
                    conn.close()

                    if student and student["face_registered"] == 0:
                        flash("Please register your face before accessing the system.")
                        return redirect(url_for("student_register_face"))

                    return redirect(url_for("student_dashboard"))
                else:
                    return redirect(url_for("dashboard"))

            else:
                flash("Invalid username or password.")
        except Exception as e:
            flash(f"Database error: {e}")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():

    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        new_password = request.form["new_password"].strip()
        confirm_password = request.form["confirm_password"].strip()

        if not new_password or not confirm_password:
            flash("All fields are required.")
            return redirect(url_for("change_password"))

        if new_password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for("change_password"))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users
            SET password = %s,
                must_change_password = 0
            WHERE student_ref = %s
        """, (
            new_password,
            session["student_ref"]
        ))

        conn.commit()

        cursor.close()
        conn.close()

        flash("Password changed successfully. Please login again.")

        session.clear()

        return redirect(url_for("login"))

    return render_template(
        "change_password.html",
        user=session["user"],
        role=session.get("role")
    )
# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") == "student":
        return redirect(url_for("student_dashboard"))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM students")
    total_students = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM attendance_sessions")
    total_sessions = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM attendance_records WHERE DATE(timestamp) = CURDATE()")
    today_attendance = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT s.name, a.timestamp, a.recognition_confidence, a.status
        FROM attendance_records a
        JOIN students s ON a.student_id = s.id
        ORDER BY a.timestamp DESC
        LIMIT 5
    """)
    recent_records = cursor.fetchall()

    cursor.execute("""
        SELECT sess.session_name, sess.date, COUNT(a.id) AS count
        FROM attendance_sessions sess
        LEFT JOIN attendance_records a ON a.session_id = sess.id
        GROUP BY sess.id
        ORDER BY sess.date DESC
        LIMIT 5
    """)
    recent_sessions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("dashboard.html",
        total_students=total_students,
        total_sessions=total_sessions,
        today_attendance=today_attendance,
        recent_records=recent_records,
        recent_sessions=recent_sessions,
        user=session["user"],
        role=session.get("role")
    )

@app.route("/student/dashboard")
@login_required
def student_dashboard():
    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    return render_template(
        "student_home.html",
        user=session["user"],
        role=session.get("role")
    )

@app.route("/student/attendance")
@login_required
def student_attendance():

    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            sess.session_name,
            sess.date,
            a.timestamp,
            a.recognition_confidence,
            a.status
        FROM attendance_records a
        JOIN attendance_sessions sess
            ON a.session_id = sess.id
        WHERE a.student_id = %s
        ORDER BY a.timestamp DESC
    """, (session["student_ref"],))

    attendance = cursor.fetchall()

    total_classes = len(attendance)
    attended = sum(1 for a in attendance if a["status"] == "Present")
    percentage = round((attended / total_classes) * 100, 1) if total_classes > 0 else 0

    cursor.close()
    conn.close()

    return render_template(
        "student_attendance.html",
        attendance=attendance,
        total_classes=total_classes,
        attended=attended,
        percentage=percentage,
        user=session["user"],
        role=session.get("role")
    )

@app.route("/student/profile")
@login_required
def student_profile():
    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM students
        WHERE id = %s
    """, (session["student_ref"],))

    student = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "student_profile.html",
        student=student,
        user=session["user"],
        role=session.get("role")
    )
@app.route("/student/profile/edit", methods=["GET", "POST"])
@login_required
def edit_student_profile():

    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":

        program = request.form["program"].strip()
        email = request.form["email"].strip()

        cursor.execute("""
            UPDATE students
            SET program = %s,
                email = %s
            WHERE id = %s
        """, (
            program,
            email,
            session["student_ref"]
        ))

        conn.commit()

        flash("Profile updated successfully.")

        cursor.close()
        conn.close()

        return redirect(url_for("student_profile"))

    cursor.execute("""
        SELECT *
        FROM students
        WHERE id = %s
    """, (session["student_ref"],))

    student = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "edit_student_profile.html",
        student=student,
        user=session["user"],
        role=session.get("role")
    )

@app.route("/student/register_face")
@login_required
def student_register_face():
    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    import cv2
    import os

    student_id = session["student_ref"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM students WHERE id = %s",
        (student_id,)
    )

    student = cursor.fetchone()

    if not student:
        cursor.close()
        conn.close()
        flash("Student not found.")
        return redirect(url_for("student_dashboard"))

    face_detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    folder_name = f"{student['name']}"
    dataset_path = os.path.join("dataset", folder_name)
    os.makedirs(dataset_path, exist_ok=True)

    cam = cv2.VideoCapture(0)

    count = 0
    max_images = 50

    while True:
        ret, frame = cam.read()

        if not ret:
            flash("Camera could not be opened.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = face_detector.detectMultiScale(
            gray,
            scaleFactor=1.3,
            minNeighbors=5
        )

        for (x, y, w, h) in faces:
            count += 1

            face_img = gray[y:y+h, x:x+w]
            face_img = cv2.resize(face_img, (200, 200))

            file_path = os.path.join(dataset_path, f"{count}.jpg")
            cv2.imwrite(file_path, face_img)

            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 255, 255), 2)
            cv2.putText(
                frame,
                f"Captured {count}/{max_images}",
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )

            cv2.waitKey(150)

        cv2.imshow("Student Face Registration - Press Q to stop", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        if count >= max_images:
            break

    cam.release()
    cv2.destroyAllWindows()

    if count > 0:

        subprocess.run([sys.executable, "train_model.py"])

        cursor.execute("""
            UPDATE students
            SET face_registered = 1,
                face_status = 'Successful'
            WHERE id = %s
        """, (student_id,))

        conn.commit()

        flash(f"Face registration successful. {count} images captured.")

    else:

        cursor.execute("""
            UPDATE students
            SET face_registered = 0,
                face_status = 'Pending'
            WHERE id = %s
        """, (student_id,))

        conn.commit()

        flash("No face images captured. Please try again.")

    cursor.close()
    conn.close()

    return redirect(url_for("student_profile"))
    
# ──────────────────────────────────────────────
# STUDENTS
# ──────────────────────────────────────────────

@app.route("/students")
@login_required
def students():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students ORDER BY name")
    all_students = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template(
        "students.html", 
        students=all_students, 
        user=session["user"],
        role=session.get("role")
    )

@app.route("/students/add", methods=["POST"])
@login_required
def add_student():

    name = request.form["name"].strip()
    student_id_str = request.form["student_id"].strip()

    if not name or not student_id_str:
        flash("Name and Student ID are required.")
        return redirect(url_for("students"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert into students table
        cursor.execute("""
            INSERT INTO students (name, student_id)
            VALUES (%s, %s)
        """, (name, student_id_str))

        new_student_id = cursor.lastrowid

        # Default login
        username = student_id_str
        password = "Unimas" + student_id_str

        # Insert into users table
        cursor.execute("""
            INSERT INTO users 
            (username, password, role, student_ref, must_change_password)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            username,
            password,
            "student",
            new_student_id,
            1
        ))

        conn.commit()

        cursor.close()
        conn.close()

        flash(
            f"Student registered successfully. "
            f"Default password: {password}"
        )

    except mysql.connector.IntegrityError:
        flash("Student ID already exists.")

    except Exception as e:
        flash(f"Error: {e}")

    return redirect(url_for("students"))

@app.route("/students/delete/<int:id>", methods=["POST"])
@login_required
def delete_student(id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM students WHERE id = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash("Student deleted.")
    except Exception as e:
        flash(f"Error: {e}")
    return redirect(url_for("students"))

# ──────────────────────────────────────────────
# ATTENDANCE SESSIONS
# ──────────────────────────────────────────────

@app.route("/sessions")
@login_required
def sessions():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT sess.*, COUNT(a.id) AS attendance_count
        FROM attendance_sessions sess
        LEFT JOIN attendance_records a ON a.session_id = sess.id
        GROUP BY sess.id
        ORDER BY sess.date DESC, sess.start_time DESC
    """)
    all_sessions = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template(
        "sessions.html", 
         sessions=all_sessions,
         user=session["user"], 
         role=session.get("role"))

@app.route("/sessions/create", methods=["POST"])
@login_required
def create_session():
    session_name = request.form["session_name"].strip()

    if not session_name:
        flash("Session name is required.")
        return redirect(url_for("sessions"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO attendance_sessions
            (session_name, date, start_time, end_time, class_id)
            VALUES (%s, CURDATE(), CURTIME(), CURTIME(), %s)
            """,
            (session_name, 1)
        )

        conn.commit()

        cursor.close()
        conn.close()

        # Automatically open recognition
        subprocess.Popen([sys.executable, "recognize_faces.py"])

        flash(f"Session '{session_name}' started successfully.")

    except Exception as e:
        flash(f"Error: {e}")

    return redirect(url_for("sessions"))

@app.route("/sessions/delete/<int:id>", methods=["POST"])
@login_required
def delete_session(id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attendance_records WHERE session_id = %s", (id,))
        cursor.execute("DELETE FROM attendance_sessions WHERE id = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash("Session deleted.")
    except Exception as e:
        flash(f"Error: {e}")
    return redirect(url_for("sessions"))

# ──────────────────────────────────────────────
# ATTENDANCE RECORDS
# ──────────────────────────────────────────────

@app.route("/records")
@login_required
def records():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, session_name, date FROM attendance_sessions ORDER BY date DESC")
    all_sessions = cursor.fetchall()

    selected_session = request.args.get("session_id", "")
    attendance = []

    if selected_session:
        cursor.execute("""
            SELECT s.name, s.student_id, a.timestamp, a.recognition_confidence, a.status
            FROM attendance_records a
            JOIN students s ON a.student_id = s.id
            WHERE a.session_id = %s
            ORDER BY a.timestamp
        """, (selected_session,))
        attendance = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("records.html",
        sessions=all_sessions,
        attendance=attendance,
        selected_session=selected_session,
        user=session["user"],
        role=session.get("role")
    )

# ──────────────────────────────────────────────
# CLASSES
# ──────────────────────────────────────────────

@app.route('/classes')
@login_required
def classes():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM classes ORDER BY course_code")
    all_classes = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'classes.html',
        classes=all_classes,
        user=session["user"],
        role=session.get("role")
    )
@app.route("/classes/add", methods=["POST"])
@login_required
def add_class():
    course_code = request.form["course_code"].strip()
    class_name = request.form["class_name"].strip()

    if not course_code or not class_name:
        flash("Course code and class name are required.")
        return redirect(url_for("classes"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO classes (course_code, class_name)
            VALUES (%s, %s)
        """, (course_code, class_name))

        conn.commit()

        cursor.close()
        conn.close()

        flash("Class added successfully.")

    except Exception as e:
        flash(f"Error: {e}")

    return redirect(url_for("classes"))

@app.route("/classes/<int:class_id>/students")
@login_required
def manage_class_students(class_id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM classes WHERE id = %s",
        (class_id,)
    )

    selected_class = cursor.fetchone()

    cursor.execute("""
        SELECT *
        FROM students
        ORDER BY name
    """)

    all_students = cursor.fetchall()

    cursor.execute("""
        SELECT student_id
        FROM class_students
        WHERE class_id = %s
    """, (class_id,))

    enrolled = [row["student_id"] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return render_template(
        "manage_class_students.html",
        selected_class=selected_class,
        students=all_students,
        enrolled=enrolled,
        user=session["user"],
        role=session.get("role")
    )

@app.route("/classes/<int:class_id>/students/save", methods=["POST"])
@login_required
def save_class_students(class_id):

    selected_students = request.form.getlist("student_ids")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM class_students WHERE class_id = %s",
            (class_id,)
        )

        for student_id in selected_students:
            cursor.execute("""
                INSERT INTO class_students (class_id, student_id)
                VALUES (%s, %s)
            """, (class_id, student_id))

        conn.commit()

        cursor.close()
        conn.close()

        flash("Class students updated successfully.")

    except Exception as e:
        flash(f"Error: {e}")

    return redirect(url_for("manage_class_students", class_id=class_id)) 

@app.route("/classes/<int:class_id>/start", methods=["POST"])
@login_required
def start_class_session(class_id):

    session_name = request.form["session_name"].strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM classes WHERE id = %s",
            (class_id,)
        )

        selected_class = cursor.fetchone()

        if not selected_class:
            flash("Class not found.")
            return redirect(url_for("classes"))

        cursor.execute("""
            INSERT INTO attendance_sessions
            (session_name, date, start_time, end_time, class_id)
            VALUES (%s, CURDATE(), CURTIME(), NULL, %s)
        """, (session_name, class_id))

        conn.commit()

        session_id = cursor.lastrowid

        cursor.close()
        conn.close()

        subprocess.Popen([
            sys.executable,
            "recognize_faces.py",
            str(class_id),
            str(session_id)
        ])

        flash(f"Attendance started for {session_name}.")

    except Exception as e:
        flash(f"Error: {e}")

    return redirect(url_for("classes"))
# ──────────────────────────────────────────────
# TEST ROUTES (keep for dev, remove later)
# ──────────────────────────────────────────────

@app.route("/test_db")
def test_db():
    try:
        conn = get_db_connection()
        conn.close()
        return "Database connected successfully!"
    except Exception as e:
        return f"Database connection failed: {e}"

# ──────────────────────────────────────────────
# RUN APP
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
