import os
import sys
import subprocess
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector

# ──────────────────────────────────────────────
# APP CONFIGURATION
# ──────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = "secret123"

app.config['MAIL_SERVER']   = 'smtp.gmail.com'
app.config['MAIL_PORT']     = 587
app.config['MAIL_USE_TLS']  = True
app.config['MAIL_USERNAME'] = 'uniattendfyp@gmail.com'
app.config['MAIL_PASSWORD'] = ''

mail = Mail(app)

# ──────────────────────────────────────────────
# DATABASE
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
    success = cursor.rowcount > 0
    cursor.close()
    conn.close()
    return success

# ──────────────────────────────────────────────
# AUTH DECORATORS
# ──────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def student_onboarding_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "student":
            return f(*args, **kwargs)

        if not session.get("student_ref"):
            return redirect(url_for("login"))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT s.program, s.email, s.face_registered
            FROM users u
            JOIN students s ON u.student_ref = s.id
            WHERE u.student_ref = %s
        """, (session["student_ref"],))
        data = cursor.fetchone()
        cursor.close()
        conn.close()

        if not data:
            flash("Student record not found. Please log in again.")
            return redirect(url_for("login"))

        if not data["program"] or not data["email"]:
            flash("Please complete your profile first.")
            return redirect(url_for("edit_student_profile"))

        if data["face_registered"] == 0:
            flash("Please register your face first.")
            return redirect(url_for("student_profile"))

        return f(*args, **kwargs)
    return decorated

# ──────────────────────────────────────────────
# AUTHENTICATION ROUTES
# ──────────────────────────────────────────────

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        if session.get("role") == "student":
            return redirect(url_for("student_dashboard"))
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user and check_password_hash(user["password"], password):
                session["user"]        = user["username"]
                session["role"]        = user["role"]
                session["student_ref"] = user["student_ref"]
                if user["role"] == "student":
                    return redirect(url_for("student_dashboard"))
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid username or password.")
        except Exception as e:
            flash(f"Database error: {e}")

    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name             = request.form["name"].strip()
        student_id       = request.form["student_id"].strip()
        email            = request.form["email"].strip()
        program          = request.form["program"].strip()
        password         = request.form["password"].strip()
        confirm_password = request.form["confirm_password"].strip()

        if password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for("signup"))

        hashed_password = generate_password_hash(password)

        try:
            conn   = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO students (name, student_id, email, program, face_registered, face_status)
                VALUES (%s, %s, %s, %s, 0, 'Pending')
            """, (name, student_id, email, program))

            new_student_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO users (username, password, role, student_ref, must_change_password)
                VALUES (%s, %s, 'student', %s, 0)
            """, (student_id, hashed_password, new_student_id))

            conn.commit()
            cursor.close()
            conn.close()

            flash("Account created successfully. Please login.")
            return redirect(url_for("login"))

        except mysql.connector.IntegrityError:
            flash("Student ID already exists.")
            return redirect(url_for("signup"))

    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username']

        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.id, u.role, u.email AS user_email, s.email AS student_email
            FROM users u
            LEFT JOIN students s ON u.student_ref = s.id
            WHERE u.username = %s
        """, (username,))
        user = cursor.fetchone()

        if user:
            email = user['student_email'] if user['role'] == 'student' else user['user_email']

            if email:
                token  = secrets.token_urlsafe(32)
                expiry = datetime.now() + timedelta(minutes=15)

                cursor.execute("""
                    UPDATE users
                    SET reset_token = %s, reset_token_expiry = %s
                    WHERE id = %s
                """, (token, expiry, user['id']))
                conn.commit()

                reset_link = url_for('reset_password', token=token, _external=True)

                msg      = Message('UniAttend Password Reset',
                                   sender=app.config['MAIL_USERNAME'],
                                   recipients=[email])
                msg.body = f"""Hello,

Click the link below to reset your UniAttend password:

{reset_link}

This link will expire in 15 minutes.

If you did not request this, please ignore this email.
"""
                try:
                    mail.send(msg)
                except Exception as e:
                    print(f"Email error: {e}")

        cursor.close()
        conn.close()

        flash('If the username exists and has a linked email, a reset link has been sent.')
        return redirect(url_for('forgot_password'))

    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE reset_token = %s", (token,))
    user = cursor.fetchone()

    if not user:
        flash('Invalid reset token.')
        return redirect(url_for('forgot_password'))

    if user['reset_token_expiry'] < datetime.now():
        flash('Reset link has expired.')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password         = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match.')
            return redirect(request.url)

        cursor.execute("""
            UPDATE users
            SET password = %s, reset_token = NULL, reset_token_expiry = NULL
            WHERE id = %s
        """, (generate_password_hash(password), user['id']))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Password reset successful. Please sign in.')
        return redirect(url_for('login'))

    cursor.close()
    conn.close()
    return render_template('reset_password.html')

