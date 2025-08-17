import os
import subprocess
import shutil
import magic
import filetype
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Получение параметров из переменных окружения
MAX_FILE_MB = int(os.getenv('MAX_FILE_MB', '100'))  # По умолчанию 100 МБ
DEFAULT_DPI = int(os.getenv('DEFAULT_DPI', '300'))  # По умолчанию 300 DPI
TIMEOUT_SECONDS = int(os.getenv('TIMEOUT_SECONDS', '300'))  # По умолчанию 5 минут
GS_PAGE_CHECK_TIMEOUT = int(os.getenv('GS_PAGE_CHECK_TIMEOUT', '10'))  # По умолчанию 10 секунд

def generate_unique_filename(target_dir, base_name, extension):
    """
    Генерирует уникальное имя файла, добавляя суффикс при необходимости
    """
    counter = 0
    original_name = f"{base_name}{extension}"
    candidate_name = original_name
    
    while os.path.exists(os.path.join(target_dir, candidate_name)):
        counter += 1
        candidate_name = f"{base_name}_{counter}{extension}"
    
    return candidate_name

def clean_sep_files(tmp_dir, main_tiff_name):
    """
    Удаляет только побочные (неосновные) файлы sep, оставляя главный TIFF
    """
    cleaned_files = []
    errors = []
    
    for filename in os.listdir(tmp_dir):
        filepath = os.path.join(tmp_dir, filename)
        
        # Удаляем только побочные файлы sep (.tif), но не основной файл
        if (filename.endswith('.tif') and 
            filename != main_tiff_name and 
            filename != main_tiff_name.replace('.tiff', '.tif')):
            
            try:
                os.remove(filepath)
                cleaned_files.append(filename)
                logger.info(f"Удален побочный файл sep: {filename}")
            except Exception as e:
                error_msg = f"Ошибка при удалении файла {filename}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
    
    return cleaned_files, errors

