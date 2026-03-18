from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QCheckBox,
    QPushButton, QTabWidget, QWidget, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QGroupBox, QGridLayout,
)

from config.settings import AppSettings, APP_DATA_DIR
from core.event_bus import EventBus
from db.database import Database
from ui.styles import (
    DARK_THEME, COLOR_BG, COLOR_BG_CARD, COLOR_TEXT, COLOR_BORDER,
    COLOR_ACCENT, COLOR_COST, COLOR_TEXT_DIM, COLOR_TEXT_MUTED,
)

APP_NAME = "AITokenMonitor"


class _PricingWorker(QObject):
    finished = Signal(str)

    def __init__(self, db: Database):
        super().__init__()
        self.db = db

    def run(self) -> None:
        try:
            from core.pricing_fetcher import PricingFetcher
            fetcher = PricingFetcher(self.db, APP_DATA_DIR)
            result = fetcher.update_all(force=True)
            total = sum(len(v) for v in result.values())
            self.finished.emit(f"Updated {total} models from {len(result)} providers")
        except Exception as e:
            self.finished.emit(f"Error: {e}")


class _DetectorWorker(QObject):
    finished = Signal(list)

    def run(self) -> None:
        try:
            from core.ai_detector import detect_all
            tools = detect_all()
            self.finished.emit(tools)
        except Exception as e:
            self.finished.emit([])


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, db: Database, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.db = db
        self.setWindowTitle("AI Token Monitor — Settings")
        self.setFixedSize(540, 520)
        self.setStyleSheet(DARK_THEME)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._detected_tab(), "Detected Tools")
        tabs.addTab(self._pricing_tab(), "Pricing")
        tabs.addTab(self._custom_tab(), "Custom Models")
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    # ── General Tab ──────────────────────────────────────────────

    def _general_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        self._scan_interval = QSpinBox()
        self._scan_interval.setRange(30, 3600)
        self._scan_interval.setSuffix(" sec")
        self._scan_interval.setValue(self.settings.scan_interval_seconds)
        lay.addLayout(self._row("Scan interval:", self._scan_interval))

        self._claude_path = QLineEdit(self.settings.claude_base_path)
        lay.addLayout(self._row("Claude logs path:", self._claude_path))

        self._autostart = QCheckBox("Start with system")
        self._autostart.setChecked(self.settings.start_with_windows)
        lay.addWidget(self._autostart)

        self._log_level = QComboBox()
        self._log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._log_level.setCurrentText(self.settings.log_level)
        lay.addLayout(self._row("Log level:", self._log_level))

        lay.addStretch()
        return w

    # ── Detected Tools Tab ───────────────────────────────────────

    def _detected_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        info = QLabel("AI tools detected on this system:")
        info.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 12px;")
        lay.addWidget(info)

        self._detected_table = QTableWidget()
        self._detected_table.setColumnCount(4)
        self._detected_table.setHorizontalHeaderLabels(["Tool", "Provider", "Version", "Method"])
        self._detected_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 4):
            self._detected_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._detected_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self._detected_table)

        rescan_btn = QPushButton("Rescan")
        rescan_btn.clicked.connect(self._run_detection)
        lay.addWidget(rescan_btn)

        self._run_detection()
        return w

    def _run_detection(self) -> None:
        self._det_thread = QThread()
        self._det_worker = _DetectorWorker()
        self._det_worker.moveToThread(self._det_thread)
        self._det_thread.started.connect(self._det_worker.run)
        self._det_worker.finished.connect(self._on_detection_done)
        self._det_worker.finished.connect(self._det_thread.quit)
        self._det_thread.start()

    def _on_detection_done(self, tools: list) -> None:
        self._detected_table.setRowCount(len(tools))
        for i, tool in enumerate(tools):
            self._detected_table.setItem(i, 0, QTableWidgetItem(tool.tool_name))
            self._detected_table.setItem(i, 1, QTableWidgetItem(tool.provider_name))
            self._detected_table.setItem(i, 2, QTableWidgetItem(tool.version or "—"))
            self._detected_table.setItem(i, 3, QTableWidgetItem(tool.detection_method))
        if not tools:
            self._detected_table.setRowCount(1)
            item = QTableWidgetItem("No AI tools detected")
            item.setForeground(Qt.GlobalColor.gray)
            self._detected_table.setItem(0, 0, item)

    # ── Pricing Tab ──────────────────────────────────────────────

    def _pricing_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        top_row = QHBoxLayout()
        self._update_btn = QPushButton("Update Prices from APIs")
        self._update_btn.clicked.connect(self._fetch_pricing)
        top_row.addWidget(self._update_btn)
        self._pricing_status = QLabel("")
        self._pricing_status.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 11px;")
        top_row.addWidget(self._pricing_status)
        top_row.addStretch()
        lay.addLayout(top_row)

        self._price_table = QTableWidget()
        self._price_table.setColumnCount(5)
        self._price_table.setHorizontalHeaderLabels(
            ["Model", "Input $/M", "Output $/M", "Cache Read $/M", "Cache Write $/M"]
        )
        self._price_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            self._price_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        self._load_pricing_table()
        lay.addWidget(self._price_table)
        return w

    def _load_pricing_table(self) -> None:
        prices = self.db.get_current_pricing()
        self._price_table.setRowCount(len(prices))
        for i, p in enumerate(prices):
            slug_item = QTableWidgetItem(p["slug"])
            slug_item.setFlags(slug_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._price_table.setItem(i, 0, slug_item)
            self._price_table.setItem(i, 1, QTableWidgetItem(str(p["input_rate_per_million"])))
            self._price_table.setItem(i, 2, QTableWidgetItem(str(p["output_rate_per_million"])))
            self._price_table.setItem(i, 3, QTableWidgetItem(str(p["cache_read_rate_per_million"])))
            self._price_table.setItem(i, 4, QTableWidgetItem(str(p["cache_write_rate_per_million"])))

    def _fetch_pricing(self) -> None:
        self._update_btn.setEnabled(False)
        self._pricing_status.setText("Fetching...")
        self._price_thread = QThread()
        self._price_worker = _PricingWorker(self.db)
        self._price_worker.moveToThread(self._price_thread)
        self._price_thread.started.connect(self._price_worker.run)
        self._price_worker.finished.connect(self._on_pricing_done)
        self._price_worker.finished.connect(self._price_thread.quit)
        self._price_thread.start()

    def _on_pricing_done(self, msg: str) -> None:
        self._update_btn.setEnabled(True)
        self._pricing_status.setText(msg)
        self._load_pricing_table()

    # ── Custom Models Tab ────────────────────────────────────────

    def _custom_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        info = QLabel("Add a custom provider/model. Useful for new models or local LLMs.")
        info.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 12px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        # Provider section
        prov_group = QGroupBox("New Provider")
        prov_lay = QGridLayout(prov_group)
        prov_lay.addWidget(QLabel("Name:"), 0, 0)
        self._new_prov_name = QLineEdit()
        self._new_prov_name.setPlaceholderText("e.g. Cohere")
        prov_lay.addWidget(self._new_prov_name, 0, 1)
        prov_lay.addWidget(QLabel("Slug:"), 1, 0)
        self._new_prov_slug = QLineEdit()
        self._new_prov_slug.setPlaceholderText("e.g. cohere (lowercase, no spaces)")
        prov_lay.addWidget(self._new_prov_slug, 1, 1)
        add_prov_btn = QPushButton("Add Provider")
        add_prov_btn.clicked.connect(self._add_provider)
        prov_lay.addWidget(add_prov_btn, 2, 1)
        lay.addWidget(prov_group)

        # Model section
        model_group = QGroupBox("New Model")
        model_lay = QGridLayout(model_group)
        model_lay.addWidget(QLabel("Provider:"), 0, 0)
        self._model_provider = QComboBox()
        self._refresh_provider_combo()
        model_lay.addWidget(self._model_provider, 0, 1)
        model_lay.addWidget(QLabel("Model name:"), 1, 0)
        self._new_model_name = QLineEdit()
        self._new_model_name.setPlaceholderText("e.g. Command R+")
        model_lay.addWidget(self._new_model_name, 1, 1)
        model_lay.addWidget(QLabel("Model slug:"), 2, 0)
        self._new_model_slug = QLineEdit()
        self._new_model_slug.setPlaceholderText("e.g. command-r-plus")
        model_lay.addWidget(self._new_model_slug, 2, 1)

        price_row = QHBoxLayout()
        model_lay.addWidget(QLabel("Input $/M:"), 3, 0)
        self._new_input_rate = QLineEdit("0")
        self._new_input_rate.setFixedWidth(60)
        price_row.addWidget(self._new_input_rate)
        price_row.addWidget(QLabel("Output $/M:"))
        self._new_output_rate = QLineEdit("0")
        self._new_output_rate.setFixedWidth(60)
        price_row.addWidget(self._new_output_rate)
        model_lay.addLayout(price_row, 3, 1)

        add_model_btn = QPushButton("Add Model")
        add_model_btn.clicked.connect(self._add_model)
        model_lay.addWidget(add_model_btn, 4, 1)
        lay.addWidget(model_group)

        lay.addStretch()
        return w

    def _refresh_provider_combo(self) -> None:
        self._model_provider.clear()
        rows = self.db.conn.execute("SELECT slug, name FROM providers ORDER BY name").fetchall()
        for r in rows:
            self._model_provider.addItem(f"{r['name']} ({r['slug']})", r["slug"])

    def _add_provider(self) -> None:
        name = self._new_prov_name.text().strip()
        slug = self._new_prov_slug.text().strip().lower().replace(" ", "_")
        if not name or not slug:
            QMessageBox.warning(self, "Error", "Name and slug are required.")
            return
        existing = self.db.get_provider_id(slug)
        if existing:
            QMessageBox.warning(self, "Error", f"Provider '{slug}' already exists.")
            return
        self.db.conn.execute("INSERT INTO providers (name, slug) VALUES (?, ?)", (name, slug))
        self.db.conn.commit()
        self._new_prov_name.clear()
        self._new_prov_slug.clear()
        self._refresh_provider_combo()
        QMessageBox.information(self, "Done", f"Provider '{name}' added.")

    def _add_model(self) -> None:
        provider_slug = self._model_provider.currentData()
        name = self._new_model_name.text().strip()
        slug = self._new_model_slug.text().strip()
        if not provider_slug or not name or not slug:
            QMessageBox.warning(self, "Error", "All fields are required.")
            return
        existing = self.db.get_model_id(slug)
        if existing:
            QMessageBox.warning(self, "Error", f"Model '{slug}' already exists.")
            return
        try:
            input_rate = float(self._new_input_rate.text())
            output_rate = float(self._new_output_rate.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Rates must be numbers.")
            return

        provider_id = self.db.get_provider_id(provider_slug)
        cur = self.db.conn.execute(
            "INSERT INTO models (provider_id, name, slug) VALUES (?, ?, ?)",
            (provider_id, name, slug),
        )
        self.db.conn.execute(
            """INSERT INTO pricing
               (model_id, input_rate_per_million, output_rate_per_million,
                cache_read_rate_per_million, cache_write_rate_per_million)
               VALUES (?, ?, ?, 0, 0)""",
            (cur.lastrowid, input_rate, output_rate),
        )
        self.db.conn.commit()
        self._new_model_name.clear()
        self._new_model_slug.clear()
        self._load_pricing_table()
        QMessageBox.information(self, "Done", f"Model '{name}' added to {provider_slug}.")

    # ── Helpers ──────────────────────────────────────────────────

    def _row(self, label: str, widget) -> QHBoxLayout:
        h = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFixedWidth(130)
        h.addWidget(lbl)
        h.addWidget(widget)
        return h

    def _save(self) -> None:
        self.settings.scan_interval_seconds = self._scan_interval.value()
        self.settings.claude_base_path = self._claude_path.text()
        self.settings.start_with_windows = self._autostart.isChecked()
        self.settings.log_level = self._log_level.currentText()
        self.settings.save()

        self._apply_autostart()
        self._save_pricing()

        EventBus.instance().settings_changed.emit("all")
        self.accept()

    def _apply_autostart(self) -> None:
        if sys.platform == "win32":
            self._apply_autostart_windows()
        elif sys.platform == "darwin":
            self._apply_autostart_macos()

    def _apply_autostart_windows(self) -> None:
        try:
            import winreg
            run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE)
            if self.settings.start_with_windows:
                exe = sys.executable
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe}" "{__file__}"')
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except OSError:
            pass

    def _apply_autostart_macos(self) -> None:
        from pathlib import Path
        plist_dir = Path.home() / "Library" / "LaunchAgents"
        plist_dir.mkdir(parents=True, exist_ok=True)
        plist_path = plist_dir / "com.aitokenmonitor.plist"
        if self.settings.start_with_windows:
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.aitokenmonitor</string>
    <key>ProgramArguments</key><array>
        <string>{sys.executable}</string>
        <string>{__file__}</string>
    </array>
    <key>RunAtLoad</key><true/>
</dict>
</plist>"""
            plist_path.write_text(plist_content, encoding="utf-8")
        else:
            if plist_path.exists():
                plist_path.unlink()

    def _save_pricing(self) -> None:
        for row in range(self._price_table.rowCount()):
            slug = self._price_table.item(row, 0).text()
            try:
                inp = float(self._price_table.item(row, 1).text())
                out = float(self._price_table.item(row, 2).text())
                cr = float(self._price_table.item(row, 3).text())
                cw = float(self._price_table.item(row, 4).text())
            except (ValueError, AttributeError):
                continue

            model_id = self.db.get_model_id(slug)
            if model_id:
                self.db.conn.execute(
                    """UPDATE pricing SET
                        input_rate_per_million = ?,
                        output_rate_per_million = ?,
                        cache_read_rate_per_million = ?,
                        cache_write_rate_per_million = ?
                       WHERE model_id = ? AND effective_date = (
                           SELECT MAX(effective_date) FROM pricing WHERE model_id = ?
                       )""",
                    (inp, out, cr, cw, model_id, model_id),
                )
        self.db.conn.commit()
