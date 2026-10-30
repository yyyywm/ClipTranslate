"""Configuration management for ClipTranslate."""

import configparser
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)


def _base_dir() -> Path:
    """Return the application base directory.

    Works both in development and when bundled by PyInstaller.
    In a bundled app this points to the PyInstaller extraction directory
    (where bundled resources such as icons live).
    """
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def _runtime_dir() -> Path:
    """Return a writable directory for runtime data.

    In development this is the project root. In a bundled PyInstaller app
    this is the directory containing the executable, so logs and config.ini
    persist across runs and are easy for users to find.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


class ConfigManager:
    """Manages reading, writing, and validation of the application config."""

    DEFAULT_CONFIG: Dict[str, str] = {
        "provider": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "language": "en",
        "prompt": "",
        "shortcut": "ctrl+i",
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
            self._config_file = _runtime_dir() / "resource" / "config.ini"
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

    def update_partial(self, **fields: str) -> None:
        """Merge specific keys into the persisted config without a full rewrite.

        Reads current on-disk values first, so UI drafts that haven't been
        saved yet are not persisted. Used for live-applied fields like the
        target language, which take effect immediately without a save step.

        Args:
            **fields: Key-value pairs to merge into the persisted config.
        """
        current = self.load()
        current.update(fields)
        self.save(current)

    def validate(self, data: Dict[str, str]) -> List[str]:
        """Validate configuration values.

        Args:
            data: Configuration dictionary to validate.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: List[str] = []
        if not data.get("base_url", "").strip():
            errors.append("接口地址 (Base URL) is required")
        if not data.get("api_key", "").strip():
            errors.append("API Key is required")
        if not data.get("model", "").strip():
            errors.append("模型名 (Model) is required")
        if data.get("language", "en") not in self.SUPPORTED_LANGUAGES:
            errors.append(
                f"Unsupported language '{data.get('language')}'. "
                f"Supported: {', '.join(self.SUPPORTED_LANGUAGES)}"
            )
        return errors
