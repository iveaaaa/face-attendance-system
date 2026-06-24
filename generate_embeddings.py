import os
from deepface import DeepFace

DATASET_PATH     = "dataset"
MODEL_NAME       = "ArcFace"
DETECTOR_BACKEND = "yunet"
DISTANCE_METRIC  = "cosine"

def build_embeddings():
    print("=" * 50)
    print("  UniAttend — ArcFace Embedding Builder")
    print("=" * 50)

    # Check dataset exists and has folders
    if not os.path.exists(DATASET_PATH):
        print(f"ERROR: dataset folder not found at '{DATASET_PATH}'")
        return

    persons = [
        p for p in os.listdir(DATASET_PATH)
        if os.path.isdir(os.path.join(DATASET_PATH, p))
    ]

    if not persons:
        print("ERROR: No person folders found in dataset/")
        return

    print(f"Found {len(persons)} person(s): {', '.join(persons)}")
    print(f"Building ArcFace embeddings — please wait...")
    print("(This may take 1-2 minutes on first run, instant after)")
    print()

    # Find a sample image to trigger embedding build
    sample_img = None
    for person in persons:
        person_path = os.path.join(DATASET_PATH, person)
        images = [
            f for f in os.listdir(person_path)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ]
        if images:
            sample_img = os.path.join(person_path, images[0])
            break

    if not sample_img:
        print("ERROR: No images found in dataset folders.")
        return

    try:
        # This call builds and caches the embeddings pkl file
        DeepFace.find(
            img_path         = sample_img,
            db_path          = DATASET_PATH,
            model_name       = MODEL_NAME,
            detector_backend = DETECTOR_BACKEND,
            distance_metric  = DISTANCE_METRIC,
            enforce_detection= False,
            silent           = False,
        )

        print()
        print("=" * 50)
        print("  Embeddings built successfully!")
        print(f"  Persons registered : {len(persons)}")
        print(f"  Model              : {MODEL_NAME}")
        print(f"  Detector           : {DETECTOR_BACKEND}")
        print(f"  Cache file         : dataset/representations_arcface.pkl")
        print("=" * 50)

    except Exception as e:
        print(f"ERROR building embeddings: {e}")


if __name__ == "__main__":
    build_embeddings()