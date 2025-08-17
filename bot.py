import asyncio
import os
import uuid
import shutil
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from pdf_to_tiff import process_pdf
from utils import is_safe_filename, get_file_size_mb
from concurrent.futures import ProcessPoolExecutor

# Безопасная загрузка переменных окружения
load_dotenv()  # .env (БЕЗ required, т.к. prefer env for production)

# Чтение токена из переменных окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "Переменная окружения BOT_TOKEN не установлена!\n"
        "1. Убедитесь, что она передана через docker-compose.yml или в файле .env\n"
        "2. Для Docker Compose используйте:\n"
        "   environment:\n"
        "     - BOT_TOKEN=ваш_бот_токен\n"
        "3. Для GitHub Actions секрет должен называться BOT_TOKEN и быть актуальным!\n"
        "4. Проверьте отсутствие пробелов и кавычек в начале/конце."
    )

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL")
PUBLISH_DIR = os.environ.get("PUBLISH_DIR", "/app/published")
TMP_DIR = os.environ.get("TMP_DIR", "/app/temp")
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", 100))
DPI_DEFAULT = int(os.environ.get("DPI_DEFAULT", 96))
GS_PATH = os.environ.get("GS_PATH", "/usr/bin/gs")
CONCURRENCY = int(os.environ.get("CONCURRENCY", 2))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
executor = ProcessPoolExecutor(CONCURRENCY)

HELP_TEXT = (
    "Бот принимает одностраничные PDF (CMYK в кривых) "
    "и возвращает TIFF (CMYK+LZW, 96 DPI) и ссылку на скачивание.\n\n"
    "Ограничения:\n"
    "- Только одностраничные PDF\n"
    "- Только CMYK-контент\n"
    "- Лимит файла: 100MB\n"
    "- После 14 дней файл удаляется\n\n"
    "Внимание!\n"
    "CMYK TIFF может отображаться некорректно в некоторых просмотрщиках (особенно старые Windows/Preview/Photos). "
    "Это не ошибка: используйте профессиональные редакторы!"
)

START_TEXT = (
    "Отправьте одностраничный PDF, я конвертирую его "
    "в TIFF (CMYK+LZW, 96 DPI) и дам прямую ссылку на скачивание."
)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(START_TEXT)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(HELP_TEXT)

@dp.message(lambda m: m.document is not None)
async def handle_doc(message: types.Message):
    doc = message.document
    filename = doc.file_name
    size_mb = get_file_size_mb(doc)

    # Проверка имени и расширения
    if not is_safe_filename(filename) or not filename.lower().endswith('.pdf'):
        await message.answer("Файл должен быть PDF и с валидным именем.")
        return
    # Проверка размера
    if size_mb > MAX_FILE_MB:
        await message.answer(f"Размер файла превышает лимит {MAX_FILE_MB}MB.")
        return
    await message.answer("Файл получен, конвертирую...")

    # Уникальная рабочая папка в TMP для изоляции
    u = str(uuid.uuid4())
    tmp_dir = os.path.join(TMP_DIR, u)
    os.makedirs(tmp_dir, exist_ok=True)
    src_pdf_path = os.path.join(tmp_dir, "input.pdf")
    await bot.download(doc, src_pdf_path)
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            process_pdf,
            src_pdf_path, filename, tmp_dir, PUBLISH_DIR, PUBLIC_BASE_URL, GS_PATH, DPI_DEFAULT
        )
    except Exception as e:
        await message.answer(f"Ошибка при конвертации: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return
    # result: (success, msg, tiff_path, url, size, stderr)
    success, user_msg, tiff_path, public_url, file_size, stderr = result
    if not success:
        await message.answer(user_msg + (f"\n> {stderr}" if stderr else ""))
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return
    # Логика выдачи файла или ссылки
    mb = file_size / 1024/1024
    txt = f"Файл готов: {public_url}\nРазмер: {mb:.2f}MB"
    if mb <= 50:
        try:
            await message.answer_document(FSInputFile(tiff_path), caption=txt)
        except Exception:
            await message.answer(txt)
    else:
        await message.answer(txt)
    shutil.rmtree(tmp_dir, ignore_errors=True)

if __name__ == "__main__":
    os.makedirs(TMP_DIR, exist_ok=True)
    os.makedirs(PUBLISH_DIR, exist_ok=True)
    try:
        asyncio.run(dp.start_polling(bot))
    except KeyboardInterrupt:
        print("\nБот остановлен пользователем")
    finally:
        executor.shutdown(wait=True)
