"""
main.py
Точка входа и главный графический интерфейс (GUI) Apple Music Downloader.
"""
from __future__ import annotations
from logger import app_logger, collect_environment_snapshot
import queue
import subprocess
import threading
import customtkinter as ctk

from config import (
    ACCENT_COLOR,
    ACCENT_HOVER,
    AMDL_EXE,
    BASE_DIR,
    BG_COLOR,
    CARD_2_COLOR,
    CARD_COLOR,
    CREDS_FILE,
    GREEN_COLOR,
    MUTED_TEXT,
    QUALITY_OPTIONS,
    RED_COLOR,
    TEXT_COLOR,
    WRAPPER_EXE,
    YELLOW_COLOR,
)
from services import (
    convert_all_m4a_to_mp3,
    is_wrapper_running,
    run_amdl_download,
    search_apple_music,
    start_wrapper_process,
    wait_for_wrapper,
)
from settings_manager import (
    load_settings,
    normalize_url,
    save_settings,
    sync_config_yaml,
)
from setup_dialog import SetupDialog


class App(ctk.CTk):
    def __init__(self):
        self.is_downloading = False

        app_logger.info("Запуск приложения Apple Music Downloader GUI")
        app_logger.debug(f"\n{collect_environment_snapshot()}")

        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Apple Music Downloader")
        self.geometry("980x830")
        self.minsize(880, 720)
        self.configure(fg_color=BG_COLOR)

        self.log_queue = queue.Queue()
        self.wrapper_process: subprocess.Popen | None = None
        self.download_process: subprocess.Popen | None = None
        self.settings = load_settings()

        self.bind_clipboard_shortcuts()

        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.process_log_queue)

        # Проверка первого запуска: если нет настроек или файла creds.txt
        if not self.settings.get("setup_complete") or not CREDS_FILE.exists():
            self.after(200, self.open_setup_wizard)
        else:
            sync_config_yaml(self.settings.get("storefront", "kz"))
            self.update_region_badge()
            self.after(300, self.start_wrapper)

    def bind_clipboard_shortcuts(self):
        """Регистрируем горячие клавиши напрямую на классе Entry, чтобы исключить дублирование."""
        self.bind_class("Entry", "<Control-KeyPress>", self._handle_clipboard_keys)

    def _handle_clipboard_keys(self, event):
        kc = event.keycode
        widget = event.widget

        if kc == 86:  # V / М (Вставка)
            try:
                text = self.clipboard_get()
                try:
                    widget.delete("sel.first", "sel.last")
                except Exception:
                    pass
                widget.insert("insert", text)
            except Exception:
                pass
            return "break"  # Предотвращает стандартную дублирующую вставку

        elif kc == 67:  # C / С (Копирование)
            try:
                selected_text = widget.selection_get()
                self.clipboard_clear()
                self.clipboard_append(selected_text)
            except Exception:
                pass
            return "break"

        elif kc == 65:  # A / Ф (Выделить всё)
            try:
                widget.select_range(0, "end")
                widget.icursor("end")
            except Exception:
                pass
            return "break"

        elif kc == 88:  # X / Ч (Вырезать)
            try:
                selected_text = widget.selection_get()
                self.clipboard_clear()
                self.clipboard_append(selected_text)
                widget.delete("sel.first", "sel.last")
            except Exception:
                pass
            return "break"
    def create_widgets(self):
        # --- Шапка ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(20, 8))

        ctk.CTkLabel(
            header,
            text="Apple Music Downloader",
            font=("Segoe UI", 26, "bold"),
            text_color=TEXT_COLOR,
        ).pack(side="left")

        self.status_pill = ctk.CTkLabel(
            header,
            text="● Готово",
            font=("Segoe UI", 11, "bold"),
            text_color=GREEN_COLOR,
            fg_color=CARD_COLOR,
            corner_radius=16,
            padx=14,
            pady=6,
        )
        self.status_pill.pack(side="right")

        self.settings_btn = ctk.CTkButton(
            header,
            text="⚙ Настройки / Аккаунт",
            width=160,
            height=32,
            corner_radius=14,
            fg_color=CARD_COLOR,
            hover_color=CARD_2_COLOR,
            text_color=TEXT_COLOR,
            font=("Segoe UI", 11, "bold"),
            command=self.open_setup_wizard,
        )
        self.settings_btn.pack(side="right", padx=(0, 10))

        self.region_badge = ctk.CTkLabel(
            header,
            text=f"Регион: {self.settings.get('storefront', 'kz').upper()}",
            font=("Segoe UI", 11, "bold"),
            text_color=MUTED_TEXT,
            fg_color=CARD_COLOR,
            corner_radius=14,
            padx=12,
            pady=6,
        )
        self.region_badge.pack(side="right", padx=(0, 10))

        # --- Выбор качества звука ---
        quality_card = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=18)
        quality_card.pack(fill="x", padx=28, pady=(6, 8))

        quality_row = ctk.CTkFrame(quality_card, fg_color="transparent")
        quality_row.pack(fill="x", padx=18, pady=10)

        ctk.CTkLabel(
            quality_row,
            text="Формат и качество звука:",
            font=("Segoe UI", 12, "bold"),
            text_color=TEXT_COLOR,
        ).pack(side="left", padx=(0, 14))

        saved_quality_code = self.settings.get("quality", "alac")
        initial_label = "Lossless (ALAC)"
        for label, code in QUALITY_OPTIONS.items():
            if code == saved_quality_code:
                initial_label = label
                break

        self.quality_var = ctk.StringVar(value=initial_label)
        self.quality_segmented = ctk.CTkSegmentedButton(
            quality_row,
            values=list(QUALITY_OPTIONS.keys()),
            variable=self.quality_var,
            command=self.on_quality_changed,
            selected_color=ACCENT_COLOR,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=CARD_2_COLOR,
            unselected_hover_color="#262636",
            font=("Segoe UI", 11, "bold"),
            height=32,
            corner_radius=10,
        )
        self.quality_segmented.pack(side="left")

        # --- Поиск треков ---
        search_card = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=18)
        search_card.pack(fill="x", padx=28, pady=(6, 8))

        ctk.CTkLabel(
            search_card,
            text="Поиск трека в каталоге Apple Music",
            font=("Segoe UI", 13, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w", padx=18, pady=(12, 6))

        search_row = ctk.CTkFrame(search_card, fg_color="transparent")
        search_row.pack(fill="x", padx=18, pady=(0, 10))

        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            search_row,
            textvariable=self.search_var,
            placeholder_text="Введите название трека или артиста (например: SICKO MODE Travis Scott)",
            height=40,
            corner_radius=12,
            fg_color=CARD_2_COLOR,
            border_color="#2a2a3a",
            border_width=1,
            font=("Segoe UI", 12),
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self.start_search())

        self.search_button = ctk.CTkButton(
            search_row,
            text="Найти",
            width=110,
            height=40,
            corner_radius=12,
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            font=("Segoe UI", 12, "bold"),
            command=self.start_search,
        )
        self.search_button.pack(side="left")

        self.results_frame = ctk.CTkScrollableFrame(
            search_card,
            height=130,
            corner_radius=12,
            fg_color=CARD_2_COLOR,
        )
        self.results_frame.pack(fill="x", padx=18, pady=(0, 12))

        self.empty_search_label = ctk.CTkLabel(
            self.results_frame,
            text="Результаты поиска появятся здесь — нажмите «Скачать» напротив нужного трека",
            font=("Segoe UI", 11),
            text_color=MUTED_TEXT,
        )
        self.empty_search_label.pack(pady=35)

        # --- Вставка прямой ссылки ---
        link_card = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=18)
        link_card.pack(fill="x", padx=28, pady=(4, 8))

        ctk.CTkLabel(
            link_card,
            text="Или вставьте прямую ссылку Apple Music",
            font=("Segoe UI", 13, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w", padx=18, pady=(10, 4))

        self.url_var = ctk.StringVar()
        self.url_entry = ctk.CTkEntry(
            link_card,
            textvariable=self.url_var,
            placeholder_text="https://music.apple.com/.../song/...",
            height=40,
            corner_radius=12,
            fg_color=CARD_2_COLOR,
            border_color="#2a2a3a",
            border_width=1,
            font=("Segoe UI", 12),
        )
        self.url_entry.pack(fill="x", padx=18, pady=(0, 10))
        self.url_entry.bind("<Return>", lambda e: self.start_download())

        # --- Кнопки действий ---
        actions_card = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=18)
        actions_card.pack(fill="x", padx=28, pady=(4, 8))

        btn_row = ctk.CTkFrame(actions_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(12, 6))

        self.download_button = ctk.CTkButton(
            btn_row,
            text="Скачать по ссылке",
            width=180,
            height=38,
            corner_radius=12,
            fg_color=GREEN_COLOR,
            hover_color="#2fc184",
            text_color="#08130f",
            font=("Segoe UI", 12, "bold"),
            command=self.start_download,
        )
        self.download_button.pack(side="left", padx=(0, 10))

        self.convert_button = ctk.CTkButton(
            btn_row,
            text="Конвертировать m4a в MP3",
            width=200,
            height=38,
            corner_radius=12,
            fg_color=CARD_2_COLOR,
            hover_color="#262636",
            border_width=1,
            border_color="#2a2a3a",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 12, "bold"),
            command=self.convert_files,
        )
        self.convert_button.pack(side="left")

        self.auto_convert = ctk.BooleanVar(value=True)
        self.auto_convert_cb = ctk.CTkCheckBox(
            actions_card,
            text="Автоматически конвертировать в MP3 320 kbps и удалять исходный m4a (для ALAC/AAC)",
            variable=self.auto_convert,
            font=("Segoe UI", 11),
            text_color=TEXT_COLOR,
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            corner_radius=8,
        )
        self.auto_convert_cb.pack(anchor="w", padx=18, pady=(0, 12))

        # --- Лог ---
        log_card = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=18)
        log_card.pack(fill="both", expand=True, padx=28, pady=(4, 18))

        ctk.CTkLabel(
            log_card,
            text="Лог работы",
            font=("Segoe UI", 13, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w", padx=18, pady=(10, 4))

        self.log_text = ctk.CTkTextbox(
            log_card,
            corner_radius=12,
            fg_color="#0b0b12",
            text_color="#a6e3a1",
            font=("Consolas", 11),
        )
        self.log_text.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.log_text.configure(state="disabled")

    def log(self, text):
        app_logger.info(str(text))
        self.log_queue.put(str(text))

    def process_log_queue(self):
        try:
            while True:
                text = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", text + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass

        self.after(100, self.process_log_queue)

    def set_status(self, text, color=GREEN_COLOR):
        self.status_pill.configure(text=f"● {text}", text_color=color)

    def on_quality_changed(self, value):
        code = QUALITY_OPTIONS.get(value, "alac")
        self.settings["quality"] = code
        save_settings(
            email=self.settings.get("email", ""),
            password=self.settings.get("password", ""),
            storefront=self.settings.get("storefront", "kz"),
            quality=code,
            logged_in=self.settings.get("logged_in", False),
        )
        self.log(f"Выбрано качество: {value} (флаг: --{code})")

    def get_current_quality_flag(self) -> str:
        selected_label = self.quality_var.get()
        return QUALITY_OPTIONS.get(selected_label, "alac")

    def open_setup_wizard(self):
        self.settings = load_settings()
        SetupDialog(self, self.settings, self.on_setup_completed)

    def on_setup_completed(self):
        self.settings = load_settings()
        sf = self.settings.get("storefront", "kz")
        self.update_region_badge()
        self.log(f"Настройки сохранены. Активный регион: {sf.upper()}")
        self.start_wrapper()

    def update_region_badge(self):
        sf = self.settings.get("storefront", "kz").upper()
        self.region_badge.configure(text=f"Регион: {sf}")

    def start_wrapper(self):
        if is_wrapper_running():
            self.log("wrapper-lite уже работает на 127.0.0.1:12340.")
            self.set_status("wrapper работает", GREEN_COLOR)
            return

        if not WRAPPER_EXE.exists():
            self.log(f"Не найден wrapper-lite:\n{WRAPPER_EXE}")
            self.set_status("Нет wrapper", RED_COLOR)
            return

        self.log("Запускаю wrapper-lite в фоновом режиме...")

        try:
            self.wrapper_process = start_wrapper_process()
        except OSError as error:
            self.log(f"Не удалось запустить wrapper-lite: {error}")
            self.set_status("Ошибка", RED_COLOR)
            return

        self.set_status("wrapper запускается...", YELLOW_COLOR)

        def _wait():
            success = wait_for_wrapper(timeout_seconds=60, interval=2.0, on_tick=self.log)
            if success:
                self.log("wrapper-lite успешно поднят в фоне (127.0.0.1:12340).")
                self.after(0, lambda: self.set_status("wrapper работает", GREEN_COLOR))
            else:
                self.log("wrapper-lite не ответил за 60 секунд.")
                self.after(0, lambda: self.set_status("Ошибка wrapper", RED_COLOR))

        threading.Thread(target=_wait, daemon=True).start()

    def start_search(self):
        query = self.search_var.get().strip()
        if not query:
            self.log("Введите запрос для поиска.")
            return

        storefront = self.settings.get("storefront", "kz")
        self.search_button.configure(state="disabled", text="Ищу...")
        self.set_status("Поиск треков...", YELLOW_COLOR)
        self.log(f"Ищу в каталоге ({storefront.upper()}): {query}")

        def _search_thread():
            try:
                results = search_apple_music(query, storefront, limit=15)
                self.after(0, lambda: self.render_search_results(results))
            except Exception as err:
                self.log(f"Ошибка при поиске: {err}")
                self.after(0, lambda: self.set_status("Ошибка поиска", RED_COLOR))
            finally:
                self.after(0, lambda: self.search_button.configure(state="normal", text="Найти"))

        threading.Thread(target=_search_thread, daemon=True).start()

    def render_search_results(self, results: list):
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        if not results:
            ctk.CTkLabel(
                self.results_frame,
                text="Ничего не найдено в выбранном регионе. Попробуйте другой запрос.",
                font=("Segoe UI", 11),
                text_color=MUTED_TEXT,
            ).pack(pady=35)
            self.set_status("Готово", GREEN_COLOR)
            return

        self.set_status(f"Найдено: {len(results)}", GREEN_COLOR)

        for item in results:
            track_name = item.get("track_name", "Без названия")
            artist_name = item.get("artist_name", "Неизвестный исполнитель")
            album_name = item.get("album_name", "")
            duration_str = item.get("duration", "")
            track_url = item.get("url", "")

            row = ctk.CTkFrame(self.results_frame, fg_color=CARD_COLOR, corner_radius=10)
            row.pack(fill="x", padx=4, pady=3)

            info_text = f"{track_name} — {artist_name}"
            if album_name:
                info_text += f"  ({album_name})"
            if duration_str:
                info_text += f"  [{duration_str}]"

            lbl = ctk.CTkLabel(
                row,
                text=info_text,
                font=("Segoe UI", 11),
                text_color=TEXT_COLOR,
                anchor="w",
            )
            lbl.pack(side="left", fill="x", expand=True, padx=12, pady=8)

            dl_btn = ctk.CTkButton(
                row,
                text="Скачать",
                width=90,
                height=28,
                corner_radius=8,
                fg_color=GREEN_COLOR,
                hover_color="#2fc184",
                text_color="#08130f",
                font=("Segoe UI", 11, "bold"),
                command=lambda u=track_url, n=f"{artist_name} - {track_name}": self.download_from_search(u, n),
            )
            dl_btn.pack(side="right", padx=8, pady=6)

    def download_from_search(self, track_url: str, display_name: str):
        if not track_url:
            self.log("У выбранного трека отсутствует ссылка.")
            return

        if self.is_downloading or (self.download_process and self.download_process.poll() is None):
            self.log("Загрузка уже идёт, подождите...")
            return

        # Просто записываем текст в поле ввода, не вызывая повторно start_download через bind/trace
        self.url_var.set(track_url)
        self.log(f"Выбран трек: {display_name}")
        self.start_download()

    def start_download(self):
        if self.is_downloading or (self.download_process and self.download_process.poll() is None):
            return

        url = self.url_var.get().strip()
        if not url:
            self.log("Вставьте ссылку Apple Music или выберите трек в поиске.")
            self.set_status("Нет ссылки", RED_COLOR)
            return

        # Активируем флаг и выключаем кнопку
        self.is_downloading = True
        self.download_button.configure(state="disabled")

        storefront = self.settings.get("storefront", "kz")
        url = normalize_url(url, storefront)
        quality_code = self.get_current_quality_flag()
        self.log(f"Запуск скачивания ({storefront.upper()}, качество: {self.quality_var.get()}): {url}")

        download_errors = []
        is_codec_missing = False

        def _log_wrapper(line: str):
            nonlocal is_codec_missing
            line_str = str(line)
            lower_line = line_str.lower()

            if "load config failed" in lower_line or "parse config.yaml" in lower_line:
                download_errors.append("Ошибка структуры config.yaml.")
            if "no codec found" in lower_line:
                is_codec_missing = True
                download_errors.append("Нет кодека Dolby Atmos для этого трека.")
            elif "404 not found" in lower_line:
                download_errors.append("Трек не найден (404 Not Found).")
            elif "failed to rip" in lower_line:
                download_errors.append(f"Ошибка рипа: {line_str}")
            elif "invalid ckc" in lower_line:
                download_errors.append("Ошибка лицензии Apple (Invalid CKC).")
            elif "the process cannot access the file" in lower_line:
                download_errors.append("Конфликт доступа к файлу в системе.")

            self.log(line_str)

        def _unlock_ui():
            self.is_downloading = False
            self.download_button.configure(state="normal")

        def _on_finish(returncode, proc):
            self.download_process = None

            if returncode == 0 and not download_errors:
                self.log("Этап 1/2: Загрузка оригинала завершена успешно.")
                if quality_code == "atmos":
                    self.log("Dolby Atmos скачан как многоканальный аудиофайл (конвертация в MP3 пропущена).")
                    self.after(0, lambda: self.set_status("Готово", GREEN_COLOR))
                    self.after(0, _unlock_ui)
                elif self.auto_convert.get():
                    self.log("Этап 2/2: Начинаю конвертацию m4a в MP3 320 kbps...")
                    # Передаём _unlock_ui внутрь конвертера — UI разблокируется только после FFmpeg!
                    self.after(0, lambda: self.convert_files(on_done_callback=_unlock_ui))
                else:
                    self.after(0, lambda: self.set_status("Готово", GREEN_COLOR))
                    self.after(0, _unlock_ui)
            else:
                err_msg = download_errors[0] if download_errors else f"Код возврата: {returncode}"
                app_logger.error(f"Download aborted: {err_msg}")
                if is_codec_missing:
                    self.log("Внимание: У этого трека нет версии Dolby Atmos! Переключите качество на ALAC или AAC.")
                else:
                    self.log(f"Загрузка прервана: {err_msg}")
                self.after(0, lambda: self.set_status("Ошибка загрузки", RED_COLOR))
                self.after(0, _unlock_ui)

        try:
            self.download_process = run_amdl_download(
                url=url,
                quality_code=quality_code,
                log_callback=_log_wrapper,
                on_finish_callback=_on_finish,
            )
        except Exception as err:
            self.is_downloading = False
            self.download_button.configure(state="normal")
            app_logger.exception("Исключение при вызове amdl:")
            self.log(f"Ошибка запуска загрузки: {err}")
            self.set_status("Ошибка", RED_COLOR)

    def convert_files(self, on_done_callback=None):
        self.set_status("Конвертация в MP3...", YELLOW_COLOR)
        self.convert_button.configure(state="disabled")

        def _worker():
            try:
                converted, failed = convert_all_m4a_to_mp3(log_callback=self.log)
                self.log(f"Конвертация завершена. Успешно: {converted}. Ошибок: {failed}.")
                self.after(0, lambda: self.set_status("Готово", GREEN_COLOR))
            except Exception as err:
                self.log(str(err))
                self.after(0, lambda: self.set_status("Ошибка ffmpeg", RED_COLOR))
            finally:
                self.after(0, lambda: self.convert_button.configure(state="normal"))
                if on_done_callback:
                    self.after(0, on_done_callback)

        threading.Thread(target=_worker, daemon=True).start()

    def on_close(self):
        self.log("Закрываю приложение...")

        if self.download_process and self.download_process.poll() is None:
            self.download_process.terminate()

        if self.wrapper_process and self.wrapper_process.poll() is None:
            self.wrapper_process.terminate()

        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
