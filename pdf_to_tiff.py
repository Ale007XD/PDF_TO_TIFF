import os
import subprocess
import logging

def process_pdf(src_pdf_path, filename, tmp_dir, publish_dir, public_base_url, gs_path, dpi_default):
    """
    Конвертация PDF в TIFF через Ghostscript (CMYK, LZW, 96dpi/настраивается).
    Никаких проверок страниц!
    """
    output_filename = os.path.splitext(filename)[0] + ".tiff"
    tiff_path = os.path.join(publish_dir, output_filename)

    command = [
        gs_path,
        '-q',
        '-dNOPAUSE',
        '-dBATCH',
        '-dSAFER',
        f'-r{dpi_default}',
        '-sDEVICE=tiff32nc',
        '-dColorConversionStrategy=/CMYK',
        '-dProcessColorModel=/DeviceCMYK',
        '-dCompress=true',
        '-dCompression=lzw',
        f'-sOutputFile={tiff_path}',
        src_pdf_path
    ]
    try:
        logging.info(f"Ghostscript: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        if result.stderr:
            logging.warning(f"Ghostscript output: {result.stderr}")
        if not os.path.exists(tiff_path) or os.path.getsize(tiff_path) == 0:
            return False, "Ошибка при конвертации с помощью Ghostscript.", None, None, 0, "TIFF не создан."
        file_size = os.path.getsize(tiff_path)
        public_url = f"{public_base_url}/{output_filename}"
        return True, "Успешно", tiff_path, public_url, file_size, ""
    except subprocess.CalledProcessError as e:
        return False, "Ошибка Ghostscript.", None, None, 0, e.stderr
    except Exception as e:
        return False, "Внутренняя ошибка сервера.", None, None, 0, str(e)
