import os
import subprocess
import shutil
import magic
import filetype
from datetime import datetime

def process_pdf(src_pdf_path, orig_name, tmp_dir, publish_dir, public_url, gs_path, dpi):
    # Проверки
    # MIME и сигнатура
    if not (magic.from_file(src_pdf_path, mime=True) == 'application/pdf' and filetype.guess(src_pdf_path).mime == 'application/pdf'):
        return False, "Файл не PDF", None, None, 0, ""

    # Проверка размера напрямую (файл на диске)
    if os.path.getsize(src_pdf_path) > 100*1024*1024:
        return False, "Слишком большой файл", None, None, 0, ""

    # Ghostscript: получить число страниц
    checker = [
        gs_path, "-q", "-dNODISPLAY", "-c",
        f"({src_pdf_path}) (r) file runpdfbegin pdfpagecount = quit"
    ]
    try:
        out = subprocess.check_output(checker, timeout=10)
        pages = int(out.decode().strip())
        if pages != 1:
            return False, "PDF должен содержать ровно одну страницу", None, None, 0, ""
    except Exception as e:
        return False, "Ошибка при проверке количества страниц. Проверьте PDF.", None, None, 0, str(e)

    # Проверка на зашифрованность
    try:
        encrypted_check = [
            gs_path, "-q", "-dNODISPLAY", "-c",
            f"({src_pdf_path}) (r) file runpdfbegin pdfhasinfo = quit"
        ]
        subprocess.check_output(encrypted_check, timeout=10)
    except Exception as e:
        return False, "Зашифрованные PDF не поддерживаются", None, None, 0, str(e)

    # Формирование путей
    today = datetime.now().strftime('%Y_%m_%d')
    target_dir = os.path.join(publish_dir, today)
    os.makedirs(target_dir, exist_ok=True)

    # Чистое имя файла
    base = os.path.splitext(os.path.basename(orig_name))[0]
    safe_base = "".join([c for c in base if c.isalnum() or c in "_-" ]).rstrip()
    tiff_name = f"{safe_base}.tiff"
    tiff_out_tmp_path = os.path.join(tmp_dir, tiff_name)
    tiff_out_final = os.path.join(target_dir, tiff_name)

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
        proc = subprocess.run(gs_cmd, shell=False, capture_output=True, timeout=300)
        if proc.returncode != 0:
            return False, "Ошибка конвертации", None, None, 0, proc.stderr.decode().strip()
    except Exception as e:
        return False, "Ошибка конвертации", None, None, 0, str(e)

    # sep/tiffgray — чистка
    for f in os.listdir(tmp_dir):
        if f.endswith('.tif') and f != tiff_name:
            try: os.remove(os.path.join(tmp_dir, f))
            except: pass

    # Проверка итогового файла
    if not os.path.exists(tiff_out_tmp_path):
        return False, "TIFF-файл не найден после конвертации", None, None, 0, ""

    # Перемещение в директорию публикации
    shutil.move(tiff_out_tmp_path, tiff_out_final)
    os.umask(0o022) # права
    file_size = os.path.getsize(tiff_out_final)

    # Проверка пути
    if not os.path.abspath(tiff_out_final).startswith(os.path.abspath(target_dir)):
        return False, "Ошибка безопасности пути публикации", None, None, 0, ""

    url = f"{public_url}/files/{today}/{tiff_name}"

    return True, "Готово!", tiff_out_final, url, file_size, ""
