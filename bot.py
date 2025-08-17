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

# Обработчик файлов PDF
@dp.message(lambda message: message.document is not None)
async def handle_document(message: types.Message):
    """Обработчик загруженных документов"""
    
    # Проверяем тип файла
    if not message.document.file_name.lower().endswith('.pdf'):
        await message.answer("⚠️ Поддерживаются только PDF файлы!")
        return
    
    # Проверяем размер файла
    file_size_mb = message.document.file_size / (1024 * 1024)
    if file_size_mb > MAX_FILE_MB:
        await message.answer(f"⚠️ Размер файла превышает лимит {MAX_FILE_MB}MB!")
        return
    
    # Проверяем безопасность имени файла
    if not is_safe_filename(message.document.file_name):
        await message.answer("⚠️ Недопустимое имя файла!")
        return
    
    await message.answer("📄 Начинаю обработку PDF...")
    
    # Создаем уникальные имена файлов
    unique_id = str(uuid.uuid4())
    safe_filename = f"{unique_id}.pdf"
    pdf_path = os.path.join(TMP_DIR, safe_filename)
    tiff_filename = f"{unique_id}.tiff"
    tiff_path = os.path.join(PUBLISH_DIR, tiff_filename)
    
    try:
        # Скачиваем PDF во временную папку
        file_info = await bot.get_file(message.document.file_id)
        await bot.download_file(file_info.file_path, pdf_path)
        
        # Запускаем конвертацию в отдельном процессе
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor, 
            process_pdf, 
            pdf_path, 
            tiff_path, 
            DPI_DEFAULT, 
            GS_PATH
        )
        
        # Проверяем результат конвертации
        if not result['success']:
            await message.answer(f"❌ Ошибка конвертации: {result['error']}")
            return
        
        # Проверяем, что файл был создан
        if not os.path.exists(tiff_path):
            await message.answer("❌ Файл TIFF не был создан!")
            return
        
        # Получаем размер результирующего файла
        tiff_size_mb = get_file_size_mb(tiff_path)
        
        # Формируем публичную ссылку
        download_url = f"{PUBLIC_BASE_URL.rstrip('/')}/{tiff_filename}"
        
        # Отправляем результат
        success_message = (
            f"✅ Конвертация завершена!\n\n"
            f"📊 Размер TIFF: {tiff_size_mb:.2f} MB\n"
            f"🔗 Прямая ссылка: {download_url}\n\n"
            f"💡 CMYK TIFF может некорректно отображаться в обычных просмотрщиках. "
            f"Используйте профессиональные редакторы для правильного просмотра."
        )
        
        # Пытаемся отправить файл как документ (если размер позволяет)
        if tiff_size_mb <= 50:  # Telegram лимит 50MB
            try:
                tiff_file = FSInputFile(tiff_path, filename=f"converted_{message.document.file_name[:-4]}.tiff")
                await message.answer_document(tiff_file, caption=success_message)
            except Exception as e:
                # Если не удалось отправить файл, просто отправляем ссылку
                await message.answer(success_message)
        else:
            # Файл слишком большой для Telegram, отправляем только ссылку
            await message.answer(success_message)
            
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка: {str(e)}")
    
    finally:
        # Удаляем временные файлы
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception as e:
            print(f"Ошибка удаления временного файла {pdf_path}: {e}")

if __name__ == "__main__":
    print("🚀 Запуск бота...")
    
    # Проверяем необходимые переменные окружения
    required_vars = ["BOT_TOKEN", "PUBLIC_BASE_URL", "PUBLISH_DIR", "TMP_DIR"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Отсутствуют переменные окружения: {', '.join(missing_vars)}")
        exit(1)
    
    # Создаем необходимые директории
    os.makedirs(TMP_DIR, exist_ok=True)
    os.makedirs(PUBLISH_DIR, exist_ok=True)
    
    print(f"📁 Временная папка: {TMP_DIR}")
    print(f"📁 Папка публикации: {PUBLISH_DIR}")
    print(f"🔗 Базовый URL: {PUBLIC_BASE_URL}")
    print(f"📏 Максимальный размер файла: {MAX_FILE_MB}MB")
    print(f"🖼️ DPI по умолчанию: {DPI_DEFAULT}")
    print(f"⚡ Параллелизм: {CONCURRENCY}")
    
    try:
        asyncio.run(dp.start_polling(bot))
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    finally:
        executor.shutdown(wait=True)
