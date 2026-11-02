import os
import re

UNSAFE = re.compile(r"\.\.|\\|[\x00-\x1f]")

FALLBACK_NAME = "attachment"


def clean_name(name: str) -> str:
    name = (name or "").strip()
    if UNSAFE.search(name):
        name = os.path.basename(name.replace("\\", "/"))
    name = name.strip()
    return name or FALLBACK_NAME


def save_attachment(folder: str, file) -> str:
    path = os.path.join(folder, clean_name(file.filename))
    file.save(path)
    return path
