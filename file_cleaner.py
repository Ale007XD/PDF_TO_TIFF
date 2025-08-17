import os
from datetime import datetime
import shutil
import dotenv
dotenv.load_dotenv()
PUBLISH_DIR = os.getenv("PUBLISH_DIR", "/srv/files")
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", 14))

now = datetime.now()
if not os.path.isdir(PUBLISH_DIR):
    print(f"Папка {PUBLISH_DIR} не найдена")
    exit(0)

for folder in os.listdir(PUBLISH_DIR):
    full = os.path.join(PUBLISH_DIR, folder)
    if not os.path.isdir(full):
        continue
    try:
        date = datetime.strptime(folder, "%Y_%m_%d")
        if (now - date).days > RETENTION_DAYS:
            shutil.rmtree(full)
            print(f"Удалена просроченная папка: {full}")
    except Exception as e:
        print(f"Ошибка обработки {full}: {e}")
        continue
