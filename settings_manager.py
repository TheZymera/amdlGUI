"""
settings_manager.py
Управление пользовательскими настройками, конфигами и утилитами:
- Чтение и запись user_settings.json
- Генерация и синхронизация config.yaml для amdl
- Подмена региона в ссылках Apple Music
"""

import json
import re
from components import find_ffmpeg
from config import (
    AAC_OUTPUT_DIR,
    ALAC_OUTPUT_DIR,
    ATMOS_OUTPUT_DIR,
    CONFIG_YAML,
    INTERNAL_DIR,
    MV_OUTPUT_DIR,
    SETTINGS_FILE,
    WRAPPER_URL,
    ensure_music_dirs,
)


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
    """Сохраняет пользовательские параметры в JSON и обновляет config.yaml."""
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
    """Генерирует строго валидный config.yaml с динамическими путями в Music/AMDL_music."""
    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    ensure_music_dirs()

    if download_artwork is None:
        download_artwork = load_settings().get("download_artwork", True)

    artwork_embed = "true" if download_artwork else "false"
    artwork_format = '"jpg"' if download_artwork else '""'

    alac_path = ALAC_OUTPUT_DIR.resolve().as_posix()
    aac_path = AAC_OUTPUT_DIR.resolve().as_posix()
    atmos_path = ATMOS_OUTPUT_DIR.resolve().as_posix()
    mv_path = MV_OUTPUT_DIR.resolve().as_posix()

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