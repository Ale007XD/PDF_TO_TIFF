# pdf_to_tiff.py

import os
import shutil
import subprocess
import logging
from wand.image import Image
from wand.exceptions import WandException

def _run_command(command):
    """Вспомогательная функция для запуска внешних команд и обработки результатов."""
    try:
        logging.info(f"Выполняю: {' '.join(command)}")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,  # Вызовет исключение при ошибке
            encoding='utf-8',
            errors='ignore'
        )
        if result.stderr:
            logging.warning(f"Stderr (успешно): {result.stderr.strip()}")
        return True, result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        error_output = f"Код возврата: {e.returncode}\\nStdout: {e.stdout.strip() if e.stdout else 'N/A'}\\nStderr: {e.stderr.strip() if e.stderr else 'N/A'}"
        logging.error(f"Команда завершилась с ошибкой:\\n{error_output}")
        return False, e.stdout.strip(), e.stderr.strip()
    except FileNotFoundError:
        logging.error(f"Команда не найдена: {command[0]}. Убедитесь, что утилита установлена.")
        return False, "", f"Утилита {command} не найдена."

def _check_pdf_with_ghostscript(src_pdf_path, gs_path):
    """Проверка PDF файла на читаемость с помощью Ghostscript (опционально)."""
    if not gs_path or not os.path.exists(gs_path):
        logging.info("Ghostscript не найден, пропускаем проверку читаемости PDF")
        return True
    
    logging.info(f"Проверяю читаемость PDF: {src_pdf_path}")
    check_command = [gs_path, "-q", "-dNODISPLAY", "-c", f"({src_pdf_path}) (r) file runpdfbegin quit"]
    is_readable, _, _ = _run_command(check_command)
    return is_readable

def _try_fix_pdf_with_qpdf(src_pdf_path, tmp_dir):
    """Попытка исправления поврежденного PDF с помощью qpdf."""
    logging.warning("PDF не удалось прочитать с первого раза. Попытка исправления...")
    
    fixed_pdf_path = os.path.join(tmp_dir, "fixed_input.pdf")
    
    # qpdf пересобирает PDF, что часто исправляет структурные ошибки
    fix_command = ["qpdf", "--linearize", src_pdf_path, fixed_pdf_path]
    
    is_fixed, _, stderr = _run_command(fix_command)

    if not is_fixed:
        # Если даже qpdf не помог, возвращаем None
        logging.error("Не удалось исправить PDF с помощью qpdf.")
        return None, stderr

    logging.info("PDF был успешно пересобран. Повторная попытка конвертации.")
    return fixed_pdf_path, ""

def _convert_pdf_to_tiff_with_wand(pdf_path, tiff_path, dpi_default):
    """Конвертация PDF в TIFF с использованием библиотеки wand (ImageMagick)."""
    try:
        logging.info(f"Начинаю конвертацию PDF в TIFF: {pdf_path} -> {tiff_path}")
        
        with Image(filename=pdf_path, resolution=dpi_default) as img:
            # Устанавливаем цветовое пространство CMYK
            img.colorspace = 'cmyk'
            
            # Устанавливаем сжатие LZW
            img.compression = 'lzw'
            
            # Убираем альфа-канал для всех страниц
            for frame in img.sequence:
                with Image(frame) as page_img:
                    page_img.alpha_channel = 'remove'
                    page_img.background_color = 'white'
            
            # Сбрасываем итератор на начало
            img.iterator_reset()
            
            # Устанавливаем формат TIFF
            img.format = 'tiff'
            
            # Сохраняем файл
            img.save(filename=tiff_path)
            
        logging.info(f"Конвертация завершена успешно: {tiff_path}")
        return True, ""
        
    except WandException as e:
        error_msg = f"Ошибка Wand при конвертации: {str(e)}"
        logging.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Неожиданная ошибка при конвертации: {str(e)}"
        logging.error(error_msg)
        return False, error_msg

def process_pdf(src_pdf_path, filename, tmp_dir, publish_dir, public_base_url, gs_path, dpi_default):
    """
    Конвертация PDF в TIFF с предварительной проверкой и попыткой исправления.
    Использует библиотеку wand (ImageMagick) вместо Ghostscript для основной конвертации.
    """
    
    # --- ЭТАП 1: Проверка PDF на "читаемость" (опционально, только если доступен Ghostscript) ---
    is_readable = _check_pdf_with_ghostscript(src_pdf_path, gs_path)
    
    current_pdf_path = src_pdf_path

    if not is_readable:
        # --- ЭТАП 2: Попытка исправления с помощью qpdf ---
        fixed_pdf_path, stderr = _try_fix_pdf_with_qpdf(src_pdf_path, tmp_dir)
        
        if fixed_pdf_path is None:
            # Если даже qpdf не помог, возвращаем ошибку
            return False, "Файл PDF поврежден и не может быть автоматически исправлен.", None, None, 0, stderr
        
        current_pdf_path = fixed_pdf_path  # Теперь работаем с исправленной версией
    else:
        logging.info("PDF в порядке (или проверка пропущена), продолжаю конвертацию.")

    # --- ЭТАП 3: Основная конвертация с помощью wand (ImageMagick) ---
    output_filename = os.path.splitext(filename)[0] + ".tiff"
    tiff_path = os.path.join(publish_dir, output_filename)
    
    # Создаем директорию для публикации, если она не существует
    os.makedirs(publish_dir, exist_ok=True)
    
    is_converted, error_message = _convert_pdf_to_tiff_with_wand(current_pdf_path, tiff_path, dpi_default)

    if not is_converted or not os.path.exists(tiff_path) or os.path.getsize(tiff_path) == 0:
        return False, "Ошибка при конвертации файла в TIFF.", None, None, 0, error_message

    # --- Финальный этап: Возвращаем успешный результат ---
    file_size = os.path.getsize(tiff_path)
    public_url = f"{public_base_url}/{output_filename}"
    
    return True, "Успешно", tiff_path, public_url, file_size, ""
