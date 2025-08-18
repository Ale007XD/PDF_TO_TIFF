import asyncio
import os
import uuid
import shutil
import logging
from concurrent.futures import ProcessPoolExecutor

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage

# Эти функции должны быть в ваших файлах utils.py и pdf_to_tiff.py
from pdf_to_tiff import process_pdf
from utils import is_safe_filename, get_file_size_mb

# --- 1. Настройка логирования ---
# Логи будут выводиться в консоль Docker и помогут в отладке
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- 2. Загрузка переменных окружения ---
# Код останавливается, если BOT_TOKEN не найден
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Критическая ошибка: переменная окружения BOT_TOKEN не задана.")

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost")
PUBLISH_DIR = os.environ.get("PUBLISH_DIR", "/app/published")
TMP_DIR = os.environ.get("TMP_DIR", "/app/temp")
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "100"))
DPI_DEFAULT = int(os.environ.get("DPI_DEFAULT", "96"))
GS_PATH = os.environ.get("GS_PATH", "/usr/bin/gs")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "2"))

# --- 3. Инициализация бота и диспетчера ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
executor = ProcessPoolExecutor(CONCURRENCY)

# --- Тексты для команд ---
HELP_TEXT = (
    "Бот принимает одностраничные PDF (CMYK в кривых) и возвращает TIFF (CMYK+LZW, 96 DPI) и ссылку на скачивание.\n\n"
    "Ограничения:\n"
    "- Только одностраничные PDF\n"
    "- Только CMYK-контент\n"
    f"- Лимит файла: {MAX_FILE_MB}MB\n"
    "- После 14 дней файл удаляется\n\n"
    "Внимание!\nCMYK TIFF может отображаться некорректно в некоторых просмотрщиках. "
    "Это не ошибка: используйте профессиональные редакторы!"
)

START_TEXT = (
    "Отправьте одностраничный PDF, я конвертирую его в TIFF (CMYK+LZW, 96 DPI) и дам прямую ссылку на скачивание."
)

# --- 4. Обработчики команд ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(START_TEXT)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(HELP_TEXT)

# --- 5. Основной обработчик документов ---
@dp.message(lambda m: m.document is not None)
async def handle_doc(message: types.Message):
    doc = message.document
    filename = doc.file_name
    size_mb = get_file_size_mb(doc)

    if not is_safe_filename(filename) or not filename.lower().endswith('.pdf'):
        await message.answer("Файл должен быть PDF и с валидным именем.")
        return

    if size_mb > MAX_FILE_MB:
        await message.answer(f"Размер файла превышает лимит {MAX_FILE_MB}MB.")
        return

    await message.answer("✅ Файл получен, начинаю обработку...")

    u = str(uuid.uuid4())
    tmp_dir = os.path.join(TMP_DIR, u)
    src_pdf_path = os.path.join(tmp_dir, "input.pdf")

    try:
        logging.info(f"Создаю временную директорию: {tmp_dir}")
        os.makedirs(tmp_dir, exist_ok=True)

        logging.info(f"Скачиваю файл в: {src_pdf_path}")
        await bot.download(doc, destination=src_pdf_path)

        # Проверка, что файл действительно был сохранен
        if not os.path.exists(src_pdf_path) or os.path.getsize(src_pdf_path) == 0:
            logging.error(f"Файл НЕ СОХРАНЕН или пуст по пути: {src_pdf_path}")
            await message.answer("❌ **Критическая ошибка:** не удалось сохранить файл на сервере. Обработка невозможна.")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return

        logging.info(f"Файл успешно сохранен. Размер: {os.path.getsize(src_pdf_path)} байт. Передаю в обработчик...")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            process_pdf,
            src_pdf_path, filename, tmp_dir, PUBLISH_DIR, PUBLIC_BASE_URL, GS_PATH, DPI_DEFAULT
        )

        success, user_msg, tiff_path, public_url, file_size, stderr = result

        if not success:
            logging.error(f"Ошибка обработки: {user_msg}\n stderr: {stderr}")
            await message.answer(user_msg + (f"\n> {stderr}" if stderr else ""))
            return

        mb = file_size / 1024 / 1024
        txt = f"Файл готов: {public_url}\nРазмер: {mb:.2f}MB"

        if mb <= 50:
            await message.answer_document(FSInputFile(tiff_path), caption=txt)
        else:
            await message.answer(txt)

    except Exception as e:
        logging.exception("Произошла непредвиденная ошибка в процессе обработки файла:")
        await message.answer(f"Произошла ошибка: {e}")
    finally:
        # Гарантированная очистка временных файлов
        logging.info(f"Очищаю временную директорию: {tmp_dir}")
        shutil.rmtree(tmp_dir, ignore_errors=True)


# --- 6. Точка входа ---
if __name__ == "__main__":
    # Создаем необходимые директории при старте
    os.makedirs(TMP_DIR, exist_ok=True)
    os.makedirs(PUBLISH_DIR, exist_ok=True)
    
    logging.info("Бот запускается...")
    try:
        asyncio.run(dp.start_polling(bot))
    except KeyboardInterrupt:
        print("\nБот остановлен пользователем.")
    finally:
        executor.shutdown(wait=True)
        logging.info("Бот остановлен.")
