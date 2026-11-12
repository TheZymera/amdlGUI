"""
logger.py
Централизованный логгер с понятными именами файлов (app_YYYY-MM-DD_HH-MM-SS.log)
и автоочисткой: на диске хранится максимум 10 последних файлов логов.
"""

import sys
import platform
import logging
from datetime import datetime
from pathlib import Path
from config import (
    LOGS_DIR,
    AMDL_EXE,
    WRAPPER_EXE,
    CONFIG_YAML,
)

MAX_LOG_FILES = 10

def cleanup_old_logs():
    """Оставляет только последние MAX_LOG_FILES логов, удаляя старые."""
    try:
        log_files = sorted(
            LOGS_DIR.glob("app_*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        for old_file in log_files[MAX_LOG_FILES:]:
            old_file.unlink(missing_ok=True)
    except Exception:
        pass

def setup_logger() -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    cleanup_old_logs()

    # Имя файла с датой и временем запуска: app_2026-11-11_22-30-00.log
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    current_log_file = LOGS_DIR / f"app_{timestamp}.log"

    logger = logging.getLogger("AMDL_GUI")
    logger.setLevel(logging.DEBUG)

    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(current_log_file, encoding="utf-8", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

app_logger = setup_logger()

def collect_environment_snapshot() -> str:
    from settings_manager import find_ffmpeg, load_settings
    settings = load_settings()
    ffmpeg_bin = find_ffmpeg()

    snapshot = [
        "=== ENVIRONMENT SNAPSHOT ===",
        f"OS: {platform.system()} {platform.release()} (arch: {platform.machine()})",
        f"Python: {platform.python_version()} ({sys.executable})",
        f"AMDL EXE exists: {AMDL_EXE.exists()} ({AMDL_EXE})",
        f"WRAPPER EXE exists: {WRAPPER_EXE.exists()} ({WRAPPER_EXE})",
        f"FFMPEG found: {bool(ffmpeg_bin)} ({ffmpeg_bin})",
        f"CONFIG YAML exists: {CONFIG_YAML.exists()}",
        f"Settings: email={bool(settings.get('email'))}, storefront={settings.get('storefront')}, quality={settings.get('quality')}",
        "============================"
    ]
    return "\n".join(snapshot)