# ──────────────────────────────────────────────
# EDUCATOR DASHBOARD
# ──────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") == "student":
        return redirect(url_for("student_dashboard"))

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM students")
    total_students = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM attendance_sessions")
    total_sessions = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total FROM attendance_records
        WHERE DATE(timestamp) = CURDATE()
    """)
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
        SELECT sess.id, sess.session_name, sess.date,
               COUNT(CASE WHEN a.status = 'Present' THEN 1 END) AS count
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

# ──────────────────────────────────────────────
# STUDENTS
# ──────────────────────────────────────────────

@app.route("/students")
@login_required
def students():
    search   = request.args.get("search", "").strip()
    page     = int(request.args.get("page", 1))
    per_page = 10
    offset   = (page - 1) * per_page

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if search:
        cursor.execute("""
            SELECT * FROM students
            WHERE student_id LIKE %s OR name LIKE %s OR email LIKE %s
            ORDER BY name LIMIT %s OFFSET %s
        """, (f"%{search}%", f"%{search}%", f"%{search}%", per_page, offset))
    else:
        cursor.execute("""
            SELECT * FROM students ORDER BY name LIMIT %s OFFSET %s
        """, (per_page, offset))

    all_students = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("students.html",
        students=all_students,
        search=search,
        page=page,
        per_page=per_page,
        user=session["user"],
        role=session.get("role")
    )

@app.route("/students/add", methods=["POST"])
@login_required
def add_student():
    name           = request.form["name"].strip()
    student_id_str = request.form["student_id"].strip()

    if not name or not student_id_str:
        flash("Name and Student ID are required.")
        return redirect(url_for("students"))

    try:
        conn   = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO students (name, student_id) VALUES (%s, %s)
        """, (name, student_id_str))

        new_student_id   = cursor.lastrowid
        default_password = "Unimas" + student_id_str

        cursor.execute("""
            INSERT INTO users (username, password, role, student_ref)
            VALUES (%s, %s, 'student', %s)
        """, (student_id_str, generate_password_hash(default_password), new_student_id))

        conn.commit()
        cursor.close()
        conn.close()

        flash(f"Student registered successfully. Default password: {default_password}")

    except mysql.connector.IntegrityError:
        flash("Student ID already exists.")
    except Exception as e:
        flash(f"Error: {e}")

    return redirect(url_for("students"))

@app.route("/students/delete/<int:id>", methods=["POST"])
@login_required
def delete_student(id):
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM attendance_records WHERE student_id = %s", (id,))
        cursor.execute("DELETE FROM class_students WHERE student_id = %s", (id,))
        cursor.execute("DELETE FROM users WHERE student_ref = %s", (id,))
        cursor.execute("DELETE FROM students WHERE id = %s", (id,))

        conn.commit()
        cursor.close()
        conn.close()
        flash("Student deleted.")
    except Exception as e:
        flash(f"Error: {e}")

    return redirect(url_for("students"))

