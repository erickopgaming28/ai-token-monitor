from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from config.settings import AppSettings, DB_PATH
from core.aggregator import Aggregator
from core.cost_engine import CostEngine
from core.event_bus import EventBus
from core.scanner import Scanner
from db.database import Database
from providers.claude_code import ClaudeCodeAdapter
from providers.openai_adapter import OpenAIAdapter
from providers.gemini_adapter import GeminiAdapter
from ui.tray import TrayManager


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    settings = AppSettings.load()
    setup_logging(settings.log_level)
    logger = logging.getLogger("main")

    QCoreApplication.setApplicationName("AI Token Monitor")
    QCoreApplication.setOrganizationName("AITokenMonitor")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    logger.info("Initializing database at %s", DB_PATH)
    db = Database(DB_PATH)
    db.initialize()

    event_bus = EventBus.instance()
    cost_engine = CostEngine(db)
    aggregator = Aggregator(db, cost_engine)

    adapters = []
    if settings.claude_code_enabled:
        adapters.append(ClaudeCodeAdapter(settings.claude_base_path))
    if settings.openai_enabled:
        adapters.append(OpenAIAdapter())
    if settings.gemini_enabled:
        adapters.append(GeminiAdapter())

    scanner = Scanner(
        adapters, db,
        scan_interval_ms=settings.scan_interval_seconds * 1000,
        debounce_ms=settings.debounce_ms,
    )

    tray = TrayManager(aggregator)

    # Add settings menu item
    from PySide6.QtGui import QAction
    from ui.settings_dialog import SettingsDialog

    def _open_settings():
        dlg = SettingsDialog(settings, db)
        if dlg.exec():
            cost_engine.reload()
            db.rebuild_daily_aggregates()
            event_bus.projects_updated.emit([])

    menu = tray._tray.contextMenu()
    settings_action = QAction("Settings", menu)
    settings_action.triggered.connect(_open_settings)
    # Insert before last separator
    actions = menu.actions()
    if len(actions) >= 2:
        menu.insertAction(actions[-2], settings_action)
    else:
        menu.addAction(settings_action)

    tray.show()
    scanner.start()

    logger.info("AI Token Monitor started. Watching: %s", settings.claude_base_path)

    exit_code = app.exec()
    scanner.stop()
    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
