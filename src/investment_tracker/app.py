"""Application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from investment_tracker.config import (
    CONFIG_PATH,
    AppConfig,
    default_first_run_config,
    load as load_config,
    save as save_config,
)
from investment_tracker.ui.main_window import MainWindow
from investment_tracker.ui.styles import APP_STYLESHEET

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


def bootstrap_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        data_directory = str(EXAMPLES_DIR) if EXAMPLES_DIR.is_dir() else ""
        config = default_first_run_config(data_directory)
        save_config(config)
        return config
    return load_config()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("Investment Tracker")
    app.setOrganizationName("investment-tracker")
    app.setStyle("Fusion")
    font = QFont("DejaVu Sans")
    font.setPointSize(12)
    app.setFont(font)
    app.setStyleSheet(APP_STYLESHEET)

    config = bootstrap_config()
    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
