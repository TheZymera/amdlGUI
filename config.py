"""
config.py
Конфигурация проекта: пути, константы интерфейса, регионы и режимы качества.
"""

import sys
from pathlib import Path
import subprocess

IS_WIN = sys.platform == "win32"
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WIN else 0

# Определение базовой директории
# Поддерживает как запуск через python main.py, так и скомпилированный PyInstaller .exe
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent

# Папка для всех внутренних бинарников и служебных файлов
INTERNAL_DIR = BASE_DIR / "internal"
LOGS_DIR = INTERNAL_DIR / "logs"

# Внутренние исполняемые файлы и утилиты
if IS_WIN:
    WRAPPER_DIR = INTERNAL_DIR / "wrapper-lite-qemu-windows-x86_64"
    WRAPPER_EXE = WRAPPER_DIR / "wrapper-lite-qemu.exe"
    AMDL_EXE = INTERNAL_DIR / "amdl.exe"
    FFMPEG_EXE = INTERNAL_DIR / "ffmpeg.exe"
else:
    WRAPPER_DIR = INTERNAL_DIR / "wrapper-lite-qemu-linux-x86_64"
    WRAPPER_EXE = WRAPPER_DIR / "wrapper-lite-qemu"
    AMDL_EXE = INTERNAL_DIR / "amdl"
    FFMPEG_EXE = INTERNAL_DIR / "ffmpeg"

# Файлы конфигурации и учетных данных
CONFIG_YAML = INTERNAL_DIR / "config.yaml"
SETTINGS_FILE = INTERNAL_DIR / "user_settings.json"

# Папки для загрузки треков (находятся в корне, на виду у пользователя)
DOWNLOAD_FOLDERS = [
    BASE_DIR / "AM-Lossless",
    BASE_DIR / "AM-AAC",
    BASE_DIR / "AM-Atmos",
]

# Доступные регионы каталога Apple Music (Storefronts)
STOREFRONTS = {
    "kz": "Казахстан (kz)",
    "us": "США (us)",
    "ru": "Россия (ru)",
    "tr": "Турция (tr)",
    "gb": "Великобритания (gb)",
    "de": "Германия (de)",
    "ua": "Украина (ua)",
    "by": "Беларусь (by)",
    "am": "Армения (am)",
    "ge": "Грузия (ge)",
    "uz": "Узбекистан (uz)",
    "jp": "Япония (jp)",
}

# Режимы качества аудио и соответствующие CLI-флаги для amdl
QUALITY_OPTIONS = {
    "Lossless (ALAC)": "alac",
    "High Quality (AAC)": "aac",
    "Dolby Atmos": "atmos",
}

# Сетевой адрес бэкенда расшифровки wrapper-lite
WRAPPER_HOST = "127.0.0.1"
WRAPPER_PORT = 12340
WRAPPER_URL = f"http://{WRAPPER_HOST}:{WRAPPER_PORT}"

# Цветовая палитра UI (Modern Dark Theme)
BG_COLOR = "#0e0e16"
CARD_COLOR = "#16161f"
CARD_2_COLOR = "#1c1c28"
TEXT_COLOR = "#e6e6f0"
MUTED_TEXT = "#8a8aa3"
ACCENT_COLOR = "#7c5cff"
ACCENT_HOVER = "#6a4be0"
GREEN_COLOR = "#3ddc97"
RED_COLOR = "#ff5c7a"
YELLOW_COLOR = "#f5c542"
