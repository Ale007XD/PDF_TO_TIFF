# pdf_to_tiff.py

import os
import shutil
import subprocess
import logging

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
        error_output = f"Код возврата: {e.returncode}\nStdout: {e.stdout.strip() if e.stdout else 'N/A'}\nStderr: {e.stderr.strip() if e.stderr else 'N/A'}"
        logging.error(f"Команда завершилась с ошибкой:\n{error_output}")
        return False, e.stdout.strip(), e.stderr.strip()
    except FileNotFoundError:
        logging.error(f"Команда не найдена: {command[0]}. Убедитесь, что утилита установлена.")
        return False, "", f"Утилита {command} не найдена."

def process_pdf(src_pdf_path, filename, tmp_dir, publish_dir, public_base_url, gs_path, dpi_default):
    """
    Конвертация PDF в TIFF с предварительной проверкой и попыткой исправления.
    """
    
    # --- ЭТАП 1: Проверка PDF на "читаемость" ---
    logging.info(f"Проверяю читаемость PDF: {src_pdf_path}")
    check_command = [gs_path, "-q", "-dNODISPLAY", "-c", f"({src_pdf_path}) (r) file runpdfbegin quit"]
    is_readable, _, _ = _run_command(check_command)
    
    current_pdf_path = src_pdf_path

    if not is_readable:
        logging.warning("PDF не удалось прочитать с первого раза. Попытка исправления...")
        
        # --- ЭТАП 2: Попытка исправления с помощью qpdf ---
        fixed_pdf_path = os.path.join(tmp_dir, "fixed_input.pdf")
        
        # qpdf пересобирает PDF, что часто исправляет структурные ошибки
        fix_command = ["qpdf", "--linearize", src_pdf_path, fixed_pdf_path]
        
        is_fixed, _, stderr = _run_command(fix_command)

        if not is_fixed:
            # Если даже qpdf не помог, возвращаем ошибку
            logging.error("Не удалось исправить PDF с помощью qpdf.")
            return False, "Файл PDF поврежден и не может быть автоматически исправлен.", None, None, 0, stderr

        logging.info("PDF был успешно пересобран. Повторная попытка конвертации.")
        current_pdf_path = fixed_pdf_path  # Теперь работаем с исправленной версией
    else:
        logging.info("PDF в порядке, продолжаю конвертацию.")

    # --- ЭТАП 3: Основная конвертация (теперь с большей вероятностью успеха) ---
    output_filename = os.path.splitext(filename)[0] + ".tiff"
    tiff_path = os.path.join(publish_dir, output_filename)
    
    conversion_command = [
        gs_path, '-q', '-dNOPAUSE', '-dBATCH', '-dSAFER', '-dPDFSTOPONERROR',
        f'-r{dpi_default}', '-sDEVICE=tiff32nc', '-dColorConversionStrategy=/CMYK',
        '-dProcessColorModel=/DeviceCMYK', '-sCompression=lzw',
        f'-sOutputFile={tiff_path}',
        current_pdf_path  # Используем либо оригинальный, либо исправленный PDF
    ]

    is_converted, _, stderr = _run_command(conversion_command)

    if not is_converted or not os.path.exists(tiff_path) or os.path.getsize(tiff_path) == 0:
        return False, "Ошибка при конвертации файла в TIFF.", None, None, 0, stderr

    # --- Финальный этап: Возвращаем успешный результат ---
    file_size = os.path.getsize(tiff_path)
    public_url = f"{public_base_url}/{output_filename}"
    
    return True, "Успешно", tiff_path, public_url, file_size, ""

