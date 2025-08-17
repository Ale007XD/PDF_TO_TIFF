import os
from datetime import datetime, timedelta
import shutil

PUBLISH_DIR = "/srv/files"
RETENTION_DAYS = 14

now = datetime.now()

for folder in os.listdir(PUBLISH_DIR):
    full = os.path.join(PUBLISH_DIR, folder)
    if not os.path.isdir(full): continue
    try:
        date = datetime.strptime(folder, "%Y_%m_%d")
        if (now - date).days > RETENTION_DAYS:
            shutil.rmtree(full)
            print(f"Удалена просроченная папка: {full}")
    except Exception:
        continue
