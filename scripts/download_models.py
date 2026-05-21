import os
from pathlib import Path
import urllib.request
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("download_models")

MODELS_DIR = Path("D:/Gopher Bot/gopher-bot/models")

def download_yolo():
    url = "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt"
    dest = MODELS_DIR / "yolov8n.pt"
    if not dest.exists():
        logger.info(f"Downloading YOLOv8n to {dest}...")
        urllib.request.urlretrieve(url, str(dest))
        logger.info("YOLOv8n downloaded.")
    else:
        logger.info("YOLOv8n already exists.")

def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Checking models in {MODELS_DIR}")
    
    download_yolo()
    
    # EasyOCR and MediaPipe handle their own downloads natively, 
    # but we can pre-fetch them here if needed in the future.
    logger.info("Done.")

if __name__ == "__main__":
    main()
