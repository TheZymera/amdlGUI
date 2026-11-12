"""
services.py
Бизнес-логика, внешние процессы и API:
- Управление wrapper-lite фоновым сервисом
- Поиск треков через публичный iTunes API
- Запуск загрузки amdl.exe
- Пакетная конвертация m4a в mp3 через ffmpeg
"""

import json
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

from config import (
    AMDL_EXE,
    DOWNLOAD_FOLDERS,
    INTERNAL_DIR,
    WRAPPER_DIR,
    WRAPPER_EXE,
    WRAPPER_HOST,
    WRAPPER_PORT,
    WRAPPER_URL,
    BASE_DIR,
    CREATE_NO_WINDOW, 
)
from settings_manager import find_ffmpeg


def is_wrapper_running() -> bool:
    """Проверяет доступность порта бэкенда wrapper-lite."""
    try:
        with socket.create_connection((WRAPPER_HOST, WRAPPER_PORT), timeout=1):
            return True
    except OSError:
        return False


def get_audio_metadata(file_path: Path, ffmpeg_bin: Path) -> dict:
    """Извлекает теги (artist, album, title, track) из m4a с помощью ffprobe."""
    ffprobe_bin = ffmpeg_bin.parent / "ffprobe.exe"
    if not ffprobe_bin.exists():
        ffprobe_bin = "ffprobe"

    cmd = [
        str(ffprobe_bin),
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        str(file_path),
    ]

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
        data = json.loads(res.stdout)
        tags = data.get("format", {}).get("tags", {})
        return {k.lower(): v for k, v in tags.items()}
    except subprocess.TimeoutExpired:
        return {}
    except Exception:
        return {}


def sanitize_filename(name: str) -> str:
    """Удаляет запрещенные в Windows символы для имен папок и файлов."""
    return re.sub(r'[<>:"/\\|?*]', "", name).strip()

def start_wrapper_process() -> subprocess.Popen:
    """Запускает wrapper-lite-qemu полностью в фоне без окна консоли."""
    if not WRAPPER_EXE.exists():
        raise FileNotFoundError(f"Файл {WRAPPER_EXE.name} не найден в {WRAPPER_DIR}")

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


def convert_all_m4a_to_mp3(log_callback: Callable[[str], None]) -> tuple[int, int]:
    ffmpeg_bin = find_ffmpeg()
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg не найден на устройстве!")

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
            tags = get_audio_metadata(file, ffmpeg_bin)
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

            cmd = [
                str(ffmpeg_bin),
                "-y",
                "-i",
                str(file),
                "-c:v",
                "copy",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "320k",
                "-map_metadata",
                "0",
                str(mp3_file),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
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
                if old_dir.resolve() != target_dir.resolve() and old_dir.exists():
                    for extra in list(old_dir.iterdir()):
                        if extra.is_file() and extra.suffix.lower() in [".jpg", ".jpeg", ".png", ".lrc", ".webp"]:
                            dest = target_dir / extra.name
                            if not dest.exists():
                                shutil.move(str(extra), str(dest))
                            else:
                                extra.unlink(missing_ok=True)

                # Удаляем старую папку альбома, если в ней ничего не осталось
                if old_dir != base_folder and old_dir.exists():
                    remaining_files = [f for f in old_dir.iterdir() if f.is_file()]
                    if not remaining_files:
                        try:
                            shutil.rmtree(old_dir)
                        except Exception:
                            pass

                converted += 1
                log_callback(f"Готово: {clean_filename}")
            else:
                failed += 1
                log_callback(f"Ошибка конвертации {file.name}: {result.stderr[:200]}")

        except Exception as e:
            failed += 1
            log_callback(f"Ошибка обработки {file.name}: {e}")

    return converted, failed
