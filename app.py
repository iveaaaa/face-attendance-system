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
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid username or password.")
        except Exception as e:
            flash(f"Database error: {e}")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
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
        user=session["user"]
    )

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
    return render_template("students.html", students=all_students, user=session["user"])

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
        cursor.execute("INSERT INTO students (name, student_id) VALUES (%s, %s)", (name, student_id_str))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Student '{name}' added successfully.")
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
    return render_template("sessions.html", sessions=all_sessions, user=session["user"])

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
        user=session["user"]
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
        user=session["user"]
    )

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
