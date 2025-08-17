#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Бот для конвертации PDF в TIFF
Версия: 1.0.0 (Часть 1/3)
Автор: @Ale007XD
Описание: Telegram-бот для конвертации PDF файлов в изображения формата TIFF 
с возможностью настройки качества и обработкой многостраничных документов.
"""

# Импорт необходимых библиотек
import os
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# Библиотеки для работы с Telegram
from telegram import Update, Document
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    ContextTypes, filters
)

# Библиотеки для обработки PDF и изображений  
from pdf2image import convert_from_path
from PIL import Image
import zipfile
import tempfile
import shutil

# Загрузка переменных окружения
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# =============================================================================
# КОНФИГУРАЦИЯ БОТА
# =============================================================================

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("Токен бота не найден! Создайте файл .env с BOT_TOKEN")

# Настройки конвертации
DPI = 300  # Качество изображения (точек на дюйм)
MAX_FILE_SIZE = 20 * 1024 * 1024  # Максимальный размер файла: 20 МБ
OUTPUT_FORMAT = 'TIFF'  # Формат выходных изображений
TEMP_DIR = 'temp'  # Директория для временных файлов

# Создаем директорию для временных файлов если её нет
Path(TEMP_DIR).mkdir(exist_ok=True)

# =============================================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# =============================================================================

# Настраиваем систему логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def cleanup_temp_files(file_path: str) -> None:
    """
    Удаляет временные файлы и директории
    
    Args:
        file_path (str): Путь к файлу или директории для удаления
    """
    try:
        if os.path.isfile(file_path):
            os.remove(file_path)
            logger.info(f"Удален временный файл: {file_path}")
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)
            logger.info(f"Удалена временная директория: {file_path}")
    except Exception as e:
        logger.error(f"Ошибка при удалении {file_path}: {e}")

def validate_pdf_file(document: Document) -> tuple[bool, str]:
    """
    Проверяет валидность PDF файла
    
    Args:
        document (Document): Объект документа из Telegram
        
    Returns:
        tuple[bool, str]: (Валиден ли файл, Сообщение об ошибке)
    """
    # Проверка расширения файла
    if not document.file_name.lower().endswith('.pdf'):
        return False, "❌ Файл должен быть в формате PDF!"
    
    # Проверка размера файла
    if document.file_size > MAX_FILE_SIZE:
        size_mb = document.file_size / (1024 * 1024)
        max_size_mb = MAX_FILE_SIZE / (1024 * 1024)
        return False, f"❌ Размер файла ({size_mb:.1f} МБ) превышает максимальный ({max_size_mb:.1f} МБ)!"
    
    return True, "✅ Файл прошел валидацию"

# =============================================================================
# ОБРАБОТЧИКИ КОМАНД
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /start
    Отправляет приветственное сообщение пользователю
    """
    user = update.effective_user
    welcome_message = f"""👋 Привет, {user.first_name}!
    
🤖 Я бот для конвертации PDF файлов в формат TIFF.

📋 **Что я умею:**
• 📄 Конвертирую PDF в высококачественные TIFF изображения
• 🖼️ Обрабатываю многостраничные документы
• 📁 Создаю ZIP архивы для многостраничных PDF
• ⚙️ Использую качество {DPI} DPI для четких изображений

💡 **Как использовать:**
1. Отправьте мне PDF файл
2. Дождитесь обработки
3. Получите TIFF изображения

📏 **Ограничения:**
• Максимальный размер файла: {MAX_FILE_SIZE // (1024*1024)} МБ
• Поддерживаются только PDF файлы

❓ Нужна помощь? Используйте /help"""
    
    await update.message.reply_text(
        welcome_message,
        parse_mode='Markdown'
    )
    
    logger.info(f"Пользователь {user.id} ({user.username}) запустил бота")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /help
    Отправляет справочную информацию
    """
    help_message = """🆘 **Справка по боту PDF→TIFF**

📖 **Основные команды:**
• `/start` - Запустить бота и показать приветствие
• `/help` - Показать эту справку
• `/about` - Информация о боте

📤 **Как конвертировать файл:**
1. Просто отправьте PDF файл боту
2. Бот автоматически начнет обработку
3. Для одностраничного PDF получите TIFF файл
4. Для многостраничного PDF получите ZIP архив

⚙️ **Настройки конвертации:**
• Качество: {DPI} DPI
• Формат вывода: {OUTPUT_FORMAT}
• Максимальный размер: {MAX_FILE_SIZE // (1024*1024)} МБ

🔧 **Устранение проблем:**
• Убедитесь, что файл имеет расширение .pdf
• Проверьте размер файла
• Попробуйте отправить файл заново

💬 Если проблемы остались, обратитесь к разработчику"""
    
    await update.message.reply_text(
        help_message,
        parse_mode='Markdown'
    )
    
    logger.info(f"Пользователь {update.effective_user.id} запросил справку")
