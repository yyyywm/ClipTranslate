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
