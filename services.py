"""
services.py
Бизнес-логика, внешние процессы и API:
- Управление wrapper-lite фоновым сервисом
- Поиск треков через публичный iTunes API
- Запуск загрузки amdl.exe
- Пакетная конвертация m4a в mp3 через ffmpeg
"""
from __future__ import annotations
import json
import mutagen
from mutagen.mp4 import MP4
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable
import re
from pathlib import Path
import shutil
import ssl
import tempfile
import zipfile
import os
import tarfile

from config import (
    AMDL_EXE,
    BASE_DIR,
    CREATE_NO_WINDOW,
    DOWNLOAD_FOLDERS,
    FFMPEG_EXE,
    INTERNAL_DIR,
    IS_WIN,
    WRAPPER_DIR,
    WRAPPER_EXE,
    WRAPPER_HOST,
    WRAPPER_PORT,
    WRAPPER_URL,
)
from settings_manager import find_ffmpeg


def is_wrapper_running() -> bool:
    """Проверяет доступность порта бэкенда wrapper-lite."""
    try:
        with socket.create_connection((WRAPPER_HOST, WRAPPER_PORT), timeout=1):
            return True
    except OSError:
        return False

def _ensure_executable(path: Path) -> None:
    """Выдаёт права на запуск бинарника на Linux/macOS."""
    if not IS_WIN and path.exists():
        path.chmod(path.stat().st_mode | 0o755)


FFMPEG_WIN_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
FFMPEG_LINUX_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"