# ──────────────────────────────────────────────
# CLASSES
# ──────────────────────────────────────────────

@app.route('/classes')
@login_required
def classes():
    search   = request.args.get("search", "").strip()
    page     = int(request.args.get("page", 1))
    per_page = 10
    offset   = (page - 1) * per_page

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if search:
        cursor.execute("""
            SELECT * FROM classes
            WHERE course_code LIKE %s OR class_name LIKE %s
            ORDER BY course_code LIMIT %s OFFSET %s
        """, (f"%{search}%", f"%{search}%", per_page, offset))
    else:
        cursor.execute("""
            SELECT * FROM classes ORDER BY course_code LIMIT %s OFFSET %s
        """, (per_page, offset))

    all_classes = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('classes.html',
        classes=all_classes,
        search=search,
        page=page,
        per_page=per_page,
        user=session["user"],
        role=session.get("role")
    )

@app.route("/classes/add", methods=["POST"])
@login_required
def add_class():
    course_code = request.form["course_code"].strip()
    class_name  = request.form["class_name"].strip()

    if not course_code or not class_name:
        flash("Course code and class name are required.")
        return redirect(url_for("classes"))

    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO classes (course_code, class_name) VALUES (%s, %s)
        """, (course_code, class_name))
        conn.commit()
        cursor.close()
        conn.close()
        flash("Class added successfully.")
    except Exception as e:
        flash(f"Error: {e}")

    return redirect(url_for("classes"))

@app.route("/classes/<int:class_id>")
@login_required
def class_details(class_id):
    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM classes WHERE id = %s", (class_id,))
    selected_class = cursor.fetchone()

    if not selected_class:
        cursor.close()
        conn.close()
        flash("Class not found.")
        return redirect(url_for("classes"))

    cursor.execute("""
        SELECT COUNT(*) AS total FROM attendance_sessions WHERE class_id = %s
    """, (class_id,))
    total_sessions = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT sess.*,
               COUNT(CASE WHEN ar.status = 'Present' THEN 1 END) AS present_count
        FROM attendance_sessions sess
        LEFT JOIN attendance_records ar ON ar.session_id = sess.id
        WHERE sess.class_id = %s
        GROUP BY sess.id
        ORDER BY sess.date DESC, sess.start_time DESC
    """, (class_id,))
    past_sessions = cursor.fetchall()

    cursor.execute("""
        SELECT s.*,
               COUNT(ar.id) AS total_sessions,
               SUM(CASE WHEN ar.status = 'Present' THEN 1 ELSE 0 END) AS attended
        FROM class_students cs
        JOIN students s ON cs.student_id = s.id
        LEFT JOIN attendance_records ar ON ar.student_id = s.id
            AND ar.session_id IN (
                SELECT id FROM attendance_sessions WHERE class_id = %s
            )
        WHERE cs.class_id = %s
        GROUP BY s.id
        ORDER BY s.name
    """, (class_id, class_id))
    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("class_details.html",
        selected_class=selected_class,
        students=students,
        past_sessions=past_sessions,
        total_sessions=total_sessions,
        user=session["user"],
        role=session.get("role")
    )

@app.route("/classes/<int:class_id>/start", methods=["POST"])
@login_required
def start_class_session(class_id):
    session_name = request.form["session_name"].strip()
    session_date = request.form["session_date"]
    start_time   = request.form["start_time"]

    try:
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM classes WHERE id = %s", (class_id,))
        selected_class = cursor.fetchone()

        if not selected_class:
            cursor.close()
            conn.close()
            flash("Class not found.")
            return redirect(url_for("classes"))

        cursor.execute("""
            INSERT INTO attendance_sessions (session_name, date, start_time, end_time, class_id)
            VALUES (%s, %s, %s, NULL, %s)
        """, (session_name, session_date, start_time, class_id))

        session_id = cursor.lastrowid

        cursor.execute("""
            SELECT student_id FROM class_students WHERE class_id = %s
        """, (class_id,))
        enrolled_students = cursor.fetchall()

        for student in enrolled_students:
            cursor.execute("""
                INSERT INTO attendance_records
                (student_id, session_id, timestamp, recognition_confidence, status)
                VALUES (%s, %s, NOW(), NULL, 'Absent')
            """, (student["student_id"], session_id))

        conn.commit()
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

    return redirect(url_for("records", session_id=session_id))

