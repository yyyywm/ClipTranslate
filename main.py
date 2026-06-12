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
