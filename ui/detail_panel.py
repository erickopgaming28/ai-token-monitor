from __future__ import annotations

import os
import subprocess
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame,
)

from ui.styles import (
    COLOR_BG, COLOR_BG_CARD, COLOR_TEXT_DIM, COLOR_TEXT_MUTED, COLOR_INPUT,
    COLOR_OUTPUT, COLOR_CACHE, COLOR_COST, COLOR_ACCENT, COLOR_BORDER,
)
from ui.token_bar import TokenBar
from ui.project_card import fmt_tokens, fmt_cost


class DetailPanel(QWidget):
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._project_path = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(12, 10, 12, 6)
        self._back_btn = QPushButton("<  Back")
        self._back_btn.setFixedWidth(70)
        self._back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(self._back_btn)
        header.addStretch()
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_widget = QWidget()
        self._content = QVBoxLayout(scroll_widget)
        self._content.setContentsMargins(12, 4, 12, 12)
        self._content.setSpacing(8)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        self._name_label = QLabel()
        self._name_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {COLOR_ACCENT};")
        self._content.addWidget(self._name_label)

        self._path_label = QLabel()
        self._path_label.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED};")
        self._path_label.setWordWrap(True)
        self._content.addWidget(self._path_label)

        self._meta_label = QLabel()
        self._meta_label.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_DIM};")
        self._content.addWidget(self._meta_label)

        self._add_separator()

        self._content.addWidget(self._section("TOKENS"))
        self._token_bar = TokenBar()
        self._token_bar.setFixedHeight(16)
        self._content.addWidget(self._token_bar)

        self._tokens_grid = QWidget()
        self._tokens_layout = QVBoxLayout(self._tokens_grid)
        self._tokens_layout.setContentsMargins(0, 4, 0, 0)
        self._tokens_layout.setSpacing(2)
        self._content.addWidget(self._tokens_grid)

        self._add_separator()
        self._content.addWidget(self._section("COST BY PROVIDER / MODEL"))
        self._breakdown_widget = QWidget()
        self._breakdown_layout = QVBoxLayout(self._breakdown_widget)
        self._breakdown_layout.setContentsMargins(0, 0, 0, 0)
        self._breakdown_layout.setSpacing(2)
        self._content.addWidget(self._breakdown_widget)

        self._add_separator()
        self._content.addWidget(self._section("DAILY HISTORY"))
        self._history_widget = QWidget()
        self._history_layout = QVBoxLayout(self._history_widget)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(1)
        self._content.addWidget(self._history_widget)

        self._add_separator()

        self._quality_label = QLabel("[E] = Exact data   [~] = Estimated")
        self._quality_label.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED};")
        self._content.addWidget(self._quality_label)

        self._open_btn = QPushButton("Open Folder")
        self._open_btn.clicked.connect(self._open_folder)
        self._content.addWidget(self._open_btn)

        self._content.addStretch()

    def load_project(self, detail: dict) -> None:
        self._project_path = detail.get("path", "")
        self._name_label.setText(detail.get("name", ""))
        self._path_label.setText(self._project_path)

        last_act = detail.get("last_activity", "")
        sessions = detail.get("session_count", 0)
        self._meta_label.setText(f"Last activity: {_relative_time(last_act)}  |  Sessions: {sessions}")

        total_in = sum(b.get("total_input", 0) for b in detail.get("breakdown", []))
        total_out = sum(b.get("total_output", 0) for b in detail.get("breakdown", []))
        total_cr = sum(b.get("total_cache_read", 0) for b in detail.get("breakdown", []))
        total_cw = sum(b.get("total_cache_write", 0) for b in detail.get("breakdown", []))

        self._token_bar.set_values(total_in, total_out)

        self._clear_layout(self._tokens_layout)
        self._tokens_layout.addWidget(self._kv_row("Input tokens", fmt_tokens(total_in), COLOR_INPUT))
        self._tokens_layout.addWidget(self._kv_row("Output tokens", fmt_tokens(total_out), COLOR_OUTPUT))
        self._tokens_layout.addWidget(self._kv_row("Cache read", fmt_tokens(total_cr), COLOR_CACHE))
        self._tokens_layout.addWidget(self._kv_row("Cache write", fmt_tokens(total_cw), COLOR_CACHE))
        self._tokens_layout.addWidget(
            self._kv_row("Total", fmt_tokens(total_in + total_out + total_cr + total_cw), COLOR_ACCENT)
        )

        self._clear_layout(self._breakdown_layout)
        current_provider = ""
        for b in detail.get("breakdown", []):
            prov = b.get("provider_name", "")
            if prov != current_provider:
                current_provider = prov
                prov_total = sum(
                    x.get("cost", 0) for x in detail["breakdown"]
                    if x.get("provider_name") == prov
                )
                lbl = QLabel(f"  {prov}: {fmt_cost(prov_total)} [E]")
                lbl.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {COLOR_COST}; background: transparent;")
                self._breakdown_layout.addWidget(lbl)

            model_lbl = QLabel(f"      {b.get('model_name', '')}: {fmt_cost(b.get('cost', 0))}")
            model_lbl.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_DIM}; background: transparent;")
            tooltip = (
                f"Input: {fmt_tokens(b.get('total_input', 0))}\n"
                f"Output: {fmt_tokens(b.get('total_output', 0))}\n"
                f"Cache read: {fmt_tokens(b.get('total_cache_read', 0))}\n"
                f"Cache write: {fmt_tokens(b.get('total_cache_write', 0))}"
            )
            model_lbl.setToolTip(tooltip)
            self._breakdown_layout.addWidget(model_lbl)

        self._clear_layout(self._history_layout)
        for d in detail.get("daily_history", []):
            total_day = d.get("input", 0) + d.get("output", 0)
            row_lbl = QLabel(f"  {d['date']}:  {fmt_tokens(total_day)} tokens  {fmt_cost(d.get('cost', 0))}")
            row_lbl.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_DIM}; background: transparent;")
            self._history_layout.addWidget(row_lbl)

        if not detail.get("daily_history"):
            empty = QLabel("  No history yet")
            empty.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_MUTED}; background: transparent;")
            self._history_layout.addWidget(empty)

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def _kv_row(self, key: str, value: str, color: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        h = QHBoxLayout(w)
        h.setContentsMargins(4, 0, 4, 0)
        k = QLabel(key)
        k.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_DIM}; background: transparent;")
        v = QLabel(value)
        v.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {color}; background: transparent;")
        v.setAlignment(Qt.AlignmentFlag.AlignRight)
        h.addWidget(k)
        h.addStretch()
        h.addWidget(v)
        return w

    def _add_separator(self) -> None:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {COLOR_BORDER}; background: transparent;")
        line.setFixedHeight(1)
        self._content.addWidget(line)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _open_folder(self) -> None:
        path = self._project_path.replace("/", "\\")
        if os.path.isdir(path):
            subprocess.Popen(["explorer", path])

    def _relative_time(ts: str) -> str:
        return _relative_time(ts)


def _relative_time(ts: str) -> str:
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        return f"{seconds // 86400}d ago"
    except Exception:
        return ts[:10] if len(ts) >= 10 else ts
