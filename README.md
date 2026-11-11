# Apple Music Downloader GUI (AMDL GUI)

A graphical interface built with CustomTkinter for downloading tracks, albums, and music videos from Apple Music, with automatic conversion to 320 kbps MP3 using FFmpeg.

> **Special thanks to the original AMDL developers** for creating the core downloading and decryption technology that makes this project possible.

## 🚀 Installation

Everything is installed and launched through a single file:

1. Go to the **Releases** section on the right side of the repository (the blue link with the latest version).
2. Download the `AMDL-Setup.exe` installer.
3. Run it — it will automatically prepare the environment and launch the application.

## 🛠 Features & Architecture

- **Strict two-phase pipeline:** Downloading and conversion are separated. `amdl` finishes decryption and defragmentation of the `.m4a` file, closes the file handle, and only then FFmpeg transcodes the track to MP3. This prevents file-locking conflicts.
- **Automatic metadata normalization:** Tags such as artist, album, track number, and title are extracted directly from the audio stream using `ffprobe`. Files are organized using the following structure: `Artist / Album / Track Number. Title.mp3`.
- **Cover art and lyrics transfer:** Album covers and `.lrc` lyrics files are synchronized with the MP3 output folder without creating orphaned folders.
- **Catalogs and regions:** Supports searching and downloading through Apple Music storefronts in different countries, including KZ, US, RU, and others.

## 💡 Credits & Sources

This repository is a GUI wrapper and post-processing pipeline built around existing tools:

- **Core downloader:** Based on the `amdl` CLI utility and the `wrapper-lite` emulator (QEMU). Huge thanks to the original developers for implementing the networking and decryption functionality.
- **Interface:** Built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) by Tom Schimansky.
- **Conversion:** Powered by [FFmpeg](https://ffmpeg.org/).

## 🤝 For Developers

The project architecture is open and organized into modules:

- `main.py` — Window lifecycle, user-event handling, and the blocking UI pipeline.
- `services.py` — Launching `amdl.exe`, extracting tags with `ffprobe`, managing `ffmpeg.exe`, and cleaning directories.
- `settings_manager.py` — Synchronizing the dynamic `config.yaml` with user settings.
- `config.py` — Paths, environment variables, and quality formats.

Improvements, bug fixes, and pull requests are welcome.
