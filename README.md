# UniAttend — Face Recognition Attendance System

A web-based automated attendance system using deep learning face recognition.
Built with Flask, OpenCV, DeepFace (YuNet + ArcFace), and MySQL.

---

## System Requirements

- Python 3.10 or 3.11
- MySQL (Laragon recommended)
- Webcam (720p minimum)
- Internet connection (first run only — downloads ArcFace model ~100MB)

---

## Technology Stack

| Component        | Technology                  |
|------------------|-----------------------------|
| Backend          | Python, Flask               |
| Frontend         | HTML, CSS, Jinja2           |
| Database         | MySQL                       |
| Face Detection   | YuNet (via DeepFace)        |
| Face Recognition | ArcFace (via DeepFace)      |
| Video Capture    | OpenCV                      |

---

## Installation

### 1. Clone or extract the project
```
cd face_attendance_system
```

### 2. Create and activate virtual environment
```
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies
```
pip install -r requirements.txt
```

### 4. Set up the database
- Start Laragon and ensure MySQL is running
- Open phpMyAdmin at `http://localhost/phpmyadmin`
- Create a new database named `face_attendance_db`
- Select `face_attendance_db` → Import → select `face_attendance_db.sql` → Go

### 5. Create educator account
Run this once before first use:
```
python create_educator.py
```
Default credentials:
- Username: `admin`
- Password: `Admin123`

### 6. Run the system
```
python app.py
```

### 7. Open in browser
```
http://127.0.0.1:5000
```

---

## First Run Note

On first run, DeepFace will automatically download the ArcFace model weights (~100MB).
This is a one-time process requiring an internet connection.
Model is cached at: `C:\Users\<username>\.deepface\weights\`

---

## How to Use

### Educator:
1. Login with educator credentials (admin / Admin123)
2. Add classes under Classes menu
3. Navigate to Classes → View Details → Start Now to begin attendance
4. Face recognition runs automatically via webcam
5. Press Q to stop the session
6. View attendance records from Class Details → View Records

### Student:
1. Self-register via the Sign Up page using your Student ID
2. Complete your profile (program and email)
3. Register face under Profile → Register Face
4. Follow the six pose instructions during registration
5. Enrol into available classes under Classes menu
6. View personal attendance records and class-by-class breakdown under Classes

---

## Face Recognition Pipeline

```
Webcam Frame
    ↓
OpenCV (frame capture)
    ↓
YuNet via DeepFace (face detection)
    ↓
ArcFace via DeepFace (face recognition)
    ↓
MySQL (attendance marking)
    ↓
Flask (web application)
```

---

## Dataset

- Each student registers 60 face images during onboarding
- Images captured across 6 pose variations (straight, left, right, up, down, smile)
- Stored in `dataset/<student_name>/` as colour RGB JPG images
- ArcFace embeddings cached in `dataset/representations_arcface.pkl`
- Dataset folder is excluded from repository — run face registration for each student before use

---

## Project Structure

```
face_attendance_system/
├── app.py                      # Main Flask application
├── recognize_faces.py          # YuNet detection + ArcFace recognition
├── generate_embeddings.py      # ArcFace embedding generation
├── create_educator.py          # One-time educator account setup
├── face_attendance_db.sql      # Database schema
├── requirements.txt            # Python dependencies
├── README.md                   # Project documentation
├── .gitignore                  # Git ignore rules
├── dataset/                    # Student face images (excluded from repo)
├── templates/                  # HTML templates
└── static/                     # CSS and image assets
```

---

## Notes

- `venv/` is excluded — recreate using `pip install -r requirements.txt`
- `dataset/` is excluded — collect face images via the face registration interface
- ArcFace model weights download automatically on first run (~100MB)
- Optimal recognition distance: 1 to 3 metres from webcam
- Ensure good lighting during face registration and attendance sessions
- Recommended: 60 face images per student across 6 pose variations
- Recognition performance may degrade if students wear hoodies or head coverings