# ──────────────────────────────────────────────
# ATTENDANCE SESSIONS
# ──────────────────────────────────────────────

@app.route("/sessions")
@login_required
def sessions():
    conn   = get_db_connection()
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

    return render_template("sessions.html",
        sessions=all_sessions,
        user=session["user"],
        role=session.get("role")
    )

@app.route("/sessions/delete/<int:id>", methods=["POST"])
@login_required
def delete_session(id):
    try:
        conn   = get_db_connection()
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
    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    selected_session      = request.args.get("session_id", "")
    status_filter         = request.args.get("status", "")
    search_query          = request.args.get("search", "").strip()
    page                  = int(request.args.get("page", 1))
    per_page              = 10
    offset                = (page - 1) * per_page
    attendance            = []
    selected_session_info = None
    selected_class        = None
    present_count         = 0
    absent_count          = 0

    if selected_session:
        cursor.execute("""
            SELECT sess.*, c.class_name, c.course_code, c.id AS class_id
            FROM attendance_sessions sess
            JOIN classes c ON sess.class_id = c.id
            WHERE sess.id = %s
        """, (selected_session,))
        selected_session_info = cursor.fetchone()
        selected_class        = selected_session_info

        if selected_session_info:
            class_id = selected_session_info["class_id"]

            query  = """
                SELECT ar.id AS record_id, s.student_id, s.name,
                       ar.timestamp, ar.recognition_confidence,
                       COALESCE(ar.status, 'Absent') AS status
                FROM class_students cs
                JOIN students s ON cs.student_id = s.id
                LEFT JOIN attendance_records ar
                    ON ar.student_id = s.id AND ar.session_id = %s
                WHERE cs.class_id = %s
            """
            params = [selected_session, class_id]

            if status_filter:
                query += " AND COALESCE(ar.status, 'Absent') = %s"
                params.append(status_filter)

            if search_query:
                query += " AND (s.student_id LIKE %s OR s.name LIKE %s)"
                params.extend([f"%{search_query}%", f"%{search_query}%"])

            query += " ORDER BY s.name LIMIT %s OFFSET %s"
            params.extend([per_page, offset])

            cursor.execute(query, tuple(params))
            attendance    = cursor.fetchall()
            present_count = sum(1 for a in attendance if a["status"] == "Present")
            absent_count  = sum(1 for a in attendance if a["status"] == "Absent")

    cursor.close()
    conn.close()

    return render_template("records.html",
        attendance=attendance,
        selected_session=selected_session,
        selected_session_info=selected_session_info,
        selected_class=selected_class,
        status_filter=status_filter,
        search_query=search_query,
        page=page,
        per_page=per_page,
        present_count=present_count,
        absent_count=absent_count,
        user=session["user"],
        role=session.get("role")
    )

