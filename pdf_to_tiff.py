# pdf_to_tiff.py

import os
import subprocess
import logging

def process_pdf(src_pdf_path, filename, tmp_dir, publish_dir, public_base_url, gs_path, dpi_default):
    """
    Конвертация PDF в TIFF через Ghostscript с улучшенной обработкой ошибок.
    - Целевой формат: CMYK TIFF с LZW-сжатием.
    - Разрешение настраивается через переменную окружения.
    """
    # Формируем имя выходного файла
    output_filename = os.path.splitext(filename)[0] + ".tiff"
    # Путь, куда будет сохранен готовый TIFF-файл
    tiff_path = os.path.join(publish_dir, output_filename)
    
    # --- УЛУЧШЕННАЯ КОМАНДА GHOSTSCRIPT ---
    command = [
        gs_path,
        '-q',                     # Тихий режим, минимум вывода в консоль
        '-dNOPAUSE',              # Не ждать нажатия клавиши между страницами
        '-dBATCH',                # Автоматический выход после обработки всех страниц
        '-dSAFER',                # Режим безопасности (критически важно!)
        '-dPDFSTOPONERROR',       # УЛУЧШЕНИЕ: Остановиться при первой же ошибке в PDF
        f'-r{dpi_default}',      # Задать разрешение (DPI)
        '-sDEVICE=tiff32nc',      # Целевое устройство: 32-битный CMYK TIFF
        '-dColorConversionStrategy=/CMYK',
        '-dProcessColorModel=/DeviceCMYK',
        '-sCompression=lzw',      # ИСПРАВЛЕНО: правильный флаг для LZW-сжатия
        f'-sOutputFile={tiff_path}', # Путь к выходному файлу
        src_pdf_path              # Путь к исходному PDF-файлу
    ]

    try:
        logging.info(f"Ghostscript: Выполняю команду {' '.join(command)}")
        # Запускаем процесс. check=True вызовет исключение при коде возврата != 0
        result = subprocess.run(
            command, 
            capture_output=True,  # Захватываем stdout и stderr
            text=True, 
            check=True, 
            # Указываем кодировку, чтобы избежать проблем с символами в выводе Ghostscript
            encoding='utf-8', 
            errors='ignore'
        )
        
        # Иногда Ghostscript пишет предупреждения в stderr, даже если все прошло успешно
        if result.stderr:
            logging.warning(f"Ghostscript stderr (успешное выполнение): {result.stderr.strip()}")

        # Дополнительная проверка, что файл действительно создан и не пустой
        if not os.path.exists(tiff_path) or os.path.getsize(tiff_path) == 0:
            error_details = "Файл TIFF не был создан или имеет нулевой размер."
            logging.error(error_details)
            return False, "Ошибка при конвертации.", None, None, 0, error_details

        file_size = os.path.getsize(tiff_path)
        public_url = f"{public_base_url}/{output_filename}"
        
        # Возвращаем кортеж с результатом для основного процесса
        return True, "Успешно", tiff_path, public_url, file_size, ""

    except subprocess.CalledProcessError as e:
        # --- УЛУЧШЕННАЯ ОБРАБОТКА ОШИБОК ---
        # Эта ошибка возникает, когда Ghostscript возвращает код, отличный от 0
        
        # Собираем максимум информации для логов, чтобы было проще понять причину
        error_output = f"Ghostscript завершился с кодом {e.returncode}.\n"
        error_output += f"Stdout: {e.stdout.strip() if e.stdout else 'N/A'}\n"
        error_output += f"Stderr: {e.stderr.strip() if e.stderr else 'N/A'}"
        logging.error(f"Ошибка Ghostscript:\n{error_output}")
        
        # Возвращаем пользователю только stderr, т.к. там обычно самая суть проблемы
        return False, "Ошибка при обработке файла.", None, None, 0, e.stderr.strip()
    
    except Exception as e:
        # Ловим любые другие непредвиденные ошибки (например, проблемы с правами доступа)
        logging.exception("Непредвиденная ошибка в process_pdf:")
        return False, "Внутренняя ошибка сервера.", None, None, 0, str(e)

