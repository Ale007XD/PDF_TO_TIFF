import os

def is_safe_filename(fn):
    forbidden = ["..", "/", "\\"]
    return not any(x in fn for x in forbidden) and fn.strip() != ""

def get_file_size_mb(file):
    # aiogram Document или путь до файла
    if hasattr(file, "file_size"):
        return file.file_size / 1024 / 1024
    elif isinstance(file, str) and os.path.isfile(file):
        return os.path.getsize(file) / 1024 / 1024
    else:
        raise ValueError("Некорректный тип для вычисления размера файла")
