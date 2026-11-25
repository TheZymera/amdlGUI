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
import atexit
import signal
from components import ensure_executable, ensure_ffmpeg, find_ffmpeg

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

_wrapper_proc: subprocess.Popen | None = None


def kill_process_tree(proc: subprocess.Popen | None) -> None:
    """Мгновенно завершает процесс вместе со всеми его дочерними процессами (QEMU/FFmpeg)."""
    if proc is None or proc.poll() is not None:
        return

    try:
        if IS_WIN:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def start_wrapper_process() -> subprocess.Popen:
    """Запускает wrapper-lite-qemu в изолированной группе процессов без окна консоли."""
    global _wrapper_proc

    if _wrapper_proc is not None and _wrapper_proc.poll() is None:
        return _wrapper_proc

    if not WRAPPER_EXE.exists():
        raise FileNotFoundError(f"Файл {WRAPPER_EXE.name} не найден в {WRAPPER_DIR}")

    ensure_executable(WRAPPER_EXE)

    popen_kwargs: dict = {
        "cwd": str(WRAPPER_DIR),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if IS_WIN:
        popen_kwargs["creationflags"] = CREATE_NO_WINDOW
    else:
        popen_kwargs["start_new_session"] = True

    _wrapper_proc = subprocess.Popen([str(WRAPPER_EXE)], **popen_kwargs)
    return _wrapper_proc


def cleanup_wrapper_processes() -> None:
    """Мгновенно завершает wrapper-lite и отвязанные процессы QEMU."""
    if IS_WIN:
        # Сначала убиваем wrapper, чтобы он не перезапустил QEMU, затем сам эмулятор
        for exe_name in ("wrapper-lite-qemu.exe", "qemu-system-x86_64.exe", "qemu-system-aarch64.exe"):
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", exe_name],
                    creationflags=CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                )
            except Exception:
                pass
    else:
        for proc_name in ("wrapper-lite-qemu", "qemu-system-x86_64", "qemu-system-aarch64"):
            try:
                subprocess.run(
                    ["pkill", "-9", "-x", proc_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                )
            except Exception:
                pass


def stop_wrapper_process(proc: subprocess.Popen | None = None) -> None:
    """Останавливает wrapper-lite и все дочерние процессы QEMU, включая отвязанные."""
    global _wrapper_proc

    if proc is not None and proc is not _wrapper_proc:
        kill_process_tree(proc)

    if _wrapper_proc is not None:
        kill_process_tree(_wrapper_proc)
        _wrapper_proc = None

    cleanup_wrapper_processes()
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
        if _wrapper_proc is not None and _wrapper_proc.poll() is not None:
            if on_tick:
                on_tick(f'wrapper-lite завершился досрочно (код: {_wrapper_proc.returncode}).')
            return False
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
    ensure_executable(WRAPPER_EXE)
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
    target_roots = list(DOWNLOAD_FOLDERS)
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