@app.route("/records/<int:record_id>/update", methods=["POST"])
@login_required
def update_attendance_record(record_id):
    new_status = request.form["status"]

    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE attendance_records
        SET status = %s,
            timestamp = CASE WHEN %s = 'Present' THEN NOW() ELSE timestamp END
        WHERE id = %s
    """, (new_status, new_status, record_id))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Attendance status updated.")
    return redirect(request.referrer or url_for("records"))

# ──────────────────────────────────────────────
# STUDENT DASHBOARD
# ──────────────────────────────────────────────

@app.route("/student/dashboard")
@login_required
@student_onboarding_required
def student_dashboard():
    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Enrolled classes count
    cursor.execute("""
        SELECT COUNT(*) AS total FROM class_students
        WHERE student_id = %s
    """, (session["student_ref"],))
    enrolled_count = cursor.fetchone()["total"]

    # Attendance summary per class
    cursor.execute("""
        SELECT c.course_code, c.class_name,
               COUNT(ar.id) AS total_sessions,
               SUM(CASE WHEN ar.status = 'Present' THEN 1 ELSE 0 END) AS attended,
               ROUND(
                   SUM(CASE WHEN ar.status = 'Present' THEN 1 ELSE 0 END)
                   / NULLIF(COUNT(ar.id), 0) * 100, 1
               ) AS percentage
        FROM attendance_records ar
        JOIN attendance_sessions sess ON ar.session_id = sess.id
        JOIN classes c ON sess.class_id = c.id
        WHERE ar.student_id = %s
        GROUP BY c.id, c.course_code, c.class_name
        ORDER BY c.course_code
    """, (session["student_ref"],))
    class_summary = cursor.fetchall()

    # Overall totals
    total_sessions = sum(c["total_sessions"] or 0 for c in class_summary)
    total_attended = sum(c["attended"] or 0 for c in class_summary)     
    overall_percentage = round(
        (total_attended / total_sessions * 100), 1
    ) if total_sessions > 0 else 0

    cursor.close()
    conn.close()

    return render_template("student_home.html",
        enrolled_count=enrolled_count,
        class_summary=class_summary,
        total_sessions=total_sessions,
        total_attended=total_attended,
        overall_percentage=overall_percentage,
        user=session["user"],
        role=session.get("role")
    )

# ──────────────────────────────────────────────
# STUDENT PROFILE
# ──────────────────────────────────────────────

@app.route("/student/profile")
@login_required
def student_profile():
    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students WHERE id = %s", (session["student_ref"],))
    student = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template("student_profile.html",
        student=student,
        user=session["user"],
        role=session.get("role")
    )

@app.route("/student/profile/edit", methods=["GET", "POST"])
@login_required
def edit_student_profile():
    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        program = request.form["program"].strip()
        email   = request.form["email"].strip()

        cursor.execute("""
            UPDATE students SET program = %s, email = %s WHERE id = %s
        """, (program, email, session["student_ref"]))
        conn.commit()
        cursor.close()
        conn.close()

        flash("Profile updated successfully.")
        return redirect(url_for("student_profile"))

    cursor.execute("SELECT * FROM students WHERE id = %s", (session["student_ref"],))
    student = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template("edit_student_profile.html",
        student=student,
        user=session["user"],
        role=session.get("role")
    )

# ──────────────────────────────────────────────
# STUDENT FACE REGISTRATION
# ──────────────────────────────────────────────

@app.route("/student/register_face")
@login_required
def student_register_face():
    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    import cv2
    from deepface import DeepFace

    student_id = session["student_ref"]

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
    student = cursor.fetchone()

    if not student:
        cursor.close()
        conn.close()
        flash("Student not found.")
        return redirect(url_for("student_dashboard"))

    dataset_path = os.path.join("dataset", student['name'])
    os.makedirs(dataset_path, exist_ok=True)

    for old_img in os.listdir(dataset_path):
        old_path = os.path.join(dataset_path, old_img)
        if os.path.isfile(old_path):
            os.remove(old_path)

    cam = None
    for index in [2, 1, 0]:
        test = cv2.VideoCapture(index)
        if test.isOpened():
            cam = test
            print(f"[CAMERA] Face registration using camera index {index}")
            break
        test.release()

    if cam is None or not cam.isOpened():
        cursor.close()
        conn.close()
        flash("Camera could not be opened. Please check webcam connection.")
        return redirect(url_for("student_profile"))

    if not cam.isOpened():
        cursor.close()
        conn.close()
        flash("Camera could not be opened. Please check webcam connection.")
        return redirect(url_for("student_profile"))

    count      = 0
    max_images = 60

    pose_steps = [
        ("Look straight",              10),
        ("Turn slightly LEFT",          10),
        ("Turn slightly RIGHT",         10),
        ("Look slightly UP",            10),
        ("Look slightly DOWN",          10),
        ("Natural face / small smile",  10),
    ]

    current_step         = 0
    captured_in_step     = 0
    countdown_started    = False
    countdown_start_time = 0
    countdown_seconds    = 0.5

    while True:
        ret, frame = cam.read()
        if not ret:
            flash("Camera could not be opened.")
            break

        frame = cv2.flip(frame, 1)

        try:
            detected = DeepFace.extract_faces(
                img_path=frame,
                detector_backend="yunet",
                enforce_detection=False,
                align=True,
            )
            faces = [
                (f["facial_area"]["x"], f["facial_area"]["y"],
                 f["facial_area"]["w"], f["facial_area"]["h"])
                for f in detected if f.get("confidence", 0) >= 0.80
            ]
        except Exception:
            faces = []

        instruction_text = pose_steps[current_step][0]

        cv2.rectangle(frame, (0, 0), (frame.shape[1], 100), (30, 30, 30), -1)
        cv2.putText(frame, "UniAttend Face Registration",
            (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(frame, instruction_text,
            (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        cv2.rectangle(frame, (frame.shape[1]-200, 10), (frame.shape[1]-20, 60), (50, 205, 50), -1)
        cv2.putText(frame, f"{count}/{max_images}",
            (frame.shape[1]-170, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        progress_width = int((count / max_images) * frame.shape[1])
        cv2.rectangle(frame, (0, frame.shape[0]-18), (frame.shape[1], frame.shape[0]), (60, 60, 60), -1)
        cv2.rectangle(frame, (0, frame.shape[0]-18), (progress_width, frame.shape[0]), (50, 205, 50), -1)

        if len(faces) == 1:
            if not countdown_started:
                countdown_started    = True
                countdown_start_time = time.time()

            if time.time() - countdown_start_time >= countdown_seconds:
                for (x, y, w, h) in faces:
                    face_img = cv2.resize(frame[y:y+h, x:x+w], (200, 200))
                    cv2.imwrite(os.path.join(dataset_path, f"{count+1}.jpg"), face_img)

                    count            += 1
                    captured_in_step += 1

                    cv2.rectangle(frame, (x, y), (x+w, y+h), (50, 205, 50), 2)
                    cv2.putText(frame, f"Captured {count}/{max_images}",
                        (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (50, 205, 50), 2)
                    cv2.waitKey(200)

                countdown_started = False

                if captured_in_step >= pose_steps[current_step][1]:
                    current_step     += 1
                    captured_in_step  = 0
                    if current_step >= len(pose_steps):
                        break
        else:
            countdown_started = False
            warning = "No face detected" if len(faces) == 0 else "Only one face allowed"
            cv2.putText(frame, warning, (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        cv2.imshow("UniAttend Face Registration", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cam.release()
    cv2.destroyAllWindows()
    cv2.waitKey(1)
    cv2.destroyAllWindows()

    if count > 0:
        subprocess.run([sys.executable, "generate_embeddings.py"])
        cursor.execute("""
            UPDATE students SET face_registered = 1, face_status = 'Successful' WHERE id = %s
        """, (student_id,))
        conn.commit()
        flash(f"Face registration successful. {count} images captured.")
    else:
        cursor.execute("""
            UPDATE students SET face_registered = 0, face_status = 'Pending' WHERE id = %s
        """, (student_id,))
        conn.commit()
        flash("No face images captured. Please try again.")

    cursor.close()
    conn.close()
    return redirect(url_for("student_profile"))

# ──────────────────────────────────────────────
# STUDENT CLASSES & ENROLMENT
# ──────────────────────────────────────────────

@app.route('/student/classes', methods=['GET'])
@login_required
@student_onboarding_required
def student_classes():
    if session.get('role') != 'student':
        return redirect(url_for('dashboard'))

    search     = request.args.get('search', '')
    student_id = session["student_ref"]

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # All classes with enrolment status
    if search:
        cursor.execute("""
            SELECT c.*,
                   CASE WHEN cs.student_id IS NOT NULL THEN 1 ELSE 0 END AS enrolled
            FROM classes c
            LEFT JOIN class_students cs ON c.id = cs.class_id AND cs.student_id = %s
            WHERE c.class_name LIKE %s OR c.course_code LIKE %s
        """, (student_id, f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("""
            SELECT c.*,
                   CASE WHEN cs.student_id IS NOT NULL THEN 1 ELSE 0 END AS enrolled
            FROM classes c
            LEFT JOIN class_students cs ON c.id = cs.class_id AND cs.student_id = %s
        """, (student_id,))
    all_classes = cursor.fetchall()

    # Enrolled classes with attendance summary
    cursor.execute("""
        SELECT c.id, c.course_code, c.class_name,
               (SELECT COUNT(*) FROM attendance_sessions 
                WHERE class_id = c.id) AS total_sessions,
               SUM(CASE WHEN ar.status = 'Present' THEN 1 ELSE 0 END) AS attended,
               ROUND(
                   SUM(CASE WHEN ar.status = 'Present' THEN 1 ELSE 0 END)
                   / NULLIF((SELECT COUNT(*) FROM attendance_sessions 
                    WHERE class_id = c.id), 0) * 100, 1
               ) AS percentage
        FROM class_students cs
        JOIN classes c ON cs.class_id = c.id
        LEFT JOIN attendance_sessions sess ON sess.class_id = c.id
        LEFT JOIN attendance_records ar ON ar.session_id = sess.id AND ar.student_id = %s
        WHERE cs.student_id = %s
        GROUP BY c.id, c.course_code, c.class_name
        ORDER BY c.course_code
    """, (student_id, student_id))
    enrolled_classes = cursor.fetchall()

    # ALL sessions per enrolled class — no limit
    for ec in enrolled_classes:
        cursor.execute("""
            SELECT sess.session_name, sess.date,
                   ar.timestamp, ar.status
            FROM attendance_sessions sess
            LEFT JOIN attendance_records ar
                ON ar.session_id = sess.id AND ar.student_id = %s
            WHERE sess.class_id = %s
            ORDER BY sess.id DESC
        """, (student_id, ec["id"]))
        ec["sessions"] = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('student_classes.html',
        all_classes=all_classes,
        enrolled_classes=enrolled_classes,
        search=search,
        user=session["user"],
        role=session.get("role")
    )

@app.route('/student/enroll/<int:class_id>', methods=['POST'])
@login_required
@student_onboarding_required
def enroll_class(class_id):
    if session.get('role') != 'student':
        return redirect(url_for('dashboard'))

    student_id = session["student_ref"]

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM class_students WHERE class_id = %s AND student_id = %s
    """, (class_id, student_id))
    existing = cursor.fetchone()

    if existing:
        flash('You are already enrolled in this class.')
    else:
        cursor.execute("""
            INSERT INTO class_students (class_id, student_id) VALUES (%s, %s)
        """, (class_id, student_id))
        conn.commit()
        flash('Class enrolled successfully.')

    cursor.close()
    conn.close()
    return redirect(url_for('student_classes'))

@app.route('/student/unenroll/<int:class_id>', methods=['POST'])
@login_required
@student_onboarding_required
def unenroll_class(class_id):
    if session.get('role') != 'student':
        return redirect(url_for('dashboard'))

    student_id = session["student_ref"]

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        DELETE FROM class_students
        WHERE class_id = %s AND student_id = %s
    """, (class_id, student_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash('Successfully unenrolled from class.')
    return redirect(url_for('student_classes'))

# ──────────────────────────────────────────────
# RUN APP
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
