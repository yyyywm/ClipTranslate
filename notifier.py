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
