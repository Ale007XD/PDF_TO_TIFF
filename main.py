#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import os
import subprocess
import uuid
import magic
import filetype
import shutil

from concurrent.futures import ProcessPoolExecutor
from dotenv import load_dotenv
from pathlib import Path
from aiogram import Bot, Dispatcher, types, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile
from tqdm import tqdm
import traceback
from PyPDF2 import PdfReader
import aiohttp
import re

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'https://localhost')
PUBLISH_DIR = os.getenv('PUBLISH_DIR', '/srv/files')
TMP_DIR = os.getenv('TMP_DIR', '/tmp/bot')

def safe_int_env(name, default):
    val = os.getenv(name)
    try:
        return int(val) if val and val.strip() else default
    except Exception:
        return default

MAX_FILE_MB = safe_int_env('MAX_FILE_MB', 100)
IMAGEMAGICK_PATH = os.getenv('IMAGEMAGICK_PATH', '/usr/bin/convert')
ICC_CMYK_PROFILE = os.getenv('ICC_CMYK_PROFILE', '/usr/share/color/icc/CMYK.icc')
CONCURRENCY = safe_int_env('CONCURRENCY', 2)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

Path(PUBLISH_DIR).mkdir(parents=True, exist_ok=True)
Path(TMP_DIR).mkdir(parents=True, exist_ok=True)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
executor = ProcessPoolExecutor(max_workers=CONCURRENCY)

CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002868181428"))  # Укажите ваш channel ID (-100XXXXXXXXXX)
PDF_LINK_PATTERN = r"(https?://[^\s]+\.pdf)"

async def log_and_reply(msg, user, orig_msg=None):
    logger.info(f"[USER {user}] {msg}")
    if orig_msg:
        await orig_msg.answer(msg)

def validate_pdf_file(file_path: str) -> tuple[bool, str]:
    try:
        logger.info(f"Проверка MIME файла (python-magic): {file_path}")
        mime_type = magic.from_file(file_path, mime=True)
        logger.info(f"MIME результат: {mime_type}")
        if mime_type != 'application/pdf':
            return False, f"Тип MIME не PDF, а {mime_type}"
        logger.info("Доп. проверка через filetype")
        kind = filetype.guess(file_path)
        logger.info(f"filetype: {kind}")
        if kind is None or kind.mime != 'application/pdf':
            return False, "filetype: не PDF"
        logger.info("Проверка через PyPDF2")
        try:
            with open(file_path, "rb") as f:
                PdfReader(f)
        except Exception as e:
            logger.error(f"PyPDF2 не может прочитать файл: {e}")
            return False, f"PyPDF2: не читается (поврежден/защищен?) {e}"
        return True, "PDF файл валиден"
    except Exception as e:
        logger.error(f"Ошибка валидации: {e}")
        return False, f"Ошибка валидации: {e}"

def count_pdf_pages(file_path: str) -> tuple[int, str]:
    gs_cmd = [
        "/usr/bin/gs", "-q", "-dNODISPLAY", "-c",
        f"({file_path}) (r) file runpdfbegin pdfpagecount = quit"
    ]
    logger.info(f"Вызов GhostScript для подсчета страниц: {gs_cmd}")
    try:
        result = subprocess.run(
            gs_cmd, check=True, timeout=20,
            capture_output=True, text=True
        )
        logger.info(f"GhostScript STDOUT: {result.stdout}")
        try:
            count = int(result.stdout.strip().split('\n')[-1])
            logger.info(f"PDF pages by GhostScript: {count}")
            return count, ""
        except Exception as e:
            logger.error(f"Ошибка парсинга stdout GhostScript: {e}, raw: {result.stdout}")
            return -1, f"Не удалось определить число страниц: {e}, output={result.stdout}"
    except subprocess.CalledProcessError as ee:
        logger.error(f"GhostScript ошибка: {ee.stderr}\nTraceback: {traceback.format_exc()}")
        return -1, f"GhostScript ошибка: {ee.stderr}"
    except Exception as e:
        logger.error(f"GhostScript другая ошибка: {e}\nTraceback: {traceback.format_exc()}")
        return -1, f"GhostScript: {e}"

