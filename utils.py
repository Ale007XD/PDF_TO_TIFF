import os

def is_safe_filename(fn):
    forbidden = ["..", "/", "\\"]
    return not any(x in fn for x in forbidden) and fn.strip() != ""

def get_file_size_mb(file):
    # aiogram Document
    return file.file_size / 1024 / 1024
