from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    token_events_ingested = Signal(int)
    projects_updated = Signal(list)
    scan_started = Signal()
    scan_completed = Signal(int, float)
    scan_error = Signal(str)
    force_rescan = Signal()
    pause_scanning = Signal(bool)
    settings_changed = Signal(str)

    _instance: EventBus | None = None

    @classmethod
    def instance(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
