from werkzeug.security import generate_password_hash
import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="face_attendance_db"
)
cursor = conn.cursor()
cursor.execute("""
    INSERT INTO users (username, password, role, must_change_password)
    VALUES (%s, %s, 'educator', 0)
""", ("admin", generate_password_hash("Admin123")))
conn.commit()
cursor.close()
conn.close()
print("Educator account created! Username: admin | Password: Admin123")