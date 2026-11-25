"""
config.py
Конфигурация проекта: пути, константы интерфейса, регионы и режимы качества.
"""

import sys
from pathlib import Path
import subprocess
import os

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


def get_system_music_dir() -> Path:
    """Returns the OS Music directory on Windows, Linux, and macOS."""
    if sys.platform == "win32":
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                raw_path, _ = winreg.QueryValueEx(key, "My Music")
                return Path(os.path.expandvars(raw_path))
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            out = subprocess.check_output(["xdg-user-dir", "MUSIC"], text=True).strip()
            if out:
                return Path(out)
        except Exception:
            pass

    return Path.home() / "Music"


MUSIC_OUTPUT_DIR = get_system_music_dir() / "AMDL_music"
ALAC_OUTPUT_DIR = MUSIC_OUTPUT_DIR / "AM-Lossless"
AAC_OUTPUT_DIR = MUSIC_OUTPUT_DIR / "AM-AAC"
ATMOS_OUTPUT_DIR = MUSIC_OUTPUT_DIR / "AM-Atmos"
MV_OUTPUT_DIR = MUSIC_OUTPUT_DIR / "AM-MV"

# Папки для загрузки треков (в системной папке Музыка/AMDL_music)
DOWNLOAD_FOLDERS = [
    ALAC_OUTPUT_DIR,
    AAC_OUTPUT_DIR,
    ATMOS_OUTPUT_DIR,
]


def ensure_music_dirs() -> None:
    for folder in (MUSIC_OUTPUT_DIR, ALAC_OUTPUT_DIR, AAC_OUTPUT_DIR, ATMOS_OUTPUT_DIR, MV_OUTPUT_DIR):
        folder.mkdir(parents=True, exist_ok=True)

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
    ALAC_OUTPUT_DIR,
    AAC_OUTPUT_DIR,
    ATMOS_OUTPUT_DIR,
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
