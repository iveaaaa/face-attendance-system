import cv2
import os

student_name = input("Enter student name: ").strip()

folder_path = os.path.join("dataset", student_name)
os.makedirs(folder_path, exist_ok=True)

cap = cv2.VideoCapture(0)
count = 1

print("Press 's' to save image")
print("Press 'q' to quit")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to access webcam.")
        break

    cv2.imshow("Face Capture", frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('s'):
        img_name = f"img{count}.jpg"
        img_path = os.path.join(folder_path, img_name)
        cv2.imwrite(img_path, frame)
        print(f"Saved: {img_path}")
        count += 1

    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()