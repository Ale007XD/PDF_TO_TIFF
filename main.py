#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import os
import subprocess
import uuid
import magic
import filetype
from concurrent.futures import ProcessPoolExecutor
from dotenv import load_dotenv
from pathlib import Path
from aiogram import Bot, Dispatcher, types, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile
from tqdm import tqdm

# Загружаем переменные окружения
load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'https://localhost')
PUBLISH_DIR = os.getenv('PUBLISH_DIR', '/srv/files')
TMP_DIR = os.getenv('TMP_DIR', '/tmp/bot')
MAX_FILE_MB = int(os.getenv('MAX_FILE_MB', '100'))
IMAGEMAGICK_PATH = os.getenv('IMAGEMAGICK_PATH', '/usr/bin/convert')
ICC_CMYK_PROFILE = os.getenv('ICC_CMYK_PROFILE', '/usr/share/color/icc/CMYK.icc')
CONCURRENCY = int(os.getenv('CONCURRENCY', '2'))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создаем необходимые директории
Path(PUBLISH_DIR).mkdir(parents=True, exist_ok=True)
Path(TMP_DIR).mkdir(parents=True, exist_ok=True)

# Инициализация бота
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Пул для выполнения конвертации
executor = ProcessPoolExecutor(max_workers=CONCURRENCY)

def convert_pdf_to_tiff(input_file: str, output_file: str) -> tuple[bool, str]:
    """
    Конвертирует PDF в TIFF используя ImageMagick
    Возвращает (успех, сообщение об ошибке)
    """
    try:
        # Команда для конвертации
        cmd = [
            IMAGEMAGICK_PATH,
            '-density', '96',
            input_file,
            '-colorspace', 'CMYK',
            '-compress', 'LZW',
            '-units', 'PixelsPerInch',
            '-resample', '96',
            '-strip',
            output_file
        ]
        
        # Если есть ICC профиль, используем его
        if os.path.exists(ICC_CMYK_PROFILE):
            cmd.insert(-1, '-profile')
            cmd.insert(-1, ICC_CMYK_PROFILE)
        
        logger.info(f"Executing: {' '.join(cmd)}")
        
        # Выполняем команду с таймаутом
        result = subprocess.run(
            cmd,
            check=True,
            timeout=300,
            capture_output=True,
            text=True
        )
        
        if os.path.exists(output_file):
            return True, "Конвертация успешна"
        else:
            return False, "Выходной файл не создан"
            
    except subprocess.TimeoutExpired:
        return False, "Превышено время конвертации (5 минут)"
    except subprocess.CalledProcessError as e:
        return False, f"Ошибка ImageMagick: {e.stderr}"
    except Exception as e:
        return False, f"Неожиданная ошибка: {str(e)}"

def validate_pdf_file(file_path: str) -> tuple[bool, str]:
    """
    Проверяет, является ли файл PDF
    """
    try:
        # Проверка через python-magic
        mime_type = magic.from_file(file_path, mime=True)
        if mime_type != 'application/pdf':
            return False, f"Неподдерживаемый тип файла: {mime_type}"
        
        # Дополнительная проверка через filetype
        kind = filetype.guess(file_path)
        if kind is None or kind.mime != 'application/pdf':
            return False, "Файл не является PDF"
            
        return True, "PDF файл валиден"
        
    except Exception as e:
        return False, f"Ошибка валидации: {str(e)}"

