# filename: common/files/utils.py

import os


def is_file_type(file_type: str, file_name: str) -> bool:
    ext = os.path.splitext(file_name.lower())[1]

    file_type_map = {
        "pdf": [".pdf"],
        "image": [".jpg", ".jpeg", ".png", ".webp"],
        "word": [".doc", ".docx"],
        "text": [".txt"],
    }

    allowed_extensions = file_type_map.get(file_type.lower(), [])

    return ext in allowed_extensions


def is_pdf_file(file_name: str) -> bool:
    return is_file_type("pdf", file_name)


def is_image_file(file_name: str) -> bool:
    return is_file_type("image", file_name)
