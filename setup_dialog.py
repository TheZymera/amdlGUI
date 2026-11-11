"""
setup_dialog.py
Модальное окно первичной настройки и авторизации:
- Ввод логина и пароля Apple ID
- Выбор региона (storefront)
- Интерактивный вход в wrapper-lite с поддержкой отправки кода 2FA
"""

import subprocess
import threading
from typing import Callable

import customtkinter as ctk

from config import (
    ACCENT_COLOR,
    ACCENT_HOVER,
    BG_COLOR,
    CARD_2_COLOR,
    CARD_COLOR,
    GREEN_COLOR,
    MUTED_TEXT,
    RED_COLOR,
    STOREFRONTS,
    TEXT_COLOR,
    WRAPPER_DIR,
    WRAPPER_EXE,
    YELLOW_COLOR,
)
from settings_manager import load_settings, save_settings


class SetupDialog(ctk.CTkToplevel):
    """Модальное окно настройки: Apple ID, регион и вход с 2FA."""

    def __init__(
        self,
        parent,
        current_settings: dict,
        on_complete_callback: Callable[[], None],
    ):
        super().__init__(parent)
        self.parent_app = parent
        self.on_complete = on_complete_callback
        self.login_process: subprocess.Popen | None = None

        self.title("Настройка Apple Music Downloader")
        self.geometry("520x590")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)

        # Делаем окно модальным поверх главного
        self.transient(parent)
        self.grab_set()

        self.build_ui(current_settings)
        self.protocol("WM_DELETE_WINDOW", self.on_close_dialog)

    def build_ui(self, settings: dict):
        container = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=18)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            container,
            text="Настройка аккаунта",
            font=("Segoe UI", 20, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w", padx=20, pady=(18, 4))

        ctk.CTkLabel(
            container,
            text=(
                "Укажите данные аккаунта и регион подписки Apple Music.\n"
                "Данные сохранятся в папку internal и больше не будут запрашиваться."
            ),
            font=("Segoe UI", 11),
            text_color=MUTED_TEXT,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 14))

        # Email (Apple ID)
        ctk.CTkLabel(
            container,
            text="Apple ID (Email):",
            font=("Segoe UI", 12, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w", padx=20, pady=(4, 4))

        self.email_var = ctk.StringVar(value=settings.get("email", ""))
        self.email_entry = ctk.CTkEntry(
            container,
            textvariable=self.email_var,
            placeholder_text="example@icloud.com",
            height=38,
            corner_radius=10,
            fg_color=CARD_2_COLOR,
            border_color="#2a2a3a",
        )
        self.email_entry.pack(fill="x", padx=20, pady=(0, 10))

        # Пароль
        ctk.CTkLabel(
            container,
            text="Пароль Apple ID:",
            font=("Segoe UI", 12, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w", padx=20, pady=(0, 4))

        self.pass_var = ctk.StringVar(value=settings.get("password", ""))
        self.pass_entry = ctk.CTkEntry(
            container,
            textvariable=self.pass_var,
            placeholder_text="••••••••••••",
            show="•",
            height=38,
            corner_radius=10,
            fg_color=CARD_2_COLOR,
            border_color="#2a2a3a",
        )
        self.pass_entry.pack(fill="x", padx=20, pady=(0, 10))

        # Выбор региона (Storefront)
        ctk.CTkLabel(
            container,
            text="Регион подписки (Storefront):",
            font=("Segoe UI", 12, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w", padx=20, pady=(0, 4))

        current_sf = settings.get("storefront", "kz")
        display_values = list(STOREFRONTS.values())
        default_display = STOREFRONTS.get(current_sf, STOREFRONTS["kz"])

        self.region_var = ctk.StringVar(value=default_display)
        self.region_menu = ctk.CTkOptionMenu(
            container,
            values=display_values,
            variable=self.region_var,
            height=38,
            corner_radius=10,
            fg_color=CARD_2_COLOR,
            button_color=ACCENT_COLOR,
            button_hover_color=ACCENT_HOVER,
        )
        self.region_menu.pack(fill="x", padx=20, pady=(0, 14))

        # Блок двухфакторной аутентификации (2FA)
        tfa_frame = ctk.CTkFrame(container, fg_color=CARD_2_COLOR, corner_radius=12)
        tfa_frame.pack(fill="x", padx=20, pady=(0, 12))

        ctk.CTkLabel(
            tfa_frame,
            text="Код 2FA (если запросит при входе):",
            font=("Segoe UI", 11, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w", padx=12, pady=(8, 4))

        tfa_row = ctk.CTkFrame(tfa_frame, fg_color="transparent")
        tfa_row.pack(fill="x", padx=12, pady=(0, 10))

        self.tfa_var = ctk.StringVar()
        self.tfa_entry = ctk.CTkEntry(
            tfa_row,
            textvariable=self.tfa_var,
            placeholder_text="6-значный код",
            height=34,
            corner_radius=8,
            fg_color=BG_COLOR,
            border_color="#2a2a3a",
        )
        self.tfa_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.tfa_entry.bind("<Return>", lambda e: self.send_2fa_code())

        self.tfa_btn = ctk.CTkButton(
            tfa_row,
            text="Отправить 2FA",
            width=120,
            height=34,
            corner_radius=8,
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            font=("Segoe UI", 11, "bold"),
            command=self.send_2fa_code,
        )
        self.tfa_btn.pack(side="left")

        # Текст состояния
        self.status_lbl = ctk.CTkLabel(
            container,
            text="Готово к сохранению",
            font=("Segoe UI", 11),
            text_color=MUTED_TEXT,
        )
        self.status_lbl.pack(anchor="w", padx=20, pady=(0, 8))

        # Кнопки действий
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4, 16))

        self.login_btn = ctk.CTkButton(
            btn_row,
            text="Войти в Apple ID",
            height=40,
            corner_radius=10,
            fg_color=CARD_2_COLOR,
            hover_color="#262636",
            border_width=1,
            border_color="#2a2a3a",
            font=("Segoe UI", 11, "bold"),
            command=self.run_interactive_login,
        )
        self.login_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.save_btn = ctk.CTkButton(
            btn_row,
            text="Сохранить и продолжить",
            height=40,
            corner_radius=10,
            fg_color=GREEN_COLOR,
            hover_color="#2fc184",
            text_color="#08130f",
            font=("Segoe UI", 12, "bold"),
            command=self.save_and_finish,
        )
        self.save_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

    def get_selected_storefront_code(self) -> str:
        selected_label = self.region_var.get()
        for code, label in STOREFRONTS.items():
            if label == selected_label:
                return code
        return "kz"

    def validate_inputs(self) -> tuple[str, str, str] | None:
        email = self.email_var.get().strip()
        password = self.pass_var.get()
        storefront = self.get_selected_storefront_code()

        if not email or "@" not in email:
            self.status_lbl.configure(text="Введите корректный Apple ID (Email)", text_color=RED_COLOR)
            return None
        if not password:
            self.status_lbl.configure(text="Введите пароль от Apple ID", text_color=RED_COLOR)
            return None
        return email, password, storefront

    def run_interactive_login(self):
        validated = self.validate_inputs()
        if not validated:
            return
        email, password, storefront = validated
        save_settings(email, password, storefront, logged_in=False)

        if not WRAPPER_EXE.exists():
            self.status_lbl.configure(
                text="wrapper-lite-qemu.exe не найден в папке internal!", text_color=RED_COLOR
            )
            return

        creds = f"{email}:{password}"
        self.status_lbl.configure(
            text="Идёт авторизация... Следите за логом или введите 2FA выше.",
            text_color=YELLOW_COLOR,
        )
        self.parent_app.log("Запущена авторизация Apple ID...")

        def _login_worker():
            try:
                self.login_process = subprocess.Popen(
                    [str(WRAPPER_EXE), "--login", creds],
                    cwd=str(WRAPPER_DIR),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                for line in self.login_process.stdout:
                    clean_line = line.rstrip()
                    self.parent_app.log(f"[Auth] {clean_line}")
                    if "2fa" in clean_line.lower() or "code" in clean_line.lower():
                        self.after(
                            0,
                            lambda: self.status_lbl.configure(
                                text="Требуется код 2FA! Введите его в поле выше и нажмите Отправить.",
                                text_color=YELLOW_COLOR,
                            ),
                        )

                self.login_process.wait()
                if self.login_process.returncode == 0:
                    self.after(
                        0,
                        lambda: self.status_lbl.configure(
                            text="Авторизация успешна! Нажмите «Сохранить и продолжить».",
                            text_color=GREEN_COLOR,
                        ),
                    )
                else:
                    self.after(
                        0,
                        lambda: self.status_lbl.configure(
                            text="Процесс входа завершён. Проверьте лог главного окна.",
                            text_color=MUTED_TEXT,
                        ),
                    )
            except OSError as err:
                self.after(
                    0,
                    lambda: self.status_lbl.configure(
                        text=f"Ошибка запуска: {err}", text_color=RED_COLOR
                    ),
                )

        threading.Thread(target=_login_worker, daemon=True).start()

    def send_2fa_code(self):
        code = self.tfa_var.get().strip()
        if not code:
            self.status_lbl.configure(text="Введите 6-значный код 2FA", text_color=RED_COLOR)
            return

        if self.login_process and self.login_process.poll() is None and self.login_process.stdin:
            try:
                self.login_process.stdin.write(code + "\n")
                self.login_process.stdin.flush()
                self.status_lbl.configure(
                    text="Код 2FA отправлен! Ожидайте подтверждения...",
                    text_color=GREEN_COLOR,
                )
                self.tfa_var.set("")
            except OSError as err:
                self.status_lbl.configure(
                    text=f"Ошибка отправки кода: {err}",
                    text_color=RED_COLOR,
                )
        else:
            self.status_lbl.configure(
                text="Процесс входа не активен. Сначала нажмите «Войти в Apple ID».",
                text_color=YELLOW_COLOR,
            )

    def save_and_finish(self):
        validated = self.validate_inputs()
        if not validated:
            return
        email, password, storefront = validated
        save_settings(email, password, storefront, logged_in=True)
        self.grab_release()
        self.destroy()
        self.on_complete()

    def on_close_dialog(self):
        if load_settings().get("setup_complete"):
            self.grab_release()
            self.destroy()
        else:
            self.parent_app.on_close()