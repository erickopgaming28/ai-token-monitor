from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QCheckBox,
    QPushButton, QTabWidget, QWidget, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QGroupBox, QGridLayout, QListWidget, QListWidgetItem,
    QFileDialog,
)

from config.settings import AppSettings, APP_DATA_DIR
from core.event_bus import EventBus
from db.database import Database
from ui.styles import (
    DARK_THEME, COLOR_BG, COLOR_BG_CARD, COLOR_TEXT, COLOR_BORDER,
    COLOR_ACCENT, COLOR_COST, COLOR_TEXT_DIM, COLOR_TEXT_MUTED,
    COLOR_SAVINGS, COLOR_EXPENSIVE,
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
        self._detected_tools = []
        self.setWindowTitle("AI Token Monitor — Settings")
        self.setFixedSize(560, 540)
        self.setStyleSheet(DARK_THEME)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._providers_tab(), "Providers")
        tabs.addTab(self._pricing_tab(), "Pricing")
        tabs.addTab(self._compare_tab(), "Compare")
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

        self._autostart = QCheckBox("Start with system")
        self._autostart.setChecked(self.settings.start_with_windows)
        lay.addWidget(self._autostart)

        self._auto_detect = QCheckBox("Auto-detect AI tools on startup")
        self._auto_detect.setChecked(self.settings.auto_detect_providers)
        lay.addWidget(self._auto_detect)

        self._log_level = QComboBox()
        self._log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._log_level.setCurrentText(self.settings.log_level)
        lay.addLayout(self._row("Log level:", self._log_level))

        lay.addStretch()
        return w

    # ── Providers Tab ────────────────────────────────────────────

    def _providers_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        # Detected section
        det_group = QGroupBox("Auto-Detected")
        det_lay = QVBoxLayout(det_group)

        info = QLabel("AI tools found on this system. Uncheck to disable.")
        info.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 11px;")
        info.setWordWrap(True)
        det_lay.addWidget(info)

        self._provider_table = QTableWidget()
        self._provider_table.setColumnCount(4)
        self._provider_table.setHorizontalHeaderLabels(["Enabled", "Provider", "Log Path", "Status"])
        self._provider_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._provider_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._provider_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._provider_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._provider_table.setFixedHeight(160)
        det_lay.addWidget(self._provider_table)

        rescan_btn = QPushButton("Rescan System")
        rescan_btn.clicked.connect(self._run_detection)
        det_lay.addWidget(rescan_btn)

        lay.addWidget(det_group)

        # Manual add section
        manual_group = QGroupBox("Add Provider Manually")
        manual_lay = QGridLayout(manual_group)

        manual_lay.addWidget(QLabel("Provider:"), 0, 0)
        self._manual_provider = QComboBox()
        self._refresh_manual_provider_combo()
        manual_lay.addWidget(self._manual_provider, 0, 1)

        manual_lay.addWidget(QLabel("Log path:"), 1, 0)
        path_row = QHBoxLayout()
        self._manual_path = QLineEdit()
        self._manual_path.setPlaceholderText("Path to log directory...")
        path_row.addWidget(self._manual_path)
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(60)
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(browse_btn)
        manual_lay.addLayout(path_row, 1, 1)

        add_btn = QPushButton("Add Provider Path")
        add_btn.clicked.connect(self._add_manual_provider)
        manual_lay.addWidget(add_btn, 2, 1)

        lay.addWidget(manual_group)

        # Manual paths list
        self._manual_table = QTableWidget()
        self._manual_table.setColumnCount(3)
        self._manual_table.setHorizontalHeaderLabels(["Provider", "Path", ""])
        self._manual_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._manual_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._manual_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._manual_table.setFixedHeight(100)
        self._load_manual_paths()
        lay.addWidget(self._manual_table)

        # Run detection on open
        self._run_detection()

        return w

    def _refresh_manual_provider_combo(self) -> None:
        self._manual_provider.clear()
        # Common providers + all from DB
        known = [
            ("Claude Code", "claude_code"),
            ("OpenAI / Codex", "openai"),
            ("Gemini CLI", "gemini"),
            ("Cursor", "cursor"),
            ("Aider", "aider"),
            ("Continue", "continue_dev"),
        ]
        seen = set()
        for name, slug in known:
            self._manual_provider.addItem(f"{name} ({slug})", slug)
            seen.add(slug)
        # Add any DB providers not in known list
        rows = self.db.conn.execute("SELECT slug, name FROM providers ORDER BY name").fetchall()
        for r in rows:
            if r["slug"] not in seen:
                self._manual_provider.addItem(f"{r['name']} ({r['slug']})", r["slug"])

    def _browse_path(self) -> None:
        from pathlib import Path
        start = str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Select log directory", start)
        if path:
            self._manual_path.setText(path)

    def _add_manual_provider(self) -> None:
        slug = self._manual_provider.currentData()
        path = self._manual_path.text().strip()
        if not slug or not path:
            QMessageBox.warning(self, "Error", "Select a provider and enter a path.")
            return
        from pathlib import Path as P
        if not P(path).exists():
            QMessageBox.warning(self, "Error", f"Path does not exist:\n{path}")
            return
        self.settings.manual_provider_paths[slug] = path
        self._manual_path.clear()
        self._load_manual_paths()

    def _load_manual_paths(self) -> None:
        paths = self.settings.manual_provider_paths
        self._manual_table.setRowCount(len(paths))
        for i, (slug, path) in enumerate(paths.items()):
            self._manual_table.setItem(i, 0, QTableWidgetItem(slug))
            path_item = QTableWidgetItem(path)
            path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._manual_table.setItem(i, 1, path_item)

            remove_btn = QPushButton("X")
            remove_btn.setFixedWidth(30)
            remove_btn.setStyleSheet(f"color: {COLOR_EXPENSIVE}; font-weight: bold;")
            remove_btn.clicked.connect(lambda checked, s=slug: self._remove_manual(s))
            self._manual_table.setCellWidget(i, 2, remove_btn)

    def _remove_manual(self, slug: str) -> None:
        self.settings.manual_provider_paths.pop(slug, None)
        self._load_manual_paths()

    def _run_detection(self) -> None:
        self._det_thread = QThread()
        self._det_worker = _DetectorWorker()
        self._det_worker.moveToThread(self._det_thread)
        self._det_thread.started.connect(self._det_worker.run)
        self._det_worker.finished.connect(self._on_detection_done)
        self._det_worker.finished.connect(self._det_thread.quit)
        self._det_thread.start()

    def _on_detection_done(self, tools: list) -> None:
        self._detected_tools = tools
        self._provider_table.setRowCount(len(tools))
        disabled = set(self.settings.disabled_providers)

        for i, tool in enumerate(tools):
            # Checkbox
            chk = QCheckBox()
            chk.setChecked(tool.provider_slug not in disabled)
            chk_widget = QWidget()
            chk_lay = QHBoxLayout(chk_widget)
            chk_lay.addWidget(chk)
            chk_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_lay.setContentsMargins(0, 0, 0, 0)
            self._provider_table.setCellWidget(i, 0, chk_widget)

            # Provider name
            name_item = QTableWidgetItem(f"{tool.tool_name}")
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._provider_table.setItem(i, 1, name_item)

            # Log path
            path_text = tool.log_path or "—"
            path_item = QTableWidgetItem(path_text)
            path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if not tool.has_logs:
                path_item.setForeground(Qt.GlobalColor.gray)
            self._provider_table.setItem(i, 2, path_item)

            # Status
            if tool.has_logs:
                status = "logs found"
                color = COLOR_SAVINGS
            elif tool.log_path:
                status = "no logs yet"
                color = COLOR_TEXT_MUTED
            else:
                status = "cli only"
                color = COLOR_TEXT_MUTED
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._provider_table.setItem(i, 3, status_item)

        if not tools:
            self._provider_table.setRowCount(1)
            item = QTableWidgetItem("No AI tools detected on this system")
            item.setForeground(Qt.GlobalColor.gray)
            self._provider_table.setItem(0, 1, item)

    def _get_disabled_providers(self) -> list[str]:
        disabled: list[str] = []
        for i, tool in enumerate(self._detected_tools):
            widget = self._provider_table.cellWidget(i, 0)
            if widget:
                chk = widget.findChild(QCheckBox)
                if chk and not chk.isChecked():
                    disabled.append(tool.provider_slug)
        return disabled

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

    # ── Compare Tab ───────────────────────────────────────────────

    def _compare_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        info = QLabel(
            "Select models for cost comparison. When viewing a project's detail, "
            "you'll see an estimate of what it would cost if you had used these "
            "models instead."
        )
        info.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 12px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        self._compare_list = QListWidget()
        self._compare_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        rows = self.db.conn.execute(
            """SELECT m.slug, m.name, p.name as provider_name
               FROM models m
               JOIN providers p ON p.id = m.provider_id
               ORDER BY p.name, m.name"""
        ).fetchall()

        selected = set(self.settings.comparison_models)

        for r in rows:
            item = QListWidgetItem(f"{r['provider_name']}  /  {r['name']}")
            item.setData(Qt.ItemDataRole.UserRole, r["slug"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if r["slug"] in selected else Qt.CheckState.Unchecked)
            self._compare_list.addItem(item)

        lay.addWidget(self._compare_list)

        hint = QLabel("Tip: select 3-5 models for a clear comparison")
        hint.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        lay.addWidget(hint)

        return w

    def _get_selected_comparison_models(self) -> list[str]:
        selected: list[str] = []
        for i in range(self._compare_list.count()):
            item = self._compare_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                slug = item.data(Qt.ItemDataRole.UserRole)
                selected.append(slug)
        return selected

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
        self._refresh_manual_provider_combo()
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
        self.settings.start_with_windows = self._autostart.isChecked()
        self.settings.auto_detect_providers = self._auto_detect.isChecked()
        self.settings.log_level = self._log_level.currentText()
        self.settings.disabled_providers = self._get_disabled_providers()
        self.settings.comparison_models = self._get_selected_comparison_models()
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
