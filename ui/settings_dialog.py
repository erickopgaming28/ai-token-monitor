from __future__ import annotations

import sys
import winreg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QCheckBox,
    QPushButton, QTabWidget, QWidget, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox,
)

from config.settings import AppSettings
from core.event_bus import EventBus
from db.database import Database
from ui.styles import DARK_THEME, COLOR_BG, COLOR_BG_CARD, COLOR_TEXT, COLOR_BORDER

APP_NAME = "AITokenMonitor"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, db: Database, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.db = db
        self.setWindowTitle("AI Token Monitor — Settings")
        self.setFixedSize(480, 420)
        self.setStyleSheet(DARK_THEME)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._pricing_tab(), "Pricing")
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

        self._autostart = QCheckBox("Start with Windows")
        self._autostart.setChecked(self.settings.start_with_windows)
        lay.addWidget(self._autostart)

        self._log_level = QComboBox()
        self._log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._log_level.setCurrentText(self.settings.log_level)
        lay.addLayout(self._row("Log level:", self._log_level))

        lay.addStretch()
        return w

    def _pricing_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        self._price_table = QTableWidget()
        self._price_table.setColumnCount(5)
        self._price_table.setHorizontalHeaderLabels(
            ["Model", "Input $/M", "Output $/M", "Cache Read $/M", "Cache Write $/M"]
        )
        self._price_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            self._price_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

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

        lay.addWidget(self._price_table)
        return w

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
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
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
