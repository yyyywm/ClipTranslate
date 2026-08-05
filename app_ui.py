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

        shortcut = self._settings.get("shortcut", "ctrl+i")
        translator.hotkey = shortcut
        # If the loaded value was rejected as corrupted, fall back to default
        # and tell the user to re-set the shortcut.
        if not translator.hotkey:
            translator.hotkey = "ctrl+i"
            self._hotkey_var.set("ctrl+i")
            self._show_popup(
                "快捷键配置损坏，已恢复默认(ctrl+i)，请重新设置",
                duration=3000,
            )
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
            except Exception:
                logger.exception("Failed to set window icon")

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
        """Capture a new hotkey from keyboard input.

        ``keyboard.read_hotkey()`` builds its return value from the global
        ``keyboard._pressed_events`` dict.  That dict is shared across the
        whole process and gets polluted by *any* key events that the
        ``keyboard`` WH_KEYBOARD_LL hook receives -- including the synthetic
        Ctrl+C / Ctrl+V injected by ``pynput.Controller`` inside
        ``_execute``.  Once a ghost key (e.g. ``1`` or ``f22``) lands in
        ``_pressed_events`` it never gets cleaned up, so every subsequent
        ``read_hotkey()`` call returns ``ctrl+1+i`` etc.

        To break the cycle we: (1) clear ``_pressed_events`` so only the
        user's actual keypress is captured, (2) call ``unhook_all()`` so
        no new synthetic events can poison the dict while we wait, and
        (3) remove the hotkey callback so ``_execute`` cannot re-enter.
        """
        import keyboard as kb

        old_hotkey = self._translator.hotkey

        # (1) Tear down the active hotkey binding so _execute cannot run
        #     while we are capturing.
        kb.remove_all_hotkeys()

        # (2) Remove the WH_KEYBOARD_LL listener entirely.  While the hook
        #     is gone, pynput's synthetic Ctrl+C / Ctrl+V events cannot be
        #     added to _pressed_events.
        kb.unhook_all()

        # (3) Clear any ghost keys left over from previous _execute runs.
        #     read_hotkey() reads from _pressed_events to build the
        #     returned string; residual entries (e.g. "1", "c", "f22")
        #     would otherwise appear in the captured hotkey.
        if hasattr(kb, "_pressed_events"):
            kb._pressed_events.clear()

        self._show_popup("请按下新快捷键...", duration=1500)
        try:
            new_hotkey = kb.read_hotkey(suppress=True)
            if not new_hotkey:
                self._show_popup("已取消", duration=1500)
                self._translator.hotkey = old_hotkey
                return
            if "+" not in new_hotkey:
                self._show_popup("无效的快捷键（需组合键）", duration=2000)
                self._translator.hotkey = old_hotkey
                return
            self._hotkey_var.set(new_hotkey)
            self._save_config()
            self._translator.change_hotkey(new_hotkey)
            self._show_popup(f"快捷键已设置为: {new_hotkey}", duration=2000)
        except Exception:
            logger.exception("Failed to read hotkey")
            self._translator.hotkey = old_hotkey
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
        except Exception:
            logger.exception("Failed to create tray icon")

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
