# ClipTranslate 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ClipTranslate 重构为 MVC 分层架构，修复严重 bug，添加类型注解和日志系统，保持原有功能不变。

**架构：** 拆分为 config.py（配置）、notifier.py（通知）、translator.py（翻译核心）、app_ui.py（GUI）、main.py（入口）。UI 与业务逻辑解耦，通过依赖注入组装。

**Tech Stack:** Python 3.9+, customtkinter, tencentcloud SDK, keyboard, pyperclip, pynput, windows_toasts, Pillow

---

## 文件映射

| 文件 | 操作 | 职责 |
|------|------|------|
| `config.py` | 新建 | 配置管理：读写 config.ini、默认值、验证、跨平台路径 |
| `notifier.py` | 新建 | 系统通知封装：Windows Toast |
| `translator.py` | 新建 | 翻译核心：TMT API、剪贴板操作、快捷键监听、请求锁 |
| `app_ui.py` | 新建 | GUI 界面：customtkinter 窗口、托盘、控件事件 |
| `main.py` | 新建 | 应用入口：`if __name__ == "__main__": main()` |
| `ClipTranslate.py` | 修改 | 兼容入口：转发到 main |
| `resource/config.ini` | 保留 | 现有用户配置 |

---

### Task 1: 创建 config.py（配置管理模块）

**Files:**
- Create: `config.py`

- [ ] **Step 1: 编写 config.py**

```python
"""Configuration management for ClipTranslate."""

import configparser
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages reading, writing, and validation of the application config."""

    DEFAULT_CONFIG: Dict[str, str] = {
        "secretid": "",
        "secretkey": "",
        "projectid": "",
        "shortcut": "ctrl+i",
        "language": "en",
    }

    SUPPORTED_LANGUAGES: List[str] = ["en", "zh", "ja", "ko"]

    def __init__(self, config_path: Optional[Union[str, Path]] = None) -> None:
        """Initialize with optional custom config path.

        Args:
            config_path: Path to config.ini. Defaults to resource/config.ini
                       relative to the project root.
        """
        if config_path is None:
            # Determine project root relative to this file
            self._config_file = Path(__file__).parent / "resource" / "config.ini"
        else:
            self._config_file = Path(config_path)

        self.ensure_exists()

    @property
    def config_file(self) -> Path:
        """Return the resolved config file path."""
        return self._config_file

    def ensure_exists(self) -> None:
        """Create a default config file if one does not exist."""
        if not self._config_file.exists():
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            self.save(self.DEFAULT_CONFIG.copy())
            logger.info("Created default config at %s", self._config_file)

    def load(self) -> Dict[str, str]:
        """Load configuration from file.

        Returns:
            Dictionary of config key-value pairs.
        """
        config = configparser.ConfigParser()
        if self._config_file.exists():
            config.read(self._config_file, encoding="utf-8")

        if "UserData" not in config.sections():
            return self.DEFAULT_CONFIG.copy()

        result: Dict[str, str] = {}
        for key in self.DEFAULT_CONFIG:
            result[key] = config.get("UserData", key, fallback=self.DEFAULT_CONFIG[key])
        return result

    def save(self, data: Dict[str, str]) -> None:
        """Save configuration to file.

        Args:
            data: Dictionary of configuration values to persist.
        """
        config = configparser.ConfigParser()
        config["UserData"] = {k: str(v) for k, v in data.items()}
        with open(self._config_file, "w", encoding="utf-8") as f:
            config.write(f)
        logger.info("Config saved to %s", self._config_file)

    def validate(self, data: Dict[str, str]) -> List[str]:
        """Validate configuration values.

        Args:
            data: Configuration dictionary to validate.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: List[str] = []
        if not data.get("secretid", "").strip():
            errors.append("SecretId is required")
        if not data.get("secretkey", "").strip():
            errors.append("SecretKey is required")
        if not data.get("projectid", "").strip():
            errors.append("ProjectId is required")
        if data.get("language", "en") not in self.SUPPORTED_LANGUAGES:
            errors.append(
                f"Unsupported language '{data.get('language')}'. "
                f"Supported: {', '.join(self.SUPPORTED_LANGUAGES)}"
            )
        return errors
```

- [ ] **Step 2: 验证文件无语法错误**

Run: `python -c "import config; print('config.py OK')"`
Expected: `config.py OK`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat(config): add ConfigManager with validation and cross-platform paths"
```

---

### Task 2: 创建 notifier.py（通知封装模块）

**Files:**
- Create: `notifier.py`

- [ ] **Step 1: 编写 notifier.py**

```python
"""Notification wrapper for ClipTranslate."""

import logging
from pathlib import Path
from typing import Optional