def convert_pdf_to_tiff(input_file: str, output_file: str) -> tuple[bool, str]:
    try:
        logger.info(f"Конвертация PDF в TIFF через ImageMagick: {input_file} -> {output_file}")
        cmd = [
            IMAGEMAGICK_PATH, '-density', '96', input_file,
            '-colorspace', 'CMYK', '-compress', 'LZW',
            '-units', 'PixelsPerInch', '-resample', '96', '-strip', output_file
        ]
        if os.path.exists(ICC_CMYK_PROFILE):
            cmd.insert(-1, '-profile')
            cmd.insert(-1, ICC_CMYK_PROFILE)
        logger.info(f"Команда ImageMagick: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, check=True, timeout=300,
            capture_output=True, text=True
        )
        logger.info(f"[ImageMagick] STDOUT: {result.stdout}")
        logger.info(f"[ImageMagick] STDERR: {result.stderr}")
        if os.path.exists(output_file):
            logger.info("Выходной файл создан.")
            return True, "Конвертация завершена"
        else:
            logger.error("ImageMagick не создал выходной файл")
            return False, "ImageMagick не создал выходной файл"
    except subprocess.TimeoutExpired:
        logger.error("Timeout ImageMagick 5 min")
        return False, "ImageMagick: превышено время ожидания (5 мин)"
    except subprocess.CalledProcessError as e:
        logger.error(f"ImageMagick ошибка: {e.stderr}")
        return False, f"ImageMagick ошибка: {e.stderr}"
    except Exception as e:
        logger.error(f"Исключение ImageMagick: {e}\n{traceback.format_exc()}")
        return False, f"Ошибка: {e}"

@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    await log_and_reply("Получена команда /start", message.from_user.id)
    await message.answer(
        "Отправьте PDF-файл — я сконвертирую его в TIFF (CMYK, LZW, 96 DPI) и верну прямую ссылку на скачивание."
    )

@dp.message(Command("help"))
async def help_handler(message: Message) -> None:
    await log_and_reply("Получена команда /help", message.from_user.id)
    await message.answer(
        "Бот принимает только PDF-документы размером до 100МБ. Конвертация — TIFF LZW, CMYK.\n"
        "Если PDF многостраничный — получится мульти-TIFF. "
        "Бот вернет вам прямую ссылку для скачивания."
    )