@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Обработчик команды /start"""
    await message.answer(
        f"👋 Привет, {html.bold(message.from_user.full_name)}!\n\n"
        "🔄 Отправьте PDF файл, и я конвертирую его в TIFF:\n"
        "• Сжатие: LZW\n"
        "• Цветовое пространство: CMYK\n"
        "• Разрешение: 96 DPI\n\n"
        f"📏 Максимальный размер файла: {MAX_FILE_MB} МБ\n"
        "🔗 В ответ вы получите прямую ссылку на скачивание"
    )

@dp.message(Command("help"))
async def help_handler(message: Message) -> None:
    """Обработчик команды /help"""
    await message.answer(
        "🆘 <b>Справка по использованию бота</b>\n\n"
        "📋 <b>Поддерживаемые форматы:</b>\n"
        "• Только PDF документы\n\n"
        "⚙️ <b>Параметры конвертации:</b>\n"
        "• Формат выхода: TIFF\n"
        "• Сжатие: LZW\n"
        "• Цветовое пространство: CMYK\n"
        "• Разрешение: 96 DPI\n\n"
        "📐 <b>Ограничения:</b>\n"
        f"• Максимальный размер: {MAX_FILE_MB} МБ\n"
        "• Время обработки: до 5 минут\n\n"
        "📄 <b>Многостраничные PDF:</b>\n"
        "Для многостраничных PDF создается отдельный TIFF файл с именем:\n"
        "<code>исходное_имя_1.tiff, исходное_имя_2.tiff</code> и т.д.\n\n"
        "🔗 <b>Результат:</b>\n"
        "Прямая ссылка для скачивания готового файла"
    )

@dp.message()
async def document_handler(message: Message) -> None:
    """Обработчик документов"""
    
    # Проверяем, есть ли документ
    if not message.document:
        await message.answer("❌ Пожалуйста, отправьте PDF документ")
        return
    
    document = message.document
    
    # Проверяем MIME-тип
    if document.mime_type != 'application/pdf':
        await message.answer(
            "❌ Поддерживаются только PDF файлы\n"
            f"Получен: {document.mime_type or 'неизвестный тип'}"
        )
        return
    
    # Проверяем размер файла
    file_size_mb = document.file_size / (1024 * 1024)
    if file_size_mb > MAX_FILE_MB:
        await message.answer(
            f"❌ Файл слишком большой: {file_size_mb:.1f} МБ\n"
            f"Максимальный размер: {MAX_FILE_MB} МБ"
        )
        return
    
    # Создаем уникальную рабочую директорию
    work_id = str(uuid.uuid4())
    work_dir = Path(TMP_DIR) / work_id
    work_dir.mkdir(exist_ok=True)
    
    # Пути файлов
    input_file = work_dir / 'input.pdf'
    
    # Генерируем имя выходного файла
    base_name = document.file_name.rsplit('.', 1)[0] if document.file_name else 'converted'
    output_filename = f"{base_name}.tiff"
    output_file = work_dir / 'output.tiff'
    final_file = Path(PUBLISH_DIR) / output_filename
    
    try:
        # Уведомляем пользователя о начале обработки
        status_msg = await message.answer(
            f"📥 Загружаю файл: {document.file_name}\n"
            f"📊 Размер: {file_size_mb:.1f} МБ\n"
            "⏳ Скачивание..."
        )
        
        # Скачиваем файл
        file_info = await bot.get_file(document.file_id)
        await bot.download_file(file_info.file_path, input_file)
        
        # Валидируем PDF
        is_valid, validation_msg = validate_pdf_file(str(input_file))
        if not is_valid:
            await status_msg.edit_text(f"❌ {validation_msg}")
            return
        
        # Обновляем статус
        await status_msg.edit_text(
            f"✅ Файл загружен и проверен\n"
            "🔄 Конвертирую в TIFF (CMYK, LZW, 96 DPI)...\n"
            "⏳ Это может занять несколько минут"
        )
        
        # Выполняем конвертацию в отдельном процессе
        loop = asyncio.get_event_loop()
        success, error_msg = await loop.run_in_executor(
            executor,
            convert_pdf_to_tiff,
            str(input_file),
            str(output_file)
        )
        
        if not success:
            await status_msg.edit_text(f"❌ Ошибка конвертации:\n{error_msg}")
            return
        
        # Перемещаем файл в публичную директорию
        if output_file.exists():
            output_file.rename(final_file)
            
            # Получаем размер выходного файла
            output_size_mb = final_file.stat().st_size / (1024 * 1024)
            
            # Формируем ссылку для скачивания
            download_url = f"{PUBLIC_BASE_URL}/files/{output_filename}"
            
            # Отправляем результат
            await status_msg.edit_text(
                f"✅ <b>Конвертация завершена!</b>\n\n"
                f"📁 Исходный файл: {document.file_name}\n"
                f"📁 Выходной файл: {output_filename}\n"
                f"📊 Размер результата: {output_size_mb:.1f} МБ\n\n"
                f"🔗 <b>Ссылка для скачивания:</b>\n"
                f"<a href='{download_url}'>{output_filename}</a>\n\n"
                f"💾 Файл сохранен на сервере и доступен по ссылке"
            )
            
            logger.info(
                f"Successfully converted {document.file_name} -> {output_filename} "
                f"({file_size_mb:.1f}MB -> {output_size_mb:.1f}MB) for user {message.from_user.id}"
            )
        else:
            await status_msg.edit_text("❌ Выходной файл не найден после конвертации")
    
    except Exception as e:
        logger.error(f"Error processing file for user {message.from_user.id}: {str(e)}")
        await message.answer(
            f"❌ Произошла ошибка при обработке файла:\n{str(e)}\n\n"
            "Попробуйте:\n"
            "• Другой PDF файл\n"
            "• Уменьшить размер файла\n"
            "• Повторить попытку позже"
        )
    
    finally:
        # Очищаем временные файлы
        try:
            if work_dir.exists():
                for file in work_dir.rglob('*'):
                    if file.is_file():
                        file.unlink()
                work_dir.rmdir()
        except Exception as e:
            logger.warning(f"Failed to cleanup temp directory {work_dir}: {e}")

async def main():
    """Основная функция запуска бота"""
    logger.info("Starting PDF→TIFF conversion bot...")
    logger.info(f"Publish directory: {PUBLISH_DIR}")
    logger.info(f"Temp directory: {TMP_DIR}")
    logger.info(f"Max file size: {MAX_FILE_MB} MB")
    logger.info(f"Concurrency: {CONCURRENCY}")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
    finally:
        await bot.session.close()
        executor.shutdown(wait=True)

if __name__ == "__main__":
    asyncio.run(main())