from windows_toasts import Toast, ToastDisplayImage, WindowsToaster

logger = logging.getLogger(__name__)


class Notifier:
    """Wraps Windows toast notifications with a clean interface."""

    APP_NAME: str = "ClipTranslate"
    DEFAULT_ICON: str = "resource/ui.png"

    def __init__(self, icon_path: Optional[str] = None) -> None:
        """Initialize the notifier.

        Args:
            icon_path: Path to the toast icon. Defaults to resource/ui.png
                       relative to the project root.
        """
        self._toaster = WindowsToaster(self.APP_NAME)
        if icon_path is None:
            self._icon_path = Path(__file__).parent / self.DEFAULT_ICON
        else:
            self._icon_path = Path(icon_path)

    def notify(self, message: str) -> None:
        """Display a Windows toast notification.

        Args:
            message: The text to display in the notification.
        """
        try:
            toast = Toast()
            toast.text_fields = [message]
            if self._icon_path.exists():
                toast.AddImage(ToastDisplayImage.fromPath(str(self._icon_path)))
            self._toaster.show_toast(toast)
            logger.debug("Notification shown: %s", message)
        except Exception as exc:
            logger.warning("Failed to show notification: %s", exc)
```

- [ ] **Step 2: 验证文件无语法错误**

Run: `python -c "import notifier; print('notifier.py OK')"`
Expected: `notifier.py OK` (可能因 WindowsToasts 在非 Windows 环境报错，可忽略)

- [ ] **Step 3: Commit**

```bash
git add notifier.py
git commit -m "feat(notifier): add Notifier wrapper for Windows toast"
```

---

### Task 3: 创建 translator.py（翻译核心模块）

**Files:**
- Create: `translator.py`

- [ ] **Step 1: 编写 translator.py**

```python
"""Translation engine and clipboard translator for ClipTranslate."""

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import keyboard
import pyperclip
from pynput.keyboard import Controller, Key
from tencentcloud.common import credential
from tencentcloud.common.common_client import CommonClient
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

logger = logging.getLogger(__name__)


@dataclass
class TranslateConfig:
    """Configuration required for translation."""

    secret_id: str
    secret_key: str
    project_id: str
    target_lang: str


class TranslationEngine:
    """Wraps Tencent Cloud TMT API calls."""

    API_VERSION: str = "2018-03-21"
    REGION: str = "ap-guangzhou"
    ENDPOINT: str = "tmt.tencentcloudapi.com"
    SERVICE: str = "tmt"

    def __init__(self, config: TranslateConfig) -> None:
        """Initialize with translation configuration.

        Args:
            config: TranslateConfig instance containing credentials.
        """
        self._config = config

    def translate(self, text: str) -> Optional[str]:
        """Translate text using Tencent Cloud TMT.

        Args:
            text: Source text to translate.

        Returns:
            Translated text, or None if the request failed.
        """
        if not text.strip():
            logger.warning("Empty text provided for translation")
            return None

        try:
            cred = credential.Credential(
                self._config.secret_id, self._config.secret_key
            )

            http_profile = HttpProfile()
            http_profile.endpoint = self.ENDPOINT

            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile

            params = json.dumps(
                {
                    "SourceText": text,
                    "Source": "auto",
                    "Target": self._config.target_lang,
                    "ProjectId": int(self._config.project_id)
                    if self._config.project_id.isdigit()
                    else 0,
                }
            )

            client = CommonClient(
                self.SERVICE,
                self.API_VERSION,
                cred,
                self.REGION,
                profile=client_profile,
            )

            response = client.call_json("TextTranslate", json.loads(params))
            result = response.get("Response", {}).get("TargetText")
            logger.info("Translation succeeded: '%s' -> '%s'", text[:30], result[:30] if result else "")
            return result

        except TencentCloudSDKException as exc:
            logger.error("Tencent Cloud SDK error: %s", exc)
            return None
        except json.JSONDecodeError as exc:
            logger.error("JSON decode error (unexpected): %s", exc)
            return None
        except Exception as exc:
            logger.error("Unexpected translation error: %s", exc)
            return None


