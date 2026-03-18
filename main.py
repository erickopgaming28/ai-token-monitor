from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QTimer

from config.settings import AppSettings, DB_PATH, APP_DATA_DIR
from core.aggregator import Aggregator
from core.cost_engine import CostEngine
from core.event_bus import EventBus
from core.scanner import Scanner
from db.database import Database
from providers.base import ProviderAdapter
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


# Map provider slugs to adapter classes
ADAPTER_MAP: dict[str, type] = {
    "claude_code": ClaudeCodeAdapter,
    "openai": OpenAIAdapter,
    "gemini": GeminiAdapter,
}


def _build_adapters(settings: AppSettings) -> list[ProviderAdapter]:
    """Build provider adapters from auto-detection + manual config."""
    logger = logging.getLogger("adapters")
    adapters: list[ProviderAdapter] = []
    provider_paths: dict[str, str] = {}

    # Step 1: Auto-detect installed AI tools
    if settings.auto_detect_providers:
        try:
            from core.ai_detector import detect_all
            tools = detect_all()
            for tool in tools:
                if tool.log_path and tool.provider_slug not in settings.disabled_providers:
                    provider_paths[tool.provider_slug] = tool.log_path
                    logger.info(
                        "Auto-detected %s → %s (has_logs=%s)",
                        tool.tool_name, tool.log_path, tool.has_logs,
                    )
        except Exception as e:
            logger.warning("Auto-detection failed: %s", e)

    # Step 2: Manual paths override / add to auto-detected
    for slug, path in settings.manual_provider_paths.items():
        if slug not in settings.disabled_providers and path:
            provider_paths[slug] = path
            logger.info("Manual provider: %s → %s", slug, path)

    # Step 3: Create adapters for each provider with a path
    for slug, path in provider_paths.items():
        adapter_cls = ADAPTER_MAP.get(slug)
        if adapter_cls:
            adapters.append(adapter_cls(path))
            logger.info("Loaded adapter: %s (%s)", slug, path)
        else:
            logger.debug("No adapter for provider '%s', skipping", slug)

    if not adapters:
        logger.warning("No providers detected. Add paths manually in Settings → Providers.")

    return adapters


def _run_pricing_update(db: Database, cost_engine: CostEngine) -> None:
    """Update pricing (cached for 24h)."""
    logger = logging.getLogger("startup")
    try:
        from core.pricing_fetcher import PricingFetcher
        fetcher = PricingFetcher(db, APP_DATA_DIR)
        fetcher.update_all(force=False)
        cost_engine.reload()
        logger.info("Pricing updated")
    except Exception as e:
        logger.debug("Pricing update skipped: %s", e)


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

    # Build adapters from detection + manual config
    adapters = _build_adapters(settings)

    # Update pricing after event loop starts
    QTimer.singleShot(500, lambda: _run_pricing_update(db, cost_engine))

    scanner = Scanner(
        adapters, db,
        scan_interval_ms=settings.scan_interval_seconds * 1000,
        debounce_ms=settings.debounce_ms,
    )

    tray = TrayManager(aggregator, cost_engine=cost_engine, settings=settings)

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
    actions = menu.actions()
    if len(actions) >= 2:
        menu.insertAction(actions[-2], settings_action)
    else:
        menu.addAction(settings_action)

    tray.show()
    scanner.start()

    provider_names = [a.get_provider_name() for a in adapters]
    logger.info("AI Token Monitor started. Providers: %s", ", ".join(provider_names) or "none")

    exit_code = app.exec()
    scanner.stop()
    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
