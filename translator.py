"""Translation engine and clipboard translator for ClipTranslate.

The translation backend is an LLM speaking the OpenAI-compatible chat
completions API (``/v1/chat/completions``). One client covers DeepSeek,
智谱 GLM, 通义千问, Kimi, OpenAI and local Ollama — the user only needs
to swap ``base_url`` / ``api_key`` / ``model``.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

import keyboard
import pyperclip
from pynput.keyboard import Controller, Key

logger = logging.getLogger(__name__)


# 目标语言代码 -> 提示词里使用的全称（LLM 对全称理解更稳定）
_LANG_NAMES = {
    "en": "English",
    "zh": "中文（简体）",
    "ja": "日本語",
    "ko": "한국어",
}


@dataclass
class TranslateConfig:
    """Configuration required for LLM-based translation.

    Attributes:
        base_url: OpenAI-compatible API base, e.g. ``https://api.deepseek.com/v1``.
        api_key: Bearer token for the API.
        model: Model name to call, e.g. ``deepseek-chat``.
        target_lang: Target language code (see ConfigManager.SUPPORTED_LANGUAGES).
        prompt: User-supplied background / domain prompt injected into the
            system message to steer terminology and style.
    """

    base_url: str
    api_key: str
    model: str
    target_lang: str
    prompt: str = ""


class TranslationEngine:
    """LLM translation engine speaking the OpenAI-compatible chat API."""

    REQUEST_TIMEOUT: float = 60.0
    TEMPERATURE: float = 0.3

    def __init__(self, config: TranslateConfig) -> None:
        """Initialize with translation configuration.

        Args:
            config: TranslateConfig instance containing LLM credentials.
        """
        self._config = config

    def _system_prompt(self) -> str:
        """Build the system message: role + target lang + user background."""
        target = _LANG_NAMES.get(self._config.target_lang, self._config.target_lang)
        background = self._config.prompt.strip()
        background_section = (
            "翻译背景与领域要求（请严格遵循其中的术语约定与风格）：\n"
            f"{background}\n"
            if background
            else ""
        )
        return (
            f"你是一名专业翻译引擎。将用户提供的文本翻译成{target}。\n"
            f"{background_section}"
            "严格规则：\n"
            "- 只输出译文本身，不要任何解释、注释、前后缀、引号或标记。\n"
            "- 保留原文的换行、格式与标点风格。\n"
            "- 准确使用专业领域术语；必要时首次出现可在括号内附原文。\n"
            "- 若文本已是目标语言，原样返回。"
        )

    @staticmethod
    def _clean(text: str) -> str:
        """Strip common LLM-added wrappers (译文：, surrounding quotes, etc.)."""
        if not text:
            return text
        for prefix in (
            "译文：", "译文:", "翻译：", "翻译:",
            "Translation:", "Translated text:", "Result:",
        ):
            if text.startswith(prefix):
                text = text[len(prefix):].lstrip()
                break
        if len(text) >= 2 and text[0] in "“\"'`" and text[-1] in "”\"'`":
            text = text[1:-1]
        return text.strip()

    def translate(self, text: str) -> Optional[str]:
        """Translate text via the LLM chat completions API.

        Args:
            text: Source text to translate.

        Returns:
            Translated text, or None if the request failed.
        """
        if not text.strip():
            logger.warning("Empty text provided for translation")
            return None

        url = self._config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self._config.model,
            "temperature": self.TEMPERATURE,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": text},
            ],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
        }

        try:
            req = urllib.request.Request(
                url, data=body, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            content = data["choices"][0]["message"]["content"]
            result = self._clean(content)
            logger.info(
                "Translation succeeded: '%s' -> '%s'",
                text[:30],
                result[:30] if result else "",
            )
            return result

        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8", "replace")
            except Exception:
                err_body = ""
            logger.error(
                "LLM API HTTP %s %s: %s", exc.code, exc.reason, err_body[:300]
            )
            return None
        except urllib.error.URLError as exc:
            logger.exception("LLM API network error: %s", exc.reason)
            return None
        except (KeyError, IndexError, json.JSONDecodeError):
            logger.exception("LLM API unexpected response shape")
            return None
        except Exception:
            logger.exception("Unexpected translation error")
            return None

    def test_connection(self) -> "tuple[bool, str]":
        """Minimal connectivity probe against the LLM chat API.

        Sends a 1-token chat completion to verify that the endpoint,
        credentials and model all work together. Returns ``(ok, detail)``
        where ``detail`` is a short human-readable reason on failure or a
        confirmation on success.
        """
        if not self._config.base_url.strip():
            return False, "接口地址 (Base URL) 为空"
        if not self._config.api_key.strip():
            return False, "API Key 为空"
        if not self._config.model.strip():
            return False, "模型名 (Model) 为空"

        url = self._config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self._config.model,
            "temperature": 0,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
        }

        try:
            req = urllib.request.Request(
                url, data=body, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "choices" in data:
                return True, "连接成功，API Key 与模型均可用"
            err = data.get("error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            return False, f"API 返回异常: {msg}"

        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8", "replace")
            except Exception:
                err_body = ""
            return False, self._explain_http_error(exc.code, err_body)
        except urllib.error.URLError as exc:
            return False, f"网络错误: {exc.reason}（检查接口地址是否正确、网络是否通畅）"
        except json.JSONDecodeError:
            return False, "响应不是合法 JSON（接口地址可能错误）"
        except Exception as exc:
            return False, f"未知错误: {exc}"

    @staticmethod
    def _explain_http_error(code: int, body: str) -> str:
        """Translate common HTTP error codes into actionable hints.

        Includes a short snippet of the response body so the user can see
        the server's own message (e.g. which model is forbidden).
        """
        snippet = body[:200].replace("\n", " ")
        if code == 401:
            return f"HTTP 401：API Key 无效或已过期（{snippet}）"
        if code == 403:
            return (
                "HTTP 403：API Key 无权限访问该模型，或账号未开通该模型 / 欠费"
                f"（{snippet}）"
            )
        if code == 404:
            return (
                "HTTP 404：接口地址错误，路径不存在"
                f"（base_url 应含 /v1 等路径，且末尾不带 /chat/completions）（{snippet}）"
            )
        if code == 429:
            return f"HTTP 429：请求过于频繁或额度耗尽（{snippet}）"
        if 500 <= code < 600:
            return f"HTTP {code}：服务端错误，稍后重试（{snippet}）"
        return f"HTTP {code}（{snippet}）"


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

        The captured string is lowercased so that 'shift+E' binds as
        'shift+e' — keyboard matches on canonical lowercased key names,
        and a mismatch here means the callback silently never fires.

        Args:
            value: New hotkey combination string (e.g. 'ctrl+i').
        """
        value = value.lower() if value else value
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

    def set_target_lang(self, target_lang: str) -> None:
        """Update only the target language, applied live.

        The engine reads ``target_lang`` from its config reference at
        translate time, so mutating the field is enough — no rebuild needed.

        Args:
            target_lang: New target language code.
        """
        self._config.target_lang = target_lang
        logger.info("Target language set to: %s", target_lang)

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

        Protected by a lock to prevent concurrent execution. LLM calls are
        slower than the old TMT API, so a '翻译中…' notification is shown
        up front so the user knows the request was received.
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

            # LLM latency is higher than the old TMT API; tell the user we
            # accepted the request so they don't keep mashing the hotkey.
            if self._notifier:
                self._notifier("翻译中…")

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