def process_pdf(src_pdf_path, orig_name, tmp_dir, publish_dir, public_url, gs_path, dpi=None):
    """
    Обрабатывает PDF файл и конвертирует его в TIFF формат
    
    Args:
        src_pdf_path: путь к исходному PDF файлу
        orig_name: оригинальное имя файла
        tmp_dir: временная директория
        publish_dir: директория для публикации
        public_url: публичный URL
        gs_path: путь к Ghostscript
        dpi: разрешение DPI (по умолчанию из переменных окружения)
    
    Returns:
        tuple: (успех, сообщение, путь_к_файлу, url, размер_файла, ошибка)
    """
    
    # Используем DPI из параметров или из переменных окружения
    if dpi is None:
        dpi = DEFAULT_DPI
    
    try:
        # Проверки
        # MIME и сигнатура
        if not (magic.from_file(src_pdf_path, mime=True) == 'application/pdf' and 
                filetype.guess(src_pdf_path).mime == 'application/pdf'):
            return False, "Файл не является PDF", None, None, 0, ""
        
        # Проверка размера файла
        file_size_bytes = os.path.getsize(src_pdf_path)
        max_size_bytes = MAX_FILE_MB * 1024 * 1024
        
        if file_size_bytes > max_size_bytes:
            return False, f"Файл слишком большой (максимум {MAX_FILE_MB} МБ)", None, None, 0, ""
        
        # Ghostscript: получить число страниц
        checker = [
            gs_path, "-q", "-dNODISPLAY", "-c",
            f"({src_pdf_path}) (r) file runpdfbegin pdfpagecount = quit"
        ]
        
        try:
            out = subprocess.check_output(checker, timeout=GS_PAGE_CHECK_TIMEOUT)
            pages = int(out.decode().strip())
            if pages != 1:
                return False, "PDF должен содержать ровно одну страницу", None, None, 0, ""
        except subprocess.TimeoutExpired:
            return False, "Превышено время ожидания при проверке количества страниц", None, None, 0, ""
        except Exception as e:
            return False, "Ошибка при проверке количества страниц. Проверьте PDF.", None, None, 0, str(e)
        
        # Проверка на зашифрованность
        try:
            encrypted_check = [
                gs_path, "-q", "-dNODISPLAY", "-c",
                f"({src_pdf_path}) (r) file runpdfbegin pdfhasinfo = quit"
            ]
            subprocess.check_output(encrypted_check, timeout=GS_PAGE_CHECK_TIMEOUT)
        except subprocess.TimeoutExpired:
            return False, "Превышено время ожидания при проверке шифрования", None, None, 0, ""
        except Exception as e:
            return False, "Зашифрованные PDF не поддерживаются", None, None, 0, str(e)
        
        # Формирование путей
        today = datetime.now().strftime('%Y_%m_%d')
        target_dir = os.path.join(publish_dir, today)
        os.makedirs(target_dir, exist_ok=True)
        
        # Чистое имя файла
        base = os.path.splitext(os.path.basename(orig_name))[0]
        safe_base = "".join([c for c in base if c.isalnum() or c in "_-"]).rstrip()
        
        # Защита от коллизий имен файлов
        unique_tiff_name = generate_unique_filename(target_dir, safe_base, '.tiff')
        
        tiff_out_tmp_path = os.path.join(tmp_dir, unique_tiff_name)
        tiff_out_final = os.path.join(target_dir, unique_tiff_name)
        
        # Конвертация через Ghostscript
        gs_cmd = [
            gs_path,
            "-dNOPAUSE", "-dBATCH", "-sDEVICE=tiffsep",
            "-sCompression=lzw",
            f"-r{dpi}",
            "-dProcessColorModel=/DeviceCMYK",
            "-dColorConversionStrategy=/CMYK",
            "-sOutputFile=" + tiff_out_tmp_path,
            src_pdf_path
        ]
        
        try:
            proc = subprocess.run(gs_cmd, shell=False, capture_output=True, timeout=TIMEOUT_SECONDS)
            if proc.returncode != 0:
                error_msg = proc.stderr.decode().strip() if proc.stderr else "Неизвестная ошибка"
                return False, "Ошибка конвертации PDF в TIFF", None, None, 0, error_msg
        except subprocess.TimeoutExpired:
            return False, f"Превышено время ожидания конвертации ({TIMEOUT_SECONDS} сек)", None, None, 0, ""
        except Exception as e:
            return False, "Ошибка при запуске конвертации", None, None, 0, str(e)
        
        # Чистка побочных sep-файлов с логированием
        cleaned_files, clean_errors = clean_sep_files(tmp_dir, unique_tiff_name)
        
        # Логируем информацию о чистке
        if cleaned_files:
            logger.info(f"Очистка завершена. Удалено файлов: {len(cleaned_files)}")
        if clean_errors:
            logger.warning(f"Ошибки при очистке ({len(clean_errors)}): {'; '.join(clean_errors)}")
        
        # Проверка итогового файла
        if not os.path.exists(tiff_out_tmp_path):
            return False, "TIFF-файл не найден после конвертации", None, None, 0, ""
        
        # Перемещение в директорию публикации
        try:
            shutil.move(tiff_out_tmp_path, tiff_out_final)
            os.umask(0o022)  # установка прав доступа
        except Exception as e:
            return False, "Ошибка при перемещении файла в директорию публикации", None, None, 0, str(e)
        
        # Получение размера итогового файла
        try:
            final_file_size = os.path.getsize(tiff_out_final)
        except Exception as e:
            return False, "Ошибка при получении размера итогового файла", None, None, 0, str(e)
        
        # Проверка безопасности пути
        if not os.path.abspath(tiff_out_final).startswith(os.path.abspath(target_dir)):
            return False, "Ошибка безопасности: недопустимый путь к файлу", None, None, 0, ""
        
        # Формирование URL
        url = f"{public_url}/files/{today}/{unique_tiff_name}"
        
        logger.info(f"Успешная конвертация: {orig_name} -> {unique_tiff_name} ({final_file_size} байт)")
        
        return True, "Конвертация успешно завершена!", tiff_out_final, url, final_file_size, ""
        
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке {orig_name}: {str(e)}")
        return False, "Произошла неожиданная ошибка при обработке файла", None, None, 0, str(e)