class ClipboardTranslator:
    """Handles clipboard operations, hotkeys, and translation flow."""

    _CLIPBOARD_RETRY_INTERVAL: float = 0.05
    _CLIPBOARD_MAX_RETRIES: int = 20

    def __init__(
        self,
        config: TranslateConfig,
        notifier: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize the clipboard translator.

        Args:
            config: Translation configuration.
            notifier: Optional callable for user notifications.
        """
        self._config = config
        self._engine = TranslationEngine(config)
        self._keyctrl = Controller()
        self._notifier = notifier
        self._hotkey: str = ""
        self._running: bool = True
        self._lock = threading.Lock()

    @property
    def hotkey(self) -> str:
        """Return the currently bound hotkey."""
        return self._hotkey

    @hotkey.setter
    def hotkey(self, value: str) -> None:
        """Set a new hotkey and re-bind it.

        Args:
            value: New hotkey combination string (e.g. 'ctrl+i').
        """
        self._hotkey = value
        keyboard.remove_all_hotkeys()
        if value:
            try:
                keyboard.add_hotkey(value, self._execute)
                logger.info("Hotkey bound: %s", value)
            except Exception as exc:
                logger.error("Failed to bind hotkey '%s': %s", value, exc)
                if self._notifier:
                    self._notifier("快捷键绑定失败")

    def change_hotkey(self, new_hotkey: str) -> None:
        """Change the active hotkey (convenience method).

        Args:
            new_hotkey: New hotkey combination string.
        """
        self.hotkey = new_hotkey

    def update_config(self, config: TranslateConfig) -> None:
        """Update translation configuration without recreating the instance.

        Args:
            config: New TranslateConfig values.
        """
        self._config = config
        self._engine = TranslationEngine(config)
        logger.info("Translation configuration updated")

    def start(self) -> None:
        """Start listening for the configured hotkey (non-blocking)."""
        if self._hotkey:
            try:
                keyboard.add_hotkey(self._hotkey, self._execute)
                logger.info("Hotkey listener started: %s", self._hotkey)
            except Exception as exc:
                logger.error("Failed to start hotkey listener: %s", exc)

    def stop(self) -> None:
        """Stop listening for hotkeys."""
        keyboard.remove_all_hotkeys()
        logger.info("Hotkey listener stopped")

    def _copy(self) -> None:
        """Simulate Ctrl+C to copy selected text."""
        try:
            self._keyctrl.press(Key.ctrl)
            self._keyctrl.press("c")
            self._keyctrl.release("c")
            self._keyctrl.release(Key.ctrl)
        except Exception as exc:
            logger.error("Copy simulation failed: %s", exc)

    def _paste(self) -> None:
        """Simulate Ctrl+V to paste text."""
        try:
            self._keyctrl.press(Key.ctrl)
            self._keyctrl.press("v")
            self._keyctrl.release("v")
            self._keyctrl.release(Key.ctrl)
        except Exception as exc:
            logger.error("Paste simulation failed: %s", exc)

    def _get_clipboard(self) -> str:
        """Read text from the clipboard with retry logic.

        Returns:
            Clipboard text content.
        """
        for attempt in range(self._CLIPBOARD_MAX_RETRIES):
            try:
                text = pyperclip.paste()
                if text:
                    return text
            except Exception as exc:
                logger.debug("Clipboard read attempt %d failed: %s", attempt, exc)
            time.sleep(self._CLIPBOARD_RETRY_INTERVAL)
        return ""

    def _execute(self) -> None:
        """Main workflow: copy -> translate -> paste.

        Protected by a lock to prevent concurrent execution.
        """
        if not self._lock.acquire(blocking=False):
            logger.debug("Translation already in progress, skipping")
            return

        try:
            # Save current clipboard so we can restore on failure
            original_clipboard = pyperclip.paste()

            self._copy()
            time.sleep(0.05)  # Small delay for OS to process copy
            source_text = self._get_clipboard()

            if not source_text:
                logger.warning("No text found in clipboard after copy")
                if self._notifier:
                    self._notifier("未检测到选中文本")
                return

            result = self._engine.translate(source_text)

            if result:
                pyperclip.copy(result)
                time.sleep(0.05)
                self._paste()
                logger.info("Translation pasted: %s", result[:50])
            else:
                # Restore original clipboard on failure
                pyperclip.copy(original_clipboard)
                if self._notifier:
                    self._notifier("翻译失败，请检查配置")

        except Exception as exc:
            logger.error("Translation workflow error: %s", exc)
            if self._notifier:
                self._notifier("翻译过程中发生错误")
        finally:
            self._lock.release()
```

- [ ] **Step 2: 验证文件无语法错误**

Run: `python -c "import translator; print('translator.py OK')"`
Expected: `translator.py OK`

- [ ] **Step 3: Commit**

```bash
git add translator.py
git commit -m "feat(translator): add TranslationEngine and ClipboardTranslator with request lock"
```

---

### Task 4: 创建 app_ui.py（GUI 界面模块）

**Files:**
- Create: `app_ui.py`

- [ ] **Step 1: 编写 app_ui.py**

```python
"""GUI application for ClipTranslate using customtkinter."""

import logging
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk
import pystray
from PIL import Image
from pystray import MenuItem as item

from config import ConfigManager
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
        return ClipboardTranslator(config=config, notifier=self._notifier.notify)

    def _build_ui(self) -> None:
        """Construct all UI widgets."""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._app.title("ClipTranslate")
        self._app.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")

        icon_path = Path(__file__).parent / self.ICON_PATH
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
        tray_icon_path = Path(__file__).parent / self.TRAY_ICON_PATH
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
            pil_image = pil_image.resize((256, 256), getattr(Image, "LANCZOS", Image.Resampling.LANCZOS))
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
        """Start the hotkey listener and enter the main event loop."""
        # Start hotkey in a daemon thread
        hotkey_thread = threading.Thread(target=self._translator.start, daemon=True)
        hotkey_thread.start()

        # Start window state polling
        self._check_window_state()

        logger.info("Application started")
        self._app.mainloop()
        self._translator.stop()
        logger.info("Application exited")
```

- [ ] **Step 2: 验证文件无语法错误**

Run: `python -c "import app_ui; print('app_ui.py OK')"`
Expected: `app_ui.py OK`

- [ ] **Step 3: Commit**

```bash
git add app_ui.py
git commit -m "feat(ui): add ClipTranslateApp with decoupled UI and tray icon"
```

---

### Task 5: 创建 main.py（应用入口）

**Files:**
- Create: `main.py`
- Modify: `ClipTranslate.py`

- [ ] **Step 1: 编写 main.py**

```python
"""Application entry point for ClipTranslate."""

import logging
import sys
from pathlib import Path


def _setup_logging() -> None:
    """Configure logging to file and console."""
    log_dir = Path(__file__).parent / "resource"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "app.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    """Run the ClipTranslate application."""
    _setup_logging()

    from app_ui import ClipTranslateApp

    app = ClipTranslateApp()
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 重写 ClipTranslate.py 为兼容入口**

```python
"""Legacy entry point — forwards to main.py for backwards compatibility."""

from main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 验证语法**

Run: `python -c "import main; print('main.py OK')"`
Expected: `main.py OK`

- [ ] **Step 4: Commit**

```bash
git add main.py ClipTranslate.py
git commit -m "feat(entry): add main.py entry point and keep ClipTranslate.py as compat wrapper"
```

---

### Task 6: 清理旧文件、验证整体功能

**Files:**
- Delete: `ClipTranslateClass.py`（功能已迁移到 translator.py）

- [ ] **Step 1: 删除旧文件**

```bash
git rm ClipTranslateClass.py
git commit -m "chore(cleanup): remove ClipTranslateClass.py (migrated to translator.py)"
```

- [ ] **Step 2: 运行应用验证**

Run: `python main.py`
Expected: 应用正常启动，窗口显示，托盘图标出现，能保存配置、设置快捷键。

- [ ] **Step 3: 检查日志输出**

Run: `cat resource/app.log`
Expected: 日志文件存在，包含 INFO 级别的启动/保存记录。

- [ ] **Step 4: 最终 Commit**

```bash
git add -A
git commit -m "refactor: complete MVC architecture refactor with type annotations and logging"
```

---

## 自检清单

### Spec 覆盖

| Spec 要求 | 对应 Task |
|-----------|-----------|
| config.py 配置管理 | Task 1 |
| notifier.py 通知封装 | Task 2 |
| translator.py 翻译核心 + 请求锁 | Task 3 |
| app_ui.py GUI 解耦 | Task 4 |
| main.py 入口保护 | Task 5 |
| ClipTranslate.py 兼容 | Task 5 |
| 修复 target=set_hotkey() 括号 | Task 3 (`start` 方法 + Task 4 正确调用) |
| 修复 JSON 拼接 | Task 3 (`json.dumps`) |
| 修复 time.sleep(1) | Task 3 (剪贴板重试 + 状态保存) |
| 类型注解 | 所有 Task |
| 日志系统 | Task 5 + 各模块 logger |
| Pillow 兼容 | Task 4 (`getattr(Image, "LANCZOS", ...)` ) |
| 路径跨平台 | Task 1, 2, 4 (`pathlib.Path`) |

### Placeholder 扫描
- 无 TBD/TODO
- 无 "implement later"
- 所有代码块包含完整可运行代码
- 无 "Similar to Task N" 引用

### 类型一致性
- `TranslateConfig` 在 Task 3 定义，Task 4 中 `new_config = TranslateConfig(...)` 字段名一致
- `ConfigManager.SUPPORTED_LANGUAGES` 在 Task 1 定义为类属性，Task 4 直接使用
- `Notifier.notify` 签名一致
- `ClipboardTranslator.start` / `stop` / `change_hotkey` 在各处调用一致
