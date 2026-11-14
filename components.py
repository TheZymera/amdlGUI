import json
import shutil
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from config import (
    AMDL_EXE,
    BASE_DIR,
    FFMPEG_EXE,
    INTERNAL_DIR,
    IS_WIN,
    WRAPPER_DIR,
    WRAPPER_EXE,
)

FFMPEG_WIN_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
FFMPEG_LINUX_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"

AMDL_GITHUB_API = "https://api.github.com/repos/zhaarey/apple-music-downloader/releases/latest"
WRAPPER_GITHUB_API = "https://api.github.com/repos/zhaarey/wrapper/releases/latest"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) amdlGUI/1.1"


def ensure_executable(path: Path) -> None:
    """Выдаёт права на запуск бинарника на Linux/macOS (chmod +x)."""
    if not IS_WIN and path.exists():
        path.chmod(path.stat().st_mode | 0o755)


def find_ffmpeg() -> Path | None:
    """Ищет ffmpeg в internal, корне проекта, папке пользователя или в системном PATH."""
    home = Path.home()
    candidates = [
        FFMPEG_EXE,
        INTERNAL_DIR / "bin" / FFMPEG_EXE.name,
        BASE_DIR / FFMPEG_EXE.name,
        BASE_DIR / "bin" / FFMPEG_EXE.name,
        *list(home.glob("OneDrive/Документы/ffmpeg*/bin/ffmpeg.exe")),
        *list(home.glob("Documents/ffmpeg*/bin/ffmpeg.exe")),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return Path(sys_ffmpeg)
    return None


def get_missing_components() -> list[str]:
    """Возвращает список отсутствующих компонентов ядра."""
    missing = []
    if not WRAPPER_EXE.exists():
        missing.append("wrapper-lite")
    if not AMDL_EXE.exists():
        missing.append("amdl")
    if find_ffmpeg() is None:
        missing.append("ffmpeg")
    return missing


def _download_with_progress(
    url: str,
    dest: Path,
    label: str,
    log_callback: Callable[[str], None],
) -> None:
    """Скачивает файл по URL с выводом прогресс-бара в консоль GUI."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        total_size = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        last_ui_update = 0.0
        bar_len = 24

        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)

            now = time.monotonic()
            if now - last_ui_update >= 0.15 or (total_size and downloaded >= total_size):
                last_ui_update = now
                mb_done = downloaded / (1024 * 1024)
                if total_size > 0:
                    percent = min(100.0, downloaded * 100.0 / total_size)
                    filled = int(bar_len * downloaded / total_size)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    mb_total = total_size / (1024 * 1024)
                    log_callback(f"\r{label}: [{bar}] {percent:5.1f}% ({mb_done:.1f} / {mb_total:.1f} МБ)")
                else:
                    log_callback(f"\r{label}: {mb_done:.1f} МБ...")


def _resolve_github_asset_url(api_url: str, os_token: str) -> tuple[str, str]:
    """Находит прямую ссылку на архив под нужную ОС в последнем релизе GitHub."""
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    for asset in data.get("assets", []):
        name = asset.get("name", "").lower()
        if os_token in name and ("amd64" in name or "x86_64" in name):
            return asset["browser_download_url"], asset["name"]

    raise RuntimeError(f"Подходящий релиз для {os_token} не найден в {api_url}")


def _extract_single_binary(archive_path: Path, binary_name: str, target_path: Path) -> None:
    """Извлекает один исполняемый файл из .zip или .tar.* архива."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as zf:
            for member in zf.namelist():
                if Path(member).name == binary_name and not member.endswith("/"):
                    with zf.open(member) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    break
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as tf:
            for member in tf.getmembers():
                if member.isfile() and Path(member.name).name == binary_name:
                    src = tf.extractfile(member)
                    if src:
                        with src, open(target_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                    break
    else:
        raise RuntimeError(f"Неподдерживаемый формат архива: {archive_path.name}")

    if not target_path.exists():
        raise RuntimeError(f"Файл {binary_name} не найден внутри архива {archive_path.name}.")

    ensure_executable(target_path)


def ensure_ffmpeg(log_callback: Callable[[str], None]) -> Path:
    """Ищет ffmpeg; при отсутствии скачивает и распаковывает под текущую ОС."""
    existing = find_ffmpeg()
    if existing:
        return existing

    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    log_callback(f"FFmpeg не найден локально. Скачиваю {FFMPEG_EXE.name}...")

    download_url = FFMPEG_WIN_URL if IS_WIN else FFMPEG_LINUX_URL
    archive_name = "ffmpeg.zip" if IS_WIN else "ffmpeg.tar.xz"

    with tempfile.TemporaryDirectory() as tmp_dir:
        archive_path = Path(tmp_dir) / archive_name
        _download_with_progress(download_url, archive_path, "Скачивание FFmpeg", log_callback)
        log_callback(f"Архив загружен. Извлекаю {FFMPEG_EXE.name}...")
        _extract_single_binary(archive_path, FFMPEG_EXE.name, FFMPEG_EXE)

    log_callback(f"FFmpeg успешно установлен в internal/{FFMPEG_EXE.name}.")
    return FFMPEG_EXE


def ensure_amdl(log_callback: Callable[[str], None]) -> Path:
    """Проверяет наличие amdl; при отсутствии скачивает актуальный релиз с GitHub."""
    if AMDL_EXE.exists():
        ensure_executable(AMDL_EXE)
        return AMDL_EXE

    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    os_token = "windows" if IS_WIN else "linux"
    log_callback(f"Компонент {AMDL_EXE.name} не найден. Получаю релиз с GitHub...")

    url, filename = _resolve_github_asset_url(AMDL_GITHUB_API, os_token)
    with tempfile.TemporaryDirectory() as tmp_dir:
        archive_path = Path(tmp_dir) / filename
        _download_with_progress(url, archive_path, "Скачивание amdl", log_callback)
        log_callback(f"Распаковываю {AMDL_EXE.name}...")
        _extract_single_binary(archive_path, AMDL_EXE.name, AMDL_EXE)

    log_callback(f"Компонент {AMDL_EXE.name} готов к работе.")
    return AMDL_EXE


def ensure_wrapper(log_callback: Callable[[str], None]) -> Path:
    """Проверяет наличие wrapper-lite; при отсутствии скачивает и распаковывает в internal/."""
    if WRAPPER_EXE.exists():
        ensure_executable(WRAPPER_EXE)
        return WRAPPER_EXE

    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    os_token = "windows" if IS_WIN else "linux"
    log_callback("Компонент wrapper-lite не найден. Получаю релиз с GitHub...")

    url, filename = _resolve_github_asset_url(WRAPPER_GITHUB_API, os_token)
    with tempfile.TemporaryDirectory() as tmp_dir:
        archive_path = Path(tmp_dir) / filename
        _download_with_progress(url, archive_path, "Скачивание wrapper-lite", log_callback)
        log_callback("Распаковываю wrapper-lite...")

        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                top_dirs = {Path(n).parts[0] for n in zf.namelist() if Path(n).parts}
                dest_root = INTERNAL_DIR if WRAPPER_DIR.name in top_dirs else WRAPPER_DIR
                dest_root.mkdir(parents=True, exist_ok=True)
                zf.extractall(dest_root)
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r:*") as tf:
                top_dirs = {Path(m.name).parts[0] for m in tf.getmembers() if Path(m.name).parts}
                dest_root = INTERNAL_DIR if WRAPPER_DIR.name in top_dirs else WRAPPER_DIR
                dest_root.mkdir(parents=True, exist_ok=True)
                tf.extractall(dest_root)
        else:
            raise RuntimeError(f"Неподдерживаемый формат архива: {filename}")

    if not WRAPPER_EXE.exists():
        raise RuntimeError(f"Не удалось найти {WRAPPER_EXE.name} после распаковки.")

    ensure_executable(WRAPPER_EXE)
    log_callback("Компонент wrapper-lite успешно установлен.")
    return WRAPPER_EXE