import os
import subprocess
import shutil
import magic
import filetype
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MAX_FILE_MB = int(os.environ.get('MAX_FILE_MB', '100'))
DPI_DEFAULT = int(os.environ.get('DPI_DEFAULT', '96'))
TIMEOUT_SECONDS = int(os.environ.get('TIMEOUT_SECONDS', '300'))
GS_PAGE_CHECK_TIMEOUT = int(os.environ.get('GS_PAGE_CHECK_TIMEOUT', '10'))

def generate_unique_filename(target_dir, base_name, extension):
    counter = 0
    original_name = f"{base_name}{extension}"
    candidate_name = original_name
    while os.path.exists(os.path.join(target_dir, candidate_name)):
        counter += 1
        candidate_name = f"{base_name}_{counter}{extension}"
    return candidate_name

def clean_sep_files(tmp_dir, main_tiff_name):
    cleaned_files = []
    errors = []
    for filename in os.listdir(tmp_dir):
        filepath = os.path.join(tmp_dir, filename)
        if (
            filename.endswith('.tif')
            and filename != main_tiff_name
            and filename != main_tiff_name.replace('.tiff', '.tif')
        ):
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
    if dpi is None:
        dpi = DPI_DEFAULT
    try:
        # Проверка PDF
        if not (
            magic.from_file(src_pdf_path, mime=True) == 'application/pdf'
            and filetype.guess(src_pdf_path).mime == 'application/pdf'
        ):
            return False, "Файл не является PDF", None, None, 0, ""

        file_size_bytes = os.path.getsize(src_pdf_path)
        max_size_bytes = MAX_FILE_MB * 1024 * 1024
        if file_size_bytes > max_size_bytes:
            return False, f"Файл слишком большой (максимум {MAX_FILE_MB} МБ)", None, None, 0, ""

        # Проверка числа страниц
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

        # Проверка на шифрование
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

        today = datetime.now().strftime('%Y_%m_%d')
        target_dir = os.path.join(publish_dir, today)
        os.makedirs(target_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(orig_name))[0]
        safe_base = "".join([c for c in base if c.isalnum() or c in "_-"]).rstrip()
        unique_tiff_name = generate_unique_filename(target_dir, safe_base, '.tiff')
        tiff_out_tmp_path = os.path.join(tmp_dir, unique_tiff_name)
        tiff_out_final = os.path.join(target_dir, unique_tiff_name)

        gs_cmd = [
            gs_path,
            "-dNOPAUSE", "-dBATCH", "-sDEVICE=tiffsep",
            "-sCompression=lzw",
            f"-r{dpi}",
            "-dProcessColorModel=/DeviceCMYK",
            "-dColorConversionStrategy=/CMYK",
            f"-sOutputFile={tiff_out_tmp_path}",
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

        cleaned_files, clean_errors = clean_sep_files(tmp_dir, unique_tiff_name)
        if cleaned_files:
            logger.info(f"Очистка завершена. Удалено файлов: {len(cleaned_files)}")
        if clean_errors:
            logger.warning(f"Ошибки при очистке ({len(clean_errors)}): {'; '.join(clean_errors)}")
        if not os.path.exists(tiff_out_tmp_path):
            return False, "TIFF-файл не найден после конвертации", None, None, 0, ""

        try:
            shutil.move(tiff_out_tmp_path, tiff_out_final)
            os.umask(0o022)
        except Exception as e:
            return False, "Ошибка при перемещении файла в директорию публикации", None, None, 0, str(e)

        try:
            final_file_size = os.path.getsize(tiff_out_final)
        except Exception as e:
            return False, "Ошибка при получении размера итогового файла", None, None, 0, str(e)

        if not os.path.abspath(tiff_out_final).startswith(os.path.abspath(target_dir)):
            return False, "Ошибка безопасности: недопустимый путь к файлу", None, None, 0, ""

        url = f"{public_url}/files/{today}/{unique_tiff_name}"

        logger.info(f"Успешная конвертация: {orig_name} -> {unique_tiff_name} ({final_file_size} байт)")
        return True, "Конвертация успешно завершена!", tiff_out_final, url, final_file_size, ""
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке {orig_name}: {str(e)}")
        return False, "Произошла неожиданная ошибка при обработке файла", None, None, 0, str(e)
