from PIL import Image
import os

dataset_path = "dataset"

bad_files = []

for person_name in os.listdir(dataset_path):
    person_path = os.path.join(dataset_path, person_name)

    if not os.path.isdir(person_path):
        continue

    for image_name in os.listdir(person_path):
        image_path = os.path.join(person_path, image_name)

        try:
            with Image.open(image_path) as img:
                img.verify()
            print(f"OK: {image_path}")
        except Exception as e:
            print(f"BAD: {image_path} -> {e}")
            bad_files.append(image_path)

print("\nScan complete.")
print(f"Total bad files: {len(bad_files)}")