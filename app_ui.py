"""GUI application for ClipTranslate using customtkinter."""

import logging
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk
import pystray
from PIL import Image
from pystray import MenuItem as item

from config import ConfigManager, _base_dir
from notifier import Notifier
from translator import ClipboardTranslator, TranslateConfig

logger = logging.getLogger(__name__)


class ClipTranslateApp:
    """Main application window and UI controller."""

    WINDOW_WIDTH: int = 400
    WINDOW_HEIGHT: int = 550
    ICON_PATH: str = "resource/logo.ico"
    TRAY_ICON_PATH: str = "resource/ui.png"

    def __init__(self) -> None:
        """Initialize the application, load config, and build UI."""
        self._config_manager = ConfigManager()
        self._settings = self._config_manager.load()

        self._notifier = Notifier()
        self._translator = self._create_translator()

        self._app = ctk.CTk()
        self._build_ui()
        self._create_tray_icon()

    def _create_translator(self) -> ClipboardTranslator:
        """Create a ClipboardTranslator from current settings."""
        config = TranslateConfig(
            secret_id=self._settings.get("secretid", ""),
            secret_key=self._settings.get("secretkey", ""),
            project_id=self._settings.get("projectid", ""),
            target_lang=self._settings.get("language", "en"),
        )
        translator = ClipboardTranslator(config=config, notifier=self._notifier.notify)
        translator.hotkey = self._settings.get("shortcut", "ctrl+i")
        return translator

    def _build_ui(self) -> None:
        """Construct all UI widgets."""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._app.title("ClipTranslate")
        self._app.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")

        icon_path = _base_dir() / self.ICON_PATH
        if icon_path.exists():
            try:
                self._app.iconbitmap(str(icon_path))
            except Exception as exc:
                logger.warning("Failed to set window icon: %s", exc)

        # SecretId
        ctk.CTkLabel(self._app, text="SecretId:", font=("华文行楷", 16)).pack(pady=5)
        self._secretid_entry = ctk.CTkEntry(
            self._app, placeholder_text="输入SecretId", font=("Verdana", 14)
        )
        self._secretid_entry.pack(pady=5)
        self._secretid_entry.insert(0, self._settings.get("secretid", ""))

        # SecretKey
        ctk.CTkLabel(self._app, text="SecretKey:", font=("华文行楷", 16)).pack(pady=5)
        self._secretkey_entry = ctk.CTkEntry(
            self._app, placeholder_text="输入SecretKey", font=("Helvetica", 14)
        )
        self._secretkey_entry.pack(pady=5)
        self._secretkey_entry.insert(0, self._settings.get("secretkey", ""))

        # ProjectId
        ctk.CTkLabel(self._app, text="ProjectId:", font=("华文行楷", 16)).pack(pady=5)
        self._projectid_entry = ctk.CTkEntry(
            self._app, placeholder_text="输入ProjectId", font=("Helvetica", 14)
        )
        self._projectid_entry.pack(pady=5)
        self._projectid_entry.insert(0, self._settings.get("projectid", ""))

        # Language selection
        lang_options = ConfigManager.SUPPORTED_LANGUAGES
        self._lang_combo = ctk.CTkComboBox(
            self._app, values=lang_options, font=("Helvetica", 14)
        )
        self._lang_combo.pack(pady=10)
        self._lang_combo.set(self._settings.get("language", "en"))

        # Hotkey display
        ctk.CTkLabel(self._app, text="当前快捷键:", font=("华文行楷", 16)).pack(pady=5)
        self._hotkey_var = ctk.StringVar(
            value=self._settings.get("shortcut", "ctrl+i")
        )
        ctk.CTkLabel(self._app, textvariable=self._hotkey_var, font=("Arial", 14)).pack(
            pady=5
        )

        # Set hotkey button
        ctk.CTkButton(
            self._app,
            text="设置快捷键",
            command=self._on_set_hotkey,
            font=("华文行楷", 16),
        ).pack(pady=10)

        # Save button
        ctk.CTkButton(
            self._app,
            text="保存设置",
            command=self._on_save,
            font=("华文行楷", 16),
        ).pack(pady=10)

        # Result label
        self._result_label = ctk.CTkLabel(self._app, text="", font=("Arial", 14))
        self._result_label.pack(pady=10)

    def _on_set_hotkey(self) -> None:
        """Capture a new hotkey from keyboard input."""
        import keyboard as kb

        self._show_popup("请按下新快捷键...", duration=1500)
        try:
            new_hotkey = kb.read_hotkey(suppress=False)
            self._hotkey_var.set(new_hotkey)
            self._translator.change_hotkey(new_hotkey)
            self._save_config()
            self._show_popup(f"快捷键已设置为: {new_hotkey}", duration=2000)
        except Exception as exc:
            logger.error("Failed to read hotkey: %s", exc)
            self._show_popup("快捷键设置失败", duration=2000)

    def _on_save(self) -> None:
        """Save current settings and update translator."""
        self._save_config()

        # Update translator config without recreating instance
        new_config = TranslateConfig(
            secret_id=self._secretid_entry.get(),
            secret_key=self._secretkey_entry.get(),
            project_id=self._projectid_entry.get(),
            target_lang=self._lang_combo.get(),
        )
        self._translator.update_config(new_config)
        self._translator.change_hotkey(self._hotkey_var.get())

        secret_id = self._secretid_entry.get()
        secret_key = self._secretkey_entry.get()
        project_id = self._projectid_entry.get()
        self._result_label.configure(
            text=f"SecretId: {secret_id}\nSecretKey: {secret_key}\nProjectId: {project_id}"
        )
        self._show_popup("设置已保存", duration=1500)

    def _save_config(self) -> None:
        """Persist current UI values to config file."""
        data = {
            "secretid": self._secretid_entry.get(),
            "secretkey": self._secretkey_entry.get(),
            "projectid": self._projectid_entry.get(),
            "shortcut": self._hotkey_var.get(),
            "language": self._lang_combo.get(),
        }
        self._config_manager.save(data)

    def _show_popup(self, message: str, duration: int = 2000) -> None:
        """Show a temporary borderless popup window.

        Args:
            message: Text to display.
            duration: Milliseconds before auto-close.
        """
        popup = ctk.CTkToplevel(self._app)
        popup.geometry("300x100")
        popup.overrideredirect(True)
        popup.attributes("-alpha", 0.9)
        popup.attributes("-topmost", True)
        ctk.CTkLabel(popup, text=message, font=("Arial", 16)).pack(expand=True, pady=10)
        popup.after(duration, popup.destroy)

    def _create_tray_icon(self) -> None:
        """Create and run the system tray icon in a daemon thread."""
        tray_icon_path = _base_dir() / self.TRAY_ICON_PATH
        if not tray_icon_path.exists():
            logger.warning("Tray icon not found: %s", tray_icon_path)
            return

        def restore_window(icon: pystray.Icon) -> None:
            self._app.after(0, self._app.deiconify)

        def quit_app(icon: pystray.Icon) -> None:
            icon.stop()
            self._app.quit()

        try:
            pil_image = Image.open(tray_icon_path)
            # Pillow 10+ compatibility
            # Pillow 9.x: Image.LANCZOS  |  Pillow 10.x: Image.Resampling.LANCZOS
            _resample = getattr(Image, "LANCZOS", None)
            if _resample is None:
                _resample = Image.Resampling.LANCZOS
            pil_image = pil_image.resize((256, 256), _resample)
            menu = (item("显示", restore_window), item("退出", quit_app))
            self._tray_icon = pystray.Icon(
                "ClipTranslate", pil_image, "ClipTranslate", menu
            )
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
            logger.info("Tray icon started")
        except Exception as exc:
            logger.error("Failed to create tray icon: %s", exc)

    def _check_window_state(self) -> None:
        """Poll window state and hide to tray when minimized."""
        if self._app.state() == "iconic":
            self._app.withdraw()
        self._app.after(100, self._check_window_state)

    def run(self) -> None:
        """Enter the main event loop."""
        # Hotkey is already bound by _create_translator() via the hotkey setter.
        self._check_window_state()

        logger.info("Application started")
        self._app.mainloop()
        self._translator.stop()
        logger.info("Application exited")
