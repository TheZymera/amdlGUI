"""
settings_manager.py
Управление пользовательскими настройками, конфигами и утилитами:
- Чтение и запись user_settings.json
- Генерация и синхронизация config.yaml для amdl
- Сохранение creds.txt
- Подмена региона в ссылках Apple Music
- Поиск ffmpeg в папках проекта и системе
"""

import json
import re
import shutil
from pathlib import Path

from config import (
    BASE_DIR,
    CONFIG_YAML,
    FFMPEG_EXE,
    INTERNAL_DIR,
    SETTINGS_FILE,
    WRAPPER_URL,
)


def find_ffmpeg() -> Path | None:
    """Ищет ffmpeg в internal, корне проекта, папке пользователя или в PATH."""
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


def load_settings() -> dict:
    """Загружает сохраненные настройки из user_settings.json."""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_settings(
    email: str,
    password: str,
    storefront: str,
    quality: str = "alac",
    logged_in: bool = False,
    download_artwork: bool | None = None,
) -> None:
    """Сохраняет пользовательские параметры в JSON, creds.txt и обновляет config.yaml."""
    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    current = load_settings()

    if download_artwork is None:
        download_artwork = current.get("download_artwork", True)

    current.update({
        "email": email.strip(),
        "password": password,
        "storefront": storefront.strip().lower(),
        "quality": quality.strip().lower(),
        "download_artwork": bool(download_artwork),
        "setup_complete": True,
        "logged_in": logged_in,
    })

    SETTINGS_FILE.write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sync_config_yaml(storefront.strip().lower(), download_artwork=bool(download_artwork))


def sync_config_yaml(storefront: str, download_artwork: bool | None = None) -> None:
    """Генерирует строго валидный config.yaml с динамическими путями для текущей системы."""
    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)

    if download_artwork is None:
        download_artwork = load_settings().get("download_artwork", True)

    artwork_embed = "true" if download_artwork else "false"
    artwork_format = '"jpg"' if download_artwork else '""'

    alac_dir = BASE_DIR / "AM-Lossless"
    aac_dir = BASE_DIR / "AM-AAC"
    atmos_dir = BASE_DIR / "AM-Atmos"
    mv_dir = BASE_DIR / "AM-MV"

    for folder in (alac_dir, aac_dir, atmos_dir, mv_dir):
        folder.mkdir(parents=True, exist_ok=True)

    alac_path = alac_dir.resolve().as_posix()
    aac_path = aac_dir.resolve().as_posix()
    atmos_path = atmos_dir.resolve().as_posix()
    mv_path = mv_dir.resolve().as_posix()

    artwork_embed = "true" if download_artwork else "false"
    artwork_format = '"jpg"' if download_artwork else '""'

    yaml_content = f"""general:
  lite-server: "{WRAPPER_URL}"
  media-user-token: ""
  authorization-token: ""
  language: "ru-RU"
  storefront: "{storefront}"
  exit-on-error: false
  max-memory-limit: 0
  proxy: ""

media:
  alac-max: 192000
  alac-fix: true
  atmos-max: 2768
  aac-type: "aac"
  get-m3u8-mode: "all"
  mv-max: 2160
  mv-audio-type: "atmos"

metadata:
  artwork:
    format: {artwork_format}
    embed: {artwork_embed}
    save-animated: false
    emby-animated: false
    dl-for-playlist: false
    save-artist: false
  lyrics:
    embed: true
    save-file: false
    type: "lrc"
    extra: false
    format: "lrc"
  tags:
    itunes-id: false
    sort-order: false
    use-songinfo-for-playlist: false

paths:
  alac: "{alac_path}"
  atmos: "{atmos_path}"
  aac: "{aac_path}"
  mv: "{mv_path}"
  song-file: ""
  album-folder: ""
  playlist-folder: ""
  artist-folder: ""
  apple-master: false
  clean: false
  explicit: false
  limit-max: 200

convert:
  after-download: false
  format: "mp3"
  ffmpeg-path: "ffmpeg"
  extra-args: ""
  delete-bad-alac: false
  check-bad-alac: false
  skip-if-source-matches: false
  keep-original: true
  with-metadata: true
  skip-lossy-to-lossless: true
  warn-lossy-to-lossless: true
"""
    CONFIG_YAML.write_text(yaml_content, encoding="utf-8")

def normalize_url(url: str, storefront: str) -> str:
    """Подменяет двухбуквенный код региона в ссылке Apple Music, сохраняя параметры трека."""
    return re.sub(
        r"(music\.apple\.com/)[a-z]{2}(?=[/-])",
        r"\1" + storefront,
        url.strip(),
    )