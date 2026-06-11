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
