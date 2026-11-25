# AMDL GUI — Apple Music Downloader

A cross-platform desktop graphical interface (Windows & Linux) built with Python and CustomTkinter for searching, downloading, and converting Apple Music tracks in **Lossless (ALAC)**, **High Quality (AAC)**, and **Dolby Atmos** formats.

---

## Shout-Out to the AMDL Developers

This GUI is built on top of the open-source Apple Music downloader ecosystem. Massive credit and thanks to the developers who created and maintain the core downloader and decryption backend:

* **[zhaarey](https://github.com/zhaarey/apple-music-downloader)** — creator and maintainer of the `amdl` core CLI downloader.
* **[WorldObservationLog](https://github.com/WorldObservationLog/wrapper)** — creator of `wrapper` / `wrapper-lite`, the local decryption backend service.
* **Sorrow** — author of the original Apple Music downloader script.
* **Sendy McSenderson** — contributor of the streaming download-and-decrypt implementation.
* **[itouakirai](https://github.com/itouakirai/go-mp4tag)** — contributor and author of `go-mp4tag` for MP4 container metadata tagging.

---

## What Is This?

**AMDL GUI** wraps the `amdl` command-line tool and `wrapper-lite` decryption service into a single offline-ready desktop application:

* **Built-in Catalog Search & Direct Links:** Search tracks directly via the iTunes Search API or paste any `music.apple.com` song/album URL.
* **Multiple Audio Formats:** Download original **ALAC (up to 24-bit/192kHz)**, **AAC**, or **Dolby Atmos (E-AC-3)** streams.
* **Automatic MP3 320 kbps Conversion:** Optionally converts downloaded `.m4a` tracks into tagged 320 kbps `.mp3` files with embedded album artwork via FFmpeg.
* **OS Music Library Integration:** Automatically organizes downloads into your system Music directory (`Music/AMDL_music/AM-Lossless`, `AM-AAC`, `AM-Atmos`) with a one-click folder button in the app.

---

## What You Require

* **Operating System:** Windows 10/11 (64-bit) or Linux (`x86_64` with `tk` / X11 or Wayland).
* **Active Apple Music Subscription:** Required to authenticate your session and stream/download audio.
* **Disk Space & CPU Virtualization:** ~500 MB free disk space. On Windows, WHPX/Hyper-V or standard QEMU acceleration is used automatically by the bundled `wrapper-lite` guest.
* **Installation Path (Windows):** Install into a Latin-character path (default: `%LocalAppData%\AMDL`) so the bundled QEMU service starts without path encoding errors.

---

## How to Install

### Windows
1. Open the **[GitHub Releases Page](https://github.com/TheZymera/amdl/releases/latest)** and download **`AMDL-Setup.exe`**.
2. Run **`AMDL-Setup.exe`** and follow the setup wizard (keep the default path `%LocalAppData%\AMDL`).
3. Launch **AMDL** from the Start Menu or Desktop shortcut and complete the first-time account setup.

### Linux (`x86_64`)
1. Open the **[GitHub Releases Page](https://github.com/TheZymera/amdl/releases/latest)** and download **`AMDL-1.2.0-linux-x86_64.tar.gz`**.
2. Extract the archive and run the installer script in your terminal:
   ```bash
   tar -xzf AMDL-1.2.0-linux-x86_64.tar.gz
   cd AMDL-1.2.0-linux-x86_64
   ./install.sh
