import os
import subprocess
import logging

# Настройка логирования для этого модуля
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_page_count(pdf_path: str) -> int | None:
    """
    Получает количество страниц в PDF-файле с помощью утилиты pdfinfo.
    Это более надежный метод, чем использование Ghostscript.
    Возвращает количество страниц или None в случае ошибки.
    """
    try:
        logging.info(f"Подсчет страниц для файла: {pdf_path} с помощью pdfinfo")
        command = ['pdfinfo', pdf_path]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        for line in result.stdout.splitlines():
            if line.lower().startswith('pages:'):
                page_count = int(line.split(':')[1].strip())
                logging.info(f"Найдено страниц: {page_count}")
                return page_count
        
        logging.warning(f"Не удалось найти 'Pages:' в выводе pdfinfo для {pdf_path}.")
        return None
    except FileNotFoundError:
        logging.error("Критическая ошибка: утилита 'pdfinfo' не найдена. Убедитесь, что пакет 'poppler-utils' установлен в Docker-контейнере.")
        return None
    except subprocess.CalledProcessError as e:
        logging.error(f"Утилита pdfinfo завершилась с ошибкой: {e.stderr}")
        return None
    except Exception:
        logging.exception("Непредвиденная ошибка при подсчете страниц с помощью pdfinfo.")
        return None


def process_pdf(src_pdf_path, filename, tmp_dir, publish_dir, public_base_url, gs_path, dpi_default):
    """
    Основная функция обработки PDF: проверка страниц и конвертация в TIFF.
    """
    # 1. Проверяем количество страниц с помощью надежного метода
    pages = get_page_count(src_pdf_path)

    if pages is None:
        return False, "Ошибка: не удалось проанализировать PDF-файл.", None, None, 0, "Проверьте логи сервера для деталей."

    if pages > 1:
        return False, f"Ошибка: бот принимает только одностраничные PDF. В вашем файле {pages} страниц.", None, None, 0, ""

    # 2. Конвертируем файл в TIFF с помощью Ghostscript
    output_filename = os.path.splitext(filename)[0] + ".tiff"
    tiff_path = os.path.join(publish_dir, output_filename)
    
    # Команда для конвертации. -sDEVICE=tiffscaled для сжатия LZW, -dNOPAUSE -dBATCH для автоматического режима
    command = [
        gs_path,
        '-q',
        '-dNOPAUSE',
        '-dBATCH',
        f'-r{dpi_default}',
        '-sDEVICE=tiffscaled', # Используем сжатие LZW
        f'-sOutputFile={tiff_path}',
        src_pdf_path
    ]

    try:
        logging.info(f"Запуск конвертации Ghostscript: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        if result.stderr:
            logging.warning(f"Ghostscript вернул предупреждения: {result.stderr}")
            
        if not os.path.exists(tiff_path) or os.path.getsize(tiff_path) == 0:
            logging.error("Конвертация завершилась, но выходной файл не создан или пуст.")
            return False, "Ошибка при конвертации файла.", None, None, 0, "Выходной TIFF не был создан."

        file_size = os.path.getsize(tiff_path)
        public_url = f"{public_base_url}/{output_filename}"
        logging.info(f"Файл успешно сконвертирован в {tiff_path}")
        
        return True, "Успешно", tiff_path, public_url, file_size, ""

    except subprocess.CalledProcessError as e:
        error_message = f"Ghostscript завершился с ошибкой: {e.stderr}"
        logging.error(error_message)
        return False, "Ошибка при конвертации файла.", None, None, 0, error_message
    except Exception:
        logging.exception("Непредвиденная ошибка во время конвертации.")
        return False, "Внутренняя ошибка сервера при конвертации.", None, None, 0, "Проверьте логи для деталей."