def ensure_ffmpeg(log_callback: Callable[[str], None]) -> Path:
    """Ищет ffmpeg в internal/ или системе; при отсутствии скачивает под текущую ОС."""
    existing = find_ffmpeg()
    if existing:
        return existing

    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    log_callback(f"FFmpeg не найден локально. Скачиваю бинарник {FFMPEG_EXE.name}...")

    download_url = FFMPEG_WIN_URL if IS_WIN else FFMPEG_LINUX_URL
    archive_name = "ffmpeg.zip" if IS_WIN else "ffmpeg.tar.xz"

    with tempfile.TemporaryDirectory() as tmp_dir:
        archive_path = Path(tmp_dir) / archive_name
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )

        with urllib.request.urlopen(req, timeout=120) as resp, open(archive_path, "wb") as out:
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
                        log_callback(f"\rСкачивание FFmpeg: [{bar}] {percent:5.1f}% ({mb_done:.1f} / {mb_total:.1f} МБ)")
                    else:
                        log_callback(f"\rСкачивание FFmpeg: {mb_done:.1f} МБ...")

        log_callback(f"Архив загружен. Извлекаю {FFMPEG_EXE.name}...")

        if IS_WIN:
            if not zipfile.is_zipfile(archive_path):
                raise RuntimeError("Скачанный файл не является ZIP-архивом.")
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.namelist():
                    if member.endswith("bin/ffmpeg.exe"):
                        with zf.open(member) as src, open(FFMPEG_EXE, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        break
        else:
            if not tarfile.is_tarfile(archive_path):
                raise RuntimeError("Скачанный файл не является TAR.XZ-архивом.")
            with tarfile.open(archive_path, "r:xz") as tf:
                for member in tf.getmembers():
                    if member.isfile() and member.name.endswith("bin/ffmpeg"):
                        src = tf.extractfile(member)
                        if src:
                            with src, open(FFMPEG_EXE, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                        break

    if not FFMPEG_EXE.exists():
        raise RuntimeError(f"Не удалось извлечь {FFMPEG_EXE.name} из загруженного архива.")

    _ensure_executable(FFMPEG_EXE)
    log_callback(f"FFmpeg успешно установлен в internal/{FFMPEG_EXE.name}.")
    return FFMPEG_EXE
def get_audio_metadata(file_path: Path) -> dict:
    """Извлекает теги (artist, album, title, track) из m4a через mutagen без ffprobe.exe."""
    try:
        audio = MP4(str(file_path))
        tags = audio.tags or {}

        def _first(key: str) -> str:
            val = tags.get(key)
            if isinstance(val, list) and val:
                return str(val[0]).strip()
            return str(val).strip() if val else ""

        track_num = ""
        trkn = tags.get("trkn")
        if isinstance(trkn, list) and trkn and isinstance(trkn[0], tuple):
            track_num = str(trkn[0][0])

        return {
            "artist": _first("\xa9ART"),
            "album_artist": _first("aART"),
            "album": _first("\xa9alb"),
            "title": _first("\xa9nam"),
            "track": track_num,
        }
    except Exception:
        try:
            easy = mutagen.File(str(file_path), easy=True)
            if not easy:
                return {}
            return {
                "artist": (easy.get("artist") or [""])[0],
                "album_artist": (easy.get("albumartist") or [""])[0],
                "album": (easy.get("album") or [""])[0],
                "title": (easy.get("title") or [""])[0],
                "track": (easy.get("tracknumber") or [""])[0].split("/")[0],
            }
        except Exception:
            return {}


def sanitize_filename(name: str) -> str:
    """Удаляет запрещенные в Windows символы для имен папок и файлов."""
    return re.sub(r'[<>:"/\\|?*]', "", name).strip()

def _remove_empty_dirs(start_dir: Path, stop_at: Path) -> None:
    """Удаляет пустые папки вверх по дереву до stop_at с учётом задержки блокировки в Windows."""
    current = start_dir
    stop_resolved = stop_at.resolve()

    while current.exists() and current.resolve() != stop_resolved:
        if stop_resolved not in current.resolve().parents:
            break
        try:
            if any(current.iterdir()):
                break
        except OSError:
            break

        removed = False
        for _ in range(5):
            try:
                current.rmdir()
                removed = True
                break
            except OSError:
                time.sleep(0.15)

        if not removed:
            break
        current = current.parent

def start_wrapper_process() -> subprocess.Popen:
    """Запускает wrapper-lite-qemu полностью в фоне без окна консоли."""
    if not WRAPPER_EXE.exists():
        raise FileNotFoundError(f"Файл {WRAPPER_EXE.name} не найден в {WRAPPER_DIR}")

    _ensure_executable(WRAPPER_EXE)

    return subprocess.Popen(
        [str(WRAPPER_EXE)],
        cwd=str(WRAPPER_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )


def wait_for_wrapper(
    timeout_seconds: int = 60,
    interval: float = 2.0,
    on_tick: Callable[[str], None] | None = None,
) -> bool:
    """Ожидает поднятия сервиса на порту 12340 с тайм-аутом."""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if is_wrapper_running():
            return True
        if on_tick:
            on_tick("Ожидаю запуск wrapper-lite...")
        time.sleep(interval)
    return False


def search_apple_music(query: str, storefront: str, limit: int = 15) -> list[dict]:
    """Выполняет поиск треков через открытый Apple iTunes Search API."""
    params = urllib.parse.urlencode({
        "term": query,
        "country": storefront,
        "media": "music",
        "entity": "song",
        "limit": limit,
    })
    api_url = f"https://itunes.apple.com/search?{params}"
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("results", []):
        duration_ms = item.get("trackTimeMillis", 0)
        minutes = (duration_ms // 1000) // 60
        seconds = (duration_ms // 1000) % 60
        duration_str = f"{minutes}:{seconds:02d}" if duration_ms else ""

        raw_url = item.get("trackViewUrl", "")
        clean_url = ""
        if raw_url:
            parsed = urllib.parse.urlparse(raw_url)
            query_params = urllib.parse.parse_qs(parsed.query)

            # Сохраняем параметр ?i=<track_id>, если он есть
            if "i" in query_params:
                track_id = query_params["i"][0]
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?i={track_id}"
            else:
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        results.append({
            "track_name": item.get("trackName", "Без названия"),
            "artist_name": item.get("artistName", "Неизвестный исполнитель"),
            "album_name": item.get("collectionName", ""),
            "duration": duration_str,
            "url": clean_url,
        })
    return results


def run_amdl_download(
        url: str,
        quality_code: str,
        log_callback: Callable[[str], None],
        on_finish_callback: Callable[[int, subprocess.Popen], None],
) -> subprocess.Popen:
    _ensure_executable(WRAPPER_EXE)
    for folder in DOWNLOAD_FOLDERS:
        folder.mkdir(parents=True, exist_ok=True)
    cmd = [str(AMDL_EXE)]

    # Флаги нужны только для aac и atmos. ALAC качается по умолчанию без флагов!
    if quality_code == "aac":
        cmd.append("--aac")
    elif quality_code == "atmos":
        cmd.append("--atmos")

    cmd.append(url)
    log_callback(f"Команда: {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        cwd=str(INTERNAL_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )

    def _reader():
        try:
            for line in process.stdout:
                log_callback(line.rstrip())
        finally:
            process.wait()
            on_finish_callback(process.returncode, process)

    threading.Thread(target=_reader, daemon=True).start()
    return process


def convert_all_m4a_to_mp3(
    log_callback: Callable[[str], None],
    download_artwork: bool = True,
) -> tuple[int, int]:
    ffmpeg_bin = ensure_ffmpeg(log_callback)

    # Ищем во всех выходных папках
    target_roots = [BASE_DIR / "AM-Lossless", BASE_DIR / "AM-AAC", BASE_DIR / "AM-Atmos"]
    m4a_files = []
    for root in target_roots:
        if root.exists():
            m4a_files.extend(root.rglob("*.m4a"))

    if not m4a_files:
        log_callback("Файлы .m4a для конвертации не найдены.")
        return 0, 0

    converted = 0
    failed = 0

    for file in m4a_files:
        try:
            # Читаем метаданные трека
            tags = get_audio_metadata(file)
            artist = tags.get("artist") or tags.get("album_artist") or "Unknown Artist"
            album = tags.get("album") or "Unknown Album"
            title = tags.get("title") or file.stem
            track = tags.get("track", "").split("/")[0]

            # Формируем аккуратное имя: "02. Название.mp3" или "Название.mp3"
            if track and track.isdigit():
                clean_track_name = f"{int(track):02d}. {title}"
            else:
                clean_track_name = title

            clean_artist = sanitize_filename(artist)
            clean_album = sanitize_filename(album)
            clean_filename = sanitize_filename(clean_track_name) + ".mp3"

            # Определяем, в какой базовой директории лежит файл (Lossless/AAC/Atmos)
            base_folder = file.parent
            for root in target_roots:
                if root in file.parents or root == file.parent:
                    base_folder = root
                    break

            # Создаем правильную целевую папку: AM-Lossless / Artist / Album /
            target_dir = base_folder / clean_artist / clean_album
            target_dir.mkdir(parents=True, exist_ok=True)
            mp3_file = target_dir / clean_filename

            log_callback(f"Конвертирую: {clean_artist} - {clean_track_name}")

            artwork_flags = ["-c:v", "copy"] if download_artwork else ["-vn"]

            cmd = [
                str(ffmpeg_bin),
                "-y",
                "-i",
                str(file),
                *artwork_flags,
                "-c:a",
                "libmp3lame",
                "-b:a",
                "320k",
                "-map_metadata",
                "0",
                "-id3v2_version",
                "3",
                str(mp3_file),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,                     
                creationflags=CREATE_NO_WINDOW,
            )        

            if result.returncode == 0 and mp3_file.exists():
                time.sleep(0.15)
                try:
                    file.unlink()
                except PermissionError:
                    time.sleep(0.5)
                    file.unlink(missing_ok=True)

                old_dir = file.parent

                # Переносим сопутствующие файлы (обложки, lrc) из старой папки в новую
                # Удаляем пустую временную папку альбома (и пустых родителей до base_folder)
                if old_dir.resolve() != target_dir.resolve():
                    _remove_empty_dirs(old_dir, base_folder)

                # Удаляем старую папку альбома, если в ней ничего не осталось
                image_exts = {".jpg", ".jpeg", ".png", ".webp"}
                if old_dir.resolve() != target_dir.resolve() and old_dir.exists():
                    for extra in list(old_dir.iterdir()):
                        if not extra.is_file():
                            continue
                        ext = extra.suffix.lower()
                        if ext in image_exts and not download_artwork:
                            extra.unlink(missing_ok=True)
                        elif ext in image_exts | {".lrc"}:
                            dest = target_dir / extra.name
                            if not dest.exists():
                                shutil.move(str(extra), str(dest))
                            else:
                                extra.unlink(missing_ok=True)

                converted += 1
                log_callback(f"Готово: {clean_filename}")
            else:
                failed += 1
                log_callback(f"Ошибка конвертации {file.name}: {result.stderr[:200]}")



        except subprocess.TimeoutExpired:
            failed += 1
            log_callback(f"Таймаут конвертации {file.name} (>120 c). Файл пропущен.")
            # Удаляем недописанный mp3, если ffmpeg успел его создать
            try:
                if mp3_file.exists():
                    mp3_file.unlink(missing_ok=True)
            except Exception:
                pass

        except Exception as e:
            failed += 1
            log_callback(f"Ошибка обработки {file.name}: {e}")

    return converted, failed
