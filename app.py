from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector

app = Flask(__name__)
app.secret_key = "secret123"

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",   # put your MySQL password here if you have one
        database="face_attendance_db"
    )

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/test_db")
def test_db():
    try:
        conn = get_db_connection()
        conn.close()
        return "Database connected successfully!"
    except Exception as e:
        return f"Database connection failed: {e}"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            query = "SELECT * FROM users WHERE username = %s AND password = %s"
            cursor.execute(query, (username, password))
            user = cursor.fetchone()

            cursor.close()
            conn.close()

            if user:
                return f"Login successful. Welcome, {user['username']}!"
            else:
                flash("Invalid username or password.")

        except Exception as e:
            flash(f"Database error: {e}")

    return render_template("login.html")

if __name__ == "__main__":
    app.run(debug=True)