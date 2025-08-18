import os
import subprocess
import logging

def process_pdf(src_pdf_path, filename, tmp_dir, publish_dir, public_base_url, gs_path, dpi_default):
    """
    Конвертация PDF в TIFF через Ghostscript (CMYK, LZW, настройка DPI).
    Никаких проверок количества страниц!
    """
    # Имя итогового файла
    output_filename = os.path.splitext(filename)[0] + ".tiff"
    tiff_path = os.path.join(publish_dir, output_filename)

    # Команда Ghostscript для конвертации
    command = [
        gs_path,
        '-q',
        '-dNOPAUSE',
        '-dBATCH',
        '-dSAFER',
        '-dPDFSTOPONERROR',
        f'-r{dpi_default}',
        '-sDEVICE=tiff32nc',
        '-dColorConversionStrategy=/CMYK',
        '-dProcessColorModel=/DeviceCMYK',
        '-sCompression=lzw',
        f'-sOutputFile={tiff_path}',
        src_pdf_path
    ]

    try:
        logging.info(f"Ghostscript: {' '.join(command)}")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8',
            errors='ignore'
        )

        # Ghostscript иногда пишет варнинги в stderr — логируем для отладки, но не считаем ошибкой
        if result.stderr:
            logging.warning(f"Ghostscript stderr (успешно): {result.stderr.strip()}")

        # Проверка успешного создания файла
        if not os.path.exists(tiff_path) or os.path.getsize(tiff_path) == 0:
            error_details = "Файл TIFF не был создан или имеет нулевой размер."
            logging.error(error_details)
            return False, "Ошибка при конвертации.", None, None, 0, error_details

        file_size = os.path.getsize(tiff_path)
        public_url = f"{public_base_url}/{output_filename}"
        return True, "Успешно", tiff_path, public_url, file_size, ""

    except subprocess.CalledProcessError as e:
        error_output = f"Ghostscript завершился с кодом {e.returncode}.\n"
        error_output += f"Stdout: {e.stdout.strip() if e.stdout else 'N/A'}\n"
        error_output += f"Stderr: {e.stderr.strip() if e.stderr else 'N/A'}"
        logging.error(f"Ошибка Ghostscript:\n{error_output}")
        return False, "Ошибка при обработке файла.", None, None, 0, e.stderr.strip() if e.stderr else error_output

    except Exception as e:
        logging.exception("Непредвиденная ошибка в process_pdf:")
        return False, "Внутренняя ошибка сервера.", None, None, 0, str(e)

