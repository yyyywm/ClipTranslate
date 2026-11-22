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

        except TencentCloudSDKException:
            logger.exception("Tencent Cloud SDK error")
            return None
        except json.JSONDecodeError:
            logger.exception("JSON decode error (unexpected)")
            return None
        except Exception:
            logger.exception("Unexpected translation error")
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
        logger.debug(
            "ClipboardTranslator init - keyboard state: "
            "_pressed_events=%s, _logically_pressed_keys=%s",
            list(keyboard._pressed_events.keys()),
            list(keyboard._logically_pressed_keys),
        )

    @staticmethod
    def _is_hotkey_corrupted(value: str) -> bool:
        """Detect a hotkey value that was polluted during capture.

        A polluted value typically has non-modifier keys wedged between
        the modifiers and the trigger key (e.g. ``ctrl+1+i`` where ``1``
        is neither a modifier nor the intended hotkey), or contains
        obviously synthetic function-key tokens like ``f22``.

        Args:
            value: The hotkey string to validate.

        Returns:
            True if the value looks corrupted and should be rejected.
        """
        KNOWN_MODIFIERS = {
            "ctrl", "alt", "shift", "win",
            "ctrl_l", "ctrl_r", "alt_l", "alt_r",
            "shift_l", "shift_r",
            "num_lock", "caps_lock", "scroll_lock",
        }

        if not value:
            return True

        parts = value.lower().split("+")

        # Hotkeys are at most 3 keys: modifier + [modifier] + key.
        # A 4+ part string is almost certainly polluted.
        if len(parts) > 3:
            return True

        for p in parts:
            if not p:
                continue
            if p in KNOWN_MODIFIERS:
                continue
            # Allowed non-modifier: a printable key (letter, digit, f-key).
            if p.isalnum() and len(p) <= 4:
                # Function keys beyond f24 never come from a real key press.
                if p.startswith("f") and len(p) > 2 and p[1:].isdigit():
                    if int(p[1:]) > 24:
                        return True
                continue
            # If the part has special characters (e.g. "space", "enter")
            # it's fine; anything else is suspicious.
            if p in {
                "space", "enter", "esc", "backspace", "tab",
                "delete", "insert", "home", "end", "pgup", "pgdn",
                "up", "down", "left", "right", "print",
                "pause", "menu", "lctrl", "rctrl", "lalt", "ralt",
                "lshift", "rshift", "lwin", "rwin",
            }:
                continue
            # Anything else is suspicious (e.g. an unknown synthetic token).
            return True

        # Additional sanity check: if there are 3 parts, at most one should be
        # a non-modifier "key".  e.g. "ctrl+1+i" -- two non-modifier tokens,
        # polluted.
        if len(parts) == 3:
            non_mod = [p for p in parts if p not in KNOWN_MODIFIERS]
            if len(non_mod) > 1:
                return True

        # A valid hotkey must contain at least one actual key (not just
        # modifiers).  "ctrl+shift" / "ctrl+alt+shift" have no trigger and
        # are therefore invalid.
        non_mod = [p for p in parts if p not in KNOWN_MODIFIERS]
        if not non_mod:
            return True

        return False

    @property
    def hotkey(self) -> str:
        """Return the currently bound hotkey."""
        return self._hotkey

    @hotkey.setter
    def hotkey(self, value: str) -> None:
        """Set a new hotkey and re-bind it.

        Corrupted values (polluted during capture) are rejected and the
        old binding is kept so the user never gets a broken hotkey.

        Args:
            value: New hotkey combination string (e.g. 'ctrl+i').
        """
        if value and self._is_hotkey_corrupted(value):
            logger.warning("Rejected corrupted hotkey value: %s", value)
            return
        self._hotkey = value
        try:
            keyboard.remove_all_hotkeys()
        except AttributeError:
            # Listener may not be initialized yet (e.g. first hotkey set).
            pass
        if value:
            try:
                keyboard.add_hotkey(value, self._execute)
                logger.info("Hotkey bound: %s", value)
            except Exception as exc:
                logger.error("Failed to bind hotkey '%s': %s", value, exc)
                self._hotkey = ""
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
        try:
            keyboard.remove_all_hotkeys()
        except AttributeError:
            pass
        logger.info("Hotkey listener stopped")

    def _copy(self) -> None:
        """Simulate Ctrl+C to copy selected text."""
        try:
            self._keyctrl.press(Key.ctrl)
            self._keyctrl.press("c")
            self._keyctrl.release("c")
            self._keyctrl.release(Key.ctrl)
        except Exception:
            logger.exception("Copy simulation failed")

    def _paste(self) -> None:
        """Simulate Ctrl+V to paste text."""
        try:
            self._keyctrl.press(Key.ctrl)
            self._keyctrl.press("v")
            self._keyctrl.release("v")
            self._keyctrl.release(Key.ctrl)
        except Exception:
            logger.exception("Paste simulation failed")

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
            except Exception:
                logger.debug("Clipboard read attempt %d failed", attempt, exc_info=True)
            time.sleep(self._CLIPBOARD_RETRY_INTERVAL)
        return ""

    def _execute(self) -> None:
        """Main workflow: copy -> translate -> paste.

        The hotkey is temporarily disabled for the duration of this method
        so that the simulated Ctrl+C / Ctrl+V generated by pynput.Controller
        are not seen by the ``keyboard`` global hook and re-fire _execute
        (a loop that triggers translation even when no real key was pressed).
        """
        if not self._lock.acquire(blocking=False):
            logger.debug("Translation already in progress, skipping")
            return

        logger.debug(
            "Pre-_execute keyboard state: _pressed_events=%s, "
            "_logically_pressed_keys=%s",
            list(keyboard._pressed_events.keys()),
            list(keyboard._logically_pressed_keys),
        )

        # Save and clear the hotkey binding so simulated key events during
        # copy/paste cannot re-enter this callback.
        saved_hotkey = self._hotkey
        self._hotkey = ""
        try:
            keyboard.remove_all_hotkeys()
            # Also remove all hook handlers so pynput's synthetic Ctrl+C/Ctrl+V
            # cannot pollute keyboard._pressed_events while we simulate keys.
            keyboard.unhook_all()
            logger.debug(
                "After remove+unhook: _pressed_events=%s, "
                "_logically_pressed_keys=%s",
                list(keyboard._pressed_events.keys()),
                list(keyboard._logically_pressed_keys),
            )
        except AttributeError:
            pass

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

        except Exception:
            logger.exception("Translation workflow error")
            if self._notifier:
                self._notifier("翻译过程中发生错误")
        finally:
            self._lock.release()
            # Clean up the keyboard library's internal state BEFORE
            # re-binding the hotkey.  keyboard.add_hotkey() immediately
            # inspects _logically_pressed_keys / _pressed_events at bind
            # time; if the ctrl+i that originally triggered _execute is
            # still "logically pressed", add_hotkey will fire _execute
            # again on the spot — producing the infinite re-entry loop.
            # Order MUST be: clear state  →  add_hotkey.
            if hasattr(keyboard, "_pressed_events"):
                keyboard._pressed_events.clear()
            if hasattr(keyboard, "_logically_pressed_keys"):
                keyboard._logically_pressed_keys.clear()
            logger.debug(
                "Post-_execute keyboard state: _pressed_events=%s, "
                "_logically_pressed_keys=%s",
                list(keyboard._pressed_events.keys()),
                list(keyboard._logically_pressed_keys),
            )

            # Re-bind the hotkey AFTER a short delay so that the user's
            # physical key-release events have time to clear from the
            # keyboard library's state.  If add_hotkey() is called while
            # the triggering key combo is still logically pressed, it
            # will immediately re-fire _execute — creating an infinite
            # loop.  Delaying ~150 ms lets the OS process the key-up
            # events first.
            self._hotkey = saved_hotkey
            if saved_hotkey:
                def _rebind():
                    try:
                        keyboard.add_hotkey(saved_hotkey, self._execute)
                        logger.debug("Hotkey re-bound: %s", saved_hotkey)
                    except Exception as exc:
                        logger.error(
                            "Failed to re-bind hotkey '%s': %s", saved_hotkey, exc
                        )

                threading.Timer(0.15, _rebind).start()
