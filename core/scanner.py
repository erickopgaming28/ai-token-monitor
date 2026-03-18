from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QThread, QFileSystemWatcher, Slot

from core.event_bus import EventBus
from db.database import Database
from providers.base import ProviderAdapter, TokenEvent

logger = logging.getLogger(__name__)


class ScannerWorker(QObject):
    def __init__(self, adapters: list[ProviderAdapter], db: Database):
        super().__init__()
        self.adapters = adapters
        self.db = db
        self.paused = False

    @Slot()
    def run_scan(self) -> None:
        if self.paused:
            return

        bus = EventBus.instance()
        bus.scan_started.emit()
        t0 = time.monotonic()
        total_files = 0
        total_new_events = 0

        try:
            for adapter in self.adapters:
                provider_slug = adapter.get_provider_slug()
                provider_id = self.db.get_provider_id(provider_slug)
                if not provider_id:
                    continue

                files = adapter.discover_files()
                for file_path in files:
                    total_files += 1
                    try:
                        state = self.db.get_scan_state(file_path)
                        offset = state["byte_offset"] if state else 0

                        try:
                            st = os.stat(file_path)
                        except OSError:
                            continue

                        current_mtime = st.st_mtime
                        current_size = st.st_size

                        if state and abs(state["file_mtime"] - current_mtime) < 0.001 and state["file_size"] == current_size:
                            continue

                        if state and current_size < offset:
                            offset = 0

                        events, new_offset = adapter.parse_file(file_path, offset)

                        if events:
                            new_count = self._ingest_events(events, provider_id, provider_slug)
                            total_new_events += new_count

                        self.db.upsert_scan_state(file_path, new_offset, current_mtime, current_size)

                    except Exception as e:
                        logger.error("Error scanning %s: %s", file_path, e)

            if total_new_events > 0:
                self.db.rebuild_daily_aggregates()
                bus.token_events_ingested.emit(total_new_events)

                project_ids = self._get_active_project_ids()
                bus.projects_updated.emit(project_ids)

        except Exception as e:
            logger.error("Scan error: %s", e)
            bus.scan_error.emit(str(e))

        duration = time.monotonic() - t0
        bus.scan_completed.emit(total_files, duration)
        logger.info("Scan done: %d files, %d new events, %.2fs", total_files, total_new_events, duration)

    def _ingest_events(self, events: list[TokenEvent], provider_id: int, provider_slug: str) -> int:
        count = 0
        for ev in events:
            project_name = Path(ev.project_path).name
            project_id = self.db.ensure_project(ev.project_path, project_name)

            model_id = self.db.get_model_id(ev.model_slug)
            if not model_id:
                model_id = self.db.ensure_model(ev.model_slug, provider_slug)
            if model_id == -1:
                continue

            session_id = self.db.ensure_session(
                ev.session_id, project_id, provider_id, ev.timestamp
            )

            inserted = self.db.insert_token_event(
                session_id=session_id,
                project_id=project_id,
                provider_id=provider_id,
                model_id=model_id,
                message_id=ev.message_id,
                input_tokens=ev.input_tokens,
                output_tokens=ev.output_tokens,
                cache_read_tokens=ev.cache_read_tokens,
                cache_write_tokens=ev.cache_write_tokens,
                timestamp=ev.timestamp,
                source_file=ev.source_file,
                source_line=ev.source_line,
                data_quality=ev.data_quality,
                is_subagent=ev.is_subagent,
                agent_id=ev.agent_id,
            )
            if inserted:
                count += 1
        return count

    def _get_active_project_ids(self) -> list[int]:
        rows = self.db.conn.execute(
            "SELECT id FROM projects WHERE is_archived = 0 ORDER BY last_activity DESC"
        ).fetchall()
        return [r["id"] for r in rows]


class Scanner(QObject):
    def __init__(self, adapters: list[ProviderAdapter], db: Database, scan_interval_ms: int = 300_000, debounce_ms: int = 1000):
        super().__init__()
        self._thread = QThread()
        self._worker = ScannerWorker(adapters, db)
        self._worker.moveToThread(self._thread)

        self._watcher = QFileSystemWatcher()

        watch_dirs: list[str] = []
        for adapter in adapters:
            if hasattr(adapter, "_base") and adapter._base.exists():
                watch_dirs.append(str(adapter._base))
                for d in adapter._base.iterdir():
                    if d.is_dir():
                        watch_dirs.append(str(d))
        if watch_dirs:
            self._watcher.addPaths(watch_dirs)
        self._watcher.directoryChanged.connect(self._on_dir_changed)

        self._periodic_timer = QTimer()
        self._periodic_timer.setInterval(scan_interval_ms)
        self._periodic_timer.timeout.connect(self._trigger_scan)

        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(debounce_ms)
        self._debounce_timer.timeout.connect(self._trigger_scan)

        bus = EventBus.instance()
        bus.force_rescan.connect(self._trigger_scan)
        bus.pause_scanning.connect(self._on_pause)

    def start(self) -> None:
        self._thread.start()
        self._periodic_timer.start()
        self._trigger_scan()

    def stop(self) -> None:
        self._periodic_timer.stop()
        self._debounce_timer.stop()
        self._thread.quit()
        self._thread.wait(5000)

    def _on_dir_changed(self, _path: str) -> None:
        self._debounce_timer.start()

    def _trigger_scan(self) -> None:
        QTimer.singleShot(0, self._worker.run_scan)

    def _on_pause(self, paused: bool) -> None:
        self._worker.paused = paused
        if paused:
            self._periodic_timer.stop()
        else:
            self._periodic_timer.start()
            self._trigger_scan()
