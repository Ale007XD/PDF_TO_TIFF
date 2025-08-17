import asyncio
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

# Основные переменные загружаются из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
PUBLISH_DIR = os.getenv("PUBLISH_DIR")
TMP_DIR = os.getenv("TMP_DIR")
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", 100))
DPI_DEFAULT = int(os.getenv("DPI_DEFAULT", 96))
GS_PATH = os.getenv("GS_PATH", "/usr/bin/gs")
CONCURRENCY = int(os.getenv("CONCURRENCY", 2))

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
    "CMYK TIFF может отображаться некорректно в некоторых просмотрщиках (особенно старые Windows/Preview/Photos). Это не ошибка: используйте профессиональные редакторы!"
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