@dp.message()
async def document_handler(message: Message) -> None:
    user_id = message.from_user.id
    try:
        await log_and_reply("Принято сообщение, обработка...", user_id)
        if not getattr(message, 'document', None):
            await log_and_reply("Нет документа в сообщении", user_id, message)
            return
        document = message.document
        await log_and_reply(f"Документ: {document.file_name}, MIME: {document.mime_type}, size: {document.file_size}", user_id)
        if document.mime_type != 'application/pdf':
            await log_and_reply(f"Файл не PDF: {document.mime_type}", user_id, message)
            return
        file_size_mb = document.file_size / (1024 * 1024)
        if file_size_mb > MAX_FILE_MB:
            await log_and_reply(f"Файл слишком большой: {file_size_mb:.1f} МБ", user_id, message)
            return

        work_id = str(uuid.uuid4())
        work_dir = Path(TMP_DIR) / work_id
        work_dir.mkdir(exist_ok=True)
        input_file = work_dir / 'input.pdf'
        base_name = (document.file_name.rsplit('.', 1)[0] if document.file_name else 'converted')
        output_filename = f"{base_name}.tiff"
        output_file = work_dir / 'output.tiff'
        final_file = Path(PUBLISH_DIR) / output_filename

        status_msg = await message.answer(f"Файл получен, начинаю загрузку и проверки...")
        file_info = await bot.get_file(document.file_id)
        await bot.download_file(file_info.file_path, input_file)
        logger.info(f"Файл сохранен во временную папку: {input_file}")

        is_valid, validation_msg = validate_pdf_file(str(input_file))
        logger.info(f"Результат валидации PDF: {is_valid} — {validation_msg}")
        if not is_valid:
            await log_and_reply(f"Валидация не пройдена: {validation_msg}", user_id, status_msg)
            return

        page_count, gs_error = count_pdf_pages(str(input_file))
        if page_count == -1:
            await log_and_reply(f"Ошибка при проверке количества страниц. Проверьте PDF. {gs_error}", user_id, status_msg)
            return

        await status_msg.edit_text(f"Файл прошёл проверки, конвертирую в TIFF (страниц: {page_count})...")

        loop = asyncio.get_event_loop()
        success, error_msg = await loop.run_in_executor(
            executor, convert_pdf_to_tiff, str(input_file), str(output_file)
        )
        if not success:
            await log_and_reply(f"Ошибка конвертации: {error_msg}", user_id, status_msg)
            return

        if output_file.exists():
            shutil.move(str(output_file), str(final_file))
            output_size_mb = final_file.stat().st_size / (1024 * 1024)
            link = f"{PUBLIC_BASE_URL}/files/{output_filename}"
            if final_file.stat().st_size < 10*1024:
                await status_msg.edit_text(
                  f"TIFF успешно создан, но очень мал по размеру (<10КБ): {output_filename}\n"
                  f"Проверьте исходный PDF. Ссылка: {link}"
                )
                logger.warning(f"TIFF-файл слишком мал: {final_file.stat().st_size} байт")
            else:
                await status_msg.edit_text(
                    f"Готово! Ссылка: {link}\n"
                    f"Размер: {output_size_mb:.1f} МБ"
                )
                logger.info(f"Конвертация завершена {document.file_name} -> {output_filename} ({output_size_mb:.1f} МБ)")
        else:
            await log_and_reply("Файл не найден после конвертации", user_id, status_msg)
    except Exception as e:
        err = traceback.format_exc()
        logger.error(f"UNCAUGHT EXCEPTION [{user_id}] {e}\n{err}")
        await message.answer(f"❌ Внутренняя ошибка: {e}")
    finally:
        try:
            if 'work_dir' in locals() and work_dir.exists():
                for f in work_dir.rglob('*'):
                    if f.is_file():
                        f.unlink()
                work_dir.rmdir()
        except Exception as e:
            logger.warning(f"Ошибка очистки временной папки: {e}")

# === КАНАЛ-ФУНКЦИЯ ===

@dp.message(lambda m: m.chat.id == CHANNEL_ID and m.text and re.search(PDF_LINK_PATTERN, m.text))
async def channel_pdf_handler(message: Message):
    pdf_links = re.findall(PDF_LINK_PATTERN, message.text)
    for pdf_url in pdf_links:
        tempdir = Path(TMP_DIR) / str(uuid.uuid4())
        tempdir.mkdir(exist_ok=True)
        input_file = tempdir / "input.pdf"
        output_file = tempdir / "output.tiff"
        filename = pdf_url.split("/")[-1]
        output_filename = filename.rsplit(".", 1)[0] + ".tiff"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(pdf_url) as resp:
                    content = await resp.read()
                    input_file.write_bytes(content)
            logger.info(f"Скачан PDF из канала: {pdf_url}")

            valid, msg = validate_pdf_file(str(input_file))
            if not valid:
                await bot.send_message(message.chat.id, f"❌ Ошибка PDF: {msg}")
                continue

            loop = asyncio.get_event_loop()
            success, err = await loop.run_in_executor(executor, convert_pdf_to_tiff, str(input_file), str(output_file))
            if not success:
                await bot.send_message(message.chat.id, f"❌ Не удалось сконвертировать PDF: {err}")
                continue

            if output_file.exists() and output_file.stat().st_size > 1024:
                await bot.send_document(message.chat.id, FSInputFile(str(output_file), filename=output_filename))
            else:
                await bot.send_message(message.chat.id, "❌ TIFF-файл слишком мал или не создан")
        except Exception as e:
            logger.error(f"[КАНАЛ] Ошибка: {e}")
            await bot.send_message(message.chat.id, f"❌ Ошибка обработки PDF: {e}")
        finally:
            try:
                for f in tempdir.rglob('*'):
                    if f.is_file():
                        f.unlink()
                tempdir.rmdir()
            except Exception:
                pass

async def main():
    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
