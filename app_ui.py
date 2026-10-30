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

    WINDOW_WIDTH: int = 440
    WINDOW_HEIGHT: int = 820
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
            base_url=self._settings.get("base_url", ""),
            api_key=self._settings.get("api_key", ""),
            model=self._settings.get("model", ""),
            target_lang=self._settings.get("language", "en"),
            prompt=self._settings.get("prompt", ""),
        )
        translator = ClipboardTranslator(
            config=config, notifier=self._notifier.notify
        )
        translator.hotkey = self._settings.get("shortcut", "ctrl+i")
        return translator

    def _build_ui(self) -> None:
        """Construct all UI widgets."""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._app.title("ClipTranslate")
        self._app.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        # 所有控件固定宽度居中：标签与输入框同宽左对齐，整体居中，不随窗口拉伸
        self.INPUT_WIDTH = 380
        pad = {"pady": (4, 2)}

        icon_path = _base_dir() / self.ICON_PATH
        if icon_path.exists():
            try:
                self._app.iconbitmap(str(icon_path))
            except Exception:
                logger.exception("Failed to set window icon")

        # ---- 供应商名称（仅作记录，不影响功能，可留空）----
        ctk.CTkLabel(
            self._app,
            text="供应商名称:",
            width=self.INPUT_WIDTH,
            anchor="w",
            font=("华文行楷", 14),
        ).pack(pady=(12, 2))
        self._provider_entry = ctk.CTkEntry(
            self._app,
            placeholder_text="选填",
            width=self.INPUT_WIDTH,
            font=("华文行楷", 14),
        )
        self._provider_entry.insert(0, self._settings.get("provider", ""))
        self._provider_entry.pack(**pad)

        # ---- 接口地址 ----
        ctk.CTkLabel(
            self._app,
            text="接口地址 (Base URL):",
            width=self.INPUT_WIDTH,
            anchor="w",
            font=("华文行楷", 14),
        ).pack(pady=(8, 2))
        self._base_url_entry = ctk.CTkEntry(
            self._app,
            placeholder_text="https://api.example.com/v1",
            width=self.INPUT_WIDTH,
            font=("Helvetica", 13),
        )
        self._base_url_entry.insert(0, self._settings.get("base_url", ""))
        self._base_url_entry.pack(**pad)
        ctk.CTkLabel(
            self._app,
            text="OpenAI 兼容的 Chat Completions 协议（无需追加 /chat/completions）",
            width=self.INPUT_WIDTH,
            anchor="w",
            font=("Arial", 11),
            text_color="gray",
        ).pack()

        # ---- API Key ----
        # 标签与输入框同宽左对齐，整体居中
        ctk.CTkLabel(
            self._app,
            text="API Key:",
            width=self.INPUT_WIDTH,
            anchor="w",
            font=("华文行楷", 14),
        ).pack(pady=(8, 2))
        self._api_key_entry = ctk.CTkEntry(
            self._app,
            show="*",
            placeholder_text="sk-...",
            width=self.INPUT_WIDTH,
            font=("Helvetica", 13),
        )
        self._api_key_entry.insert(0, self._settings.get("api_key", ""))
        self._api_key_entry.pack(**pad)
        # 显隐按钮叠加在输入框右边缘，跟随输入框
        self._key_show_var = ctk.StringVar(value="显示")
        self._key_show_btn = ctk.CTkButton(
            self._api_key_entry,
            textvariable=self._key_show_var,
            width=44,
            height=20,
            command=self._toggle_api_key,
            font=("Helvetica", 10),
            fg_color="transparent",
            text_color="gray",
        )
        self._key_show_btn.place(relx=1.0, rely=0.5, x=-8, anchor="e")

        # ---- 模型 ----
        ctk.CTkLabel(
            self._app,
            text="模型:",
            width=self.INPUT_WIDTH,
            anchor="w",
            font=("华文行楷", 14),
        ).pack(pady=(8, 2))
        self._model_entry = ctk.CTkEntry(
            self._app,
            placeholder_text="deepseek-chat",
            width=self.INPUT_WIDTH,
            font=("Helvetica", 13),
        )
        self._model_entry.insert(0, self._settings.get("model", ""))
        self._model_entry.pack(**pad)

        # ---- 连接LLM（固定宽度，不随窗口拉伸）----
        ctk.CTkButton(
            self._app,
            text="连接LLM",
            command=self._on_test_llm,
            width=140,
            font=("华文行楷", 14),
        ).pack(pady=10)


        # ---- 目标语言（即选即生效，无需保存）----
        ctk.CTkLabel(
            self._app,
            text="目标语言:",
            width=self.INPUT_WIDTH,
            anchor="w",
            font=("华文行楷", 14),
        ).pack(pady=(8, 2))
        self._lang_combo = ctk.CTkComboBox(
            self._app,
            values=ConfigManager.SUPPORTED_LANGUAGES,
            command=self._on_lang_change,
            width=self.INPUT_WIDTH,
            font=("Helvetica", 14),
        )
        self._lang_combo.set(self._settings.get("language", "en"))
        self._lang_combo.pack(**pad)

        # ---- 快捷键 ----
        # 标签与快捷键值同行显示，整体固定宽度居中
        hot_row = ctk.CTkFrame(
            self._app, fg_color="transparent", width=self.INPUT_WIDTH
        )
        hot_row.pack(pady=(8, 2))
        ctk.CTkLabel(
            hot_row, text="当前快捷键:", anchor="w", font=("华文行楷", 14)
        ).pack(side="left", padx=(0, 8))
        self._hotkey_var = ctk.StringVar(
            value=self._settings.get("shortcut", "ctrl+i")
        )
        ctk.CTkLabel(
            hot_row, textvariable=self._hotkey_var, font=("Arial", 14)
        ).pack(side="left")
        # 设置按钮单独一行，放在快捷键显示下方
        ctk.CTkButton(
            self._app,
            text="设置快捷键",
            width=120,
            command=self._on_set_hotkey,
            font=("华文行楷", 13),
        ).pack(pady=(0, 4))

        # ---- 领域背景 / 提示词 ----
        ctk.CTkLabel(
            self._app,
            text="领域背景 / 提示词:",
            width=self.INPUT_WIDTH,
            anchor="w",
            font=("华文行楷", 14),
        ).pack(pady=(8, 2))
        ctk.CTkLabel(
            self._app,
            text="填写专业领域、术语约定或风格要求，提升术语翻译准确性",
            width=self.INPUT_WIDTH,
            anchor="w",
            font=("Arial", 11),
            text_color="gray",
        ).pack()
        self._prompt_text = ctk.CTkTextbox(
            self._app, width=self.INPUT_WIDTH, height=90, font=("Helvetica", 13)
        )
        self._prompt_text.insert("1.0", self._settings.get("prompt", ""))
        self._prompt_text.pack(**pad)
        # 保存 / 清空按钮（整体居中，固定宽度，不随窗口拉伸）
        btn_row = ctk.CTkFrame(self._app, fg_color="transparent")
        btn_row.pack(pady=(2, 4))
        ctk.CTkButton(
            btn_row,
            text="保存",
            command=self._save_prompt,
            width=80,
            font=("华文行楷", 13),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row,
            text="清空",
            command=self._clear_prompt,
            width=80,
            font=("华文行楷", 13),
        ).pack(side="left")

        # ---- 结果 / 状态提示区 ----
        self._result_label = ctk.CTkLabel(
            self._app, text="", font=("Arial", 12), wraplength=400
        )
        self._result_label.pack(pady=8)

    def _toggle_api_key(self) -> None:
        """Toggle API Key visibility between masked and plain."""
        if self._api_key_entry.cget("show") == "*":
            self._api_key_entry.configure(show="")
            self._key_show_var.set("隐藏")
        else:
            self._api_key_entry.configure(show="*")
            self._key_show_var.set("显示")

    def _build_config_from_ui(self) -> TranslateConfig:
        """Build TranslateConfig from UI, but use the persisted prompt.

        The prompt is managed via the 保存/清空 buttons; connecting LLM
        must not pick up unsaved prompt edits.
        """
        saved_prompt = self._config_manager.load().get("prompt", "")
        return TranslateConfig(
            base_url=self._base_url_entry.get(),
            api_key=self._api_key_entry.get(),
            model=self._model_entry.get(),
            target_lang=self._lang_combo.get(),
            prompt=saved_prompt,
        )

    def _on_lang_change(self, value: str) -> None:
        """Apply the selected target language immediately (no save needed).

        The language combo is live: selecting a value applies it to the
        translator and persists only that field, leaving any unsaved AI
        config drafts untouched.
        """
        self._translator.set_target_lang(value)
        self._config_manager.update_partial(language=value)

    def _on_set_hotkey(self) -> None:
        """Capture a new hotkey, save & apply it, then display the result.

        The capture prompt stays visible for the whole blocking read_hotkey
        call (we force a render first, since read_hotkey blocks the main
        loop). After capture the prompt is destroyed, the new combo is
        persisted, bound, shown in the '当前快捷键' label, and announced
        via a result popup.
        """
        import keyboard as kb

        # Unbind the old hotkey while capturing the new one so pressing the
        # intended shortcut doesn't fire the previous _execute callback.
        old_hotkey = self._translator.hotkey
        kb.remove_all_hotkeys()

        # 持续显示提示窗，捕获期间不自动关闭
        prompt = self._show_popup("请按下新快捷键...", duration=0)
        # read_hotkey 会阻塞主循环，先强制刷新让提示窗真正渲染出来
        try:
            self._app.update_idletasks()
            prompt.update_idletasks()
        except Exception:
            logger.debug("Forced popup render skipped", exc_info=True)

        new_hotkey = ""
        try:
            new_hotkey = kb.read_hotkey(suppress=True)
        except Exception:
            logger.exception("Failed to read hotkey")
        finally:
            try:
                prompt.destroy()
            except Exception:
                pass

        if not new_hotkey:
            self._translator.hotkey = old_hotkey
            self._show_popup("已取消", duration=1500)
            return
        if "+" not in new_hotkey:
            self._translator.hotkey = old_hotkey
            self._show_popup("无效的快捷键（需组合键）", duration=2000)
            return

        # 保存 + 应用 + 更新显示
        self._hotkey_var.set(new_hotkey)
        self._save_config()
        self._translator.change_hotkey(new_hotkey)
        self._show_popup(f"快捷键已设置为: {new_hotkey}", duration=2500)

    def _on_test_llm(self) -> None:
        """Test LLM connectivity with current UI values; persist on success.

        Applies the UI config to the translator, runs a minimal chat
        completion probe in a background thread, and reports success or
        failure with a reason. On success the config is also saved — this
        button replaces the old '保存AI设置', so validated config is kept.
        """
        new_config = self._build_config_from_ui()
        self._translator.update_config(new_config)

        self._result_label.configure(text="连接中…", text_color="gray")
        self._show_popup("连接中…", duration=3000)

        def worker() -> None:
            ok, detail = self._translator._engine.test_connection()

            def update() -> None:
                if ok:
                    self._save_config()
                    # 成功只弹一下提示：结果区短暂显示后清除，不长期保持
                    self._result_label.configure(
                        text="✓ 成功接入LLM", text_color="green"
                    )
                    self._app.after(
                        1500,
                        lambda: self._result_label.configure(text=""),
                    )
                    if self._notifier:
                        self._notifier.notify("成功接入LLM")
                else:
                    self._result_label.configure(
                        text=f"✗ 连接失败\n{detail}", text_color="red"
                    )
                    if self._notifier:
                        self._notifier.notify("LLM 连接失败")

            self._app.after(0, update)

        threading.Thread(target=worker, daemon=True).start()

    def _save_config(self) -> None:
        """Persist AI/hotkey UI values, leaving the prompt untouched.

        Uses update_partial so the领域背景 prompt is preserved on disk —
        connecting LLM or setting a hotkey must not overwrite it. The
        prompt is saved separately via _save_prompt().
        """
        self._config_manager.update_partial(
            provider=self._provider_entry.get(),
            base_url=self._base_url_entry.get(),
            api_key=self._api_key_entry.get(),
            model=self._model_entry.get(),
            language=self._lang_combo.get(),
            shortcut=self._hotkey_var.get(),
        )

    def _persist_prompt(self) -> None:
        """Write the current prompt to config and rebuild the engine."""
        prompt = self._prompt_text.get("1.0", "end-1c")
        self._config_manager.update_partial(prompt=prompt)
        self._settings = self._config_manager.load()
        self._translator.update_config(self._build_config_from_ui())

    def _save_prompt(self) -> None:
        """保存领域背景并应用到翻译引擎（独立于连接LLM/设快捷键）。"""
        self._persist_prompt()
        self._result_label.configure(
            text="✓ 领域背景已保存", text_color="green"
        )
        self._app.after(
            1500,
            lambda: self._result_label.configure(text=""),
        )

    def _clear_prompt(self) -> None:
        """清空领域背景输入框并保存空值。"""
        self._prompt_text.delete("1.0", "end")
        self._persist_prompt()
        self._show_popup("领域背景已清空", duration=1500)

    def _show_popup(self, message: str, duration: int = 2000) -> ctk.CTkToplevel:
        """Show a temporary borderless popup window.

        Args:
            message: Text to display.
            duration: Milliseconds before auto-close. 0 keeps it open until
                the caller destroys the returned popup (used for prompts
                that must persist across a blocking call).

        Returns:
            The popup widget, so callers can destroy it manually.
        """
        popup = ctk.CTkToplevel(self._app)
        popup.geometry("300x100")
        popup.overrideredirect(True)
        popup.attributes("-alpha", 0.9)
        popup.attributes("-topmost", True)
        ctk.CTkLabel(popup, text=message, font=("Arial", 16)).pack(
            expand=True, pady=10
        )
        if duration > 0:
            popup.after(duration, popup.destroy)
        return popup

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
