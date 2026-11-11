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
    CREDS_FILE,
    INTERNAL_DIR,
    SETTINGS_FILE,
    WRAPPER_URL,
)


def find_ffmpeg() -> Path | None:
    """Ищет ffmpeg в internal, корне проекта, папке пользователя или в PATH."""
    home = Path.home()
    candidates = [
        INTERNAL_DIR / "ffmpeg.exe",
        INTERNAL_DIR / "bin" / "ffmpeg.exe",
        BASE_DIR / "ffmpeg.exe",
        BASE_DIR / "bin" / "ffmpeg.exe",
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
) -> None:
    """Сохраняет пользовательские параметры в JSON, creds.txt и обновляет config.yaml."""
    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    current = load_settings()
    current.update({
        "email": email.strip(),
        "password": password,
        "storefront": storefront.strip().lower(),
        "quality": quality.strip().lower(),
        "setup_complete": True,
        "logged_in": logged_in,
    })

    SETTINGS_FILE.write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    CREDS_FILE.write_text(f"{email.strip()}:{password}\n", encoding="utf-8")
    sync_config_yaml(storefront.strip().lower())


def sync_config_yaml(storefront: str) -> None:
    """Генерирует строго валидный config.yaml для amdl без синтаксических ошибок."""
    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)

    alac_path = (BASE_DIR / "AM-Lossless").resolve().as_posix()
    aac_path = (BASE_DIR / "AM-AAC").resolve().as_posix()
    atmos_path = (BASE_DIR / "AM-Atmos").resolve().as_posix()
    mv_path = (BASE_DIR / "AM-MV").resolve().as_posix()

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
  artwork-size: 3000
  artwork-format: "jpg"
  artwork-embed: true
  artwork-save-animated: false
  artwork-emby-animated: false
  artwork-dl-for-playlist: false
  artwork-save-artist: false
  lyrics-embed: true
  lyrics-save-file: false
  lyrics-type: "lrc"
  lyrics-extra: false
  lyrics-format: "lrc"
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