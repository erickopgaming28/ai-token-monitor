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
    COLOR_SAVINGS, COLOR_EXPENSIVE, COLOR_COMPARE,
)
from ui.token_bar import TokenBar
from ui.project_card import fmt_tokens, fmt_cost


class DetailPanel(QWidget):
    back_requested = Signal()

    def __init__(self, cost_engine=None, settings=None, parent: QWidget | None = None):
        super().__init__(parent)
        self._project_path = ""
        self._cost_engine = cost_engine
        self._settings = settings
        self._current_tokens: dict = {}
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

        # ── Comparison Section ───────────────────────────────────
        self._add_separator()
        self._compare_header = self._section("COST COMPARISON (ESTIMATE)")
        self._content.addWidget(self._compare_header)

        self._compare_info = QLabel("Select models to compare in Settings → Compare")
        self._compare_info.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED}; background: transparent;")
        self._compare_info.setWordWrap(True)
        self._content.addWidget(self._compare_info)

        self._compare_widget = QWidget()
        self._compare_layout = QVBoxLayout(self._compare_widget)
        self._compare_layout.setContentsMargins(0, 0, 0, 0)
        self._compare_layout.setSpacing(3)
        self._content.addWidget(self._compare_widget)

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

        self._current_tokens = {
            "input": total_in, "output": total_out,
            "cache_read": total_cr, "cache_write": total_cw,
        }

        self._token_bar.set_values(total_in, total_out)

        self._clear_layout(self._tokens_layout)
        self._tokens_layout.addWidget(self._kv_row("Input tokens", fmt_tokens(total_in), COLOR_INPUT))
        self._tokens_layout.addWidget(self._kv_row("Output tokens", fmt_tokens(total_out), COLOR_OUTPUT))
        self._tokens_layout.addWidget(self._kv_row("Cache read", fmt_tokens(total_cr), COLOR_CACHE))
        self._tokens_layout.addWidget(self._kv_row("Cache write", fmt_tokens(total_cw), COLOR_CACHE))
        self._tokens_layout.addWidget(
            self._kv_row("Total", fmt_tokens(total_in + total_out + total_cr + total_cw), COLOR_ACCENT)
        )

        # Real cost breakdown
        self._clear_layout(self._breakdown_layout)
        real_total_cost = 0.0
        current_provider = ""
        for b in detail.get("breakdown", []):
            prov = b.get("provider_name", "")
            if prov != current_provider:
                current_provider = prov
                prov_total = sum(
                    x.get("cost", 0) for x in detail["breakdown"]
                    if x.get("provider_name") == prov
                )
                real_total_cost += prov_total
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

        # Comparison
        self._render_comparison(real_total_cost)

        # History
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

    def _render_comparison(self, real_total_cost: float) -> None:
        """Render 'what if' cost comparison for selected models."""
        self._clear_layout(self._compare_layout)

        if not self._cost_engine or not self._settings:
            self._compare_info.setVisible(True)
            return

        comp_models = self._settings.comparison_models
        if not comp_models:
            self._compare_info.setVisible(True)
            self._compare_info.setText("Select models to compare in Settings → Compare")
            return

        self._compare_info.setVisible(False)

        tokens = self._current_tokens
        if tokens.get("input", 0) + tokens.get("output", 0) == 0:
            info = QLabel("  No tokens to compare")
            info.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_MUTED}; background: transparent;")
            self._compare_layout.addWidget(info)
            return

        results = self._cost_engine.compare(
            comp_models,
            tokens.get("input", 0),
            tokens.get("output", 0),
            tokens.get("cache_read", 0),
            tokens.get("cache_write", 0),
        )

        # Header row
        hdr = QLabel("  If you used these models instead:")
        hdr.setStyleSheet(f"font-size: 11px; color: {COLOR_COMPARE}; font-weight: bold; background: transparent;")
        self._compare_layout.addWidget(hdr)

        for cb in results:
            model_name = self._cost_engine.get_model_name(cb.model_slug)
            hypo_cost = cb.total_cost
            diff = hypo_cost - real_total_cost

            if diff < -0.001:
                diff_text = f"  {fmt_cost(abs(diff))} cheaper"
                diff_color = COLOR_SAVINGS
                arrow = "▼"
            elif diff > 0.001:
                diff_text = f"  {fmt_cost(diff)} more"
                diff_color = COLOR_EXPENSIVE
                arrow = "▲"
            else:
                diff_text = "  same cost"
                diff_color = COLOR_TEXT_MUTED
                arrow = "="

            # Row widget
            row_w = QWidget()
            row_w.setStyleSheet(f"background: {COLOR_BG_CARD}; border-radius: 4px;")
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(8, 4, 8, 4)

            name_lbl = QLabel(f"{model_name}")
            name_lbl.setStyleSheet(f"font-size: 12px; color: {COLOR_COMPARE}; background: transparent;")
            row_h.addWidget(name_lbl)

            row_h.addStretch()

            cost_lbl = QLabel(fmt_cost(hypo_cost))
            cost_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {COLOR_TEXT_DIM}; background: transparent;")
            row_h.addWidget(cost_lbl)

            diff_lbl = QLabel(f" {arrow}{diff_text}")
            diff_lbl.setStyleSheet(f"font-size: 11px; color: {diff_color}; background: transparent;")
            row_h.addWidget(diff_lbl)

            # Tooltip with formula
            rates = self._cost_engine.get_model_rates(cb.model_slug)
            if rates:
                tip = (
                    f"Formula: (input × ${rates['input']}/M) + (output × ${rates['output']}/M)"
                    f"\n+ (cache_read × ${rates['cache_read']}/M) + (cache_write × ${rates['cache_write']}/M)"
                    f"\n\nInput: {fmt_tokens(tokens['input'])} × ${rates['input']}/M = {fmt_cost(cb.input_cost)}"
                    f"\nOutput: {fmt_tokens(tokens['output'])} × ${rates['output']}/M = {fmt_cost(cb.output_cost)}"
                    f"\nCache read: {fmt_tokens(tokens['cache_read'])} × ${rates['cache_read']}/M = {fmt_cost(cb.cache_read_cost)}"
                    f"\nCache write: {fmt_tokens(tokens['cache_write'])} × ${rates['cache_write']}/M = {fmt_cost(cb.cache_write_cost)}"
                    f"\n\nTotal: {fmt_cost(hypo_cost)}"
                    f"\nYour actual cost: {fmt_cost(real_total_cost)}"
                    f"\nDifference: {arrow} {fmt_cost(abs(diff))}"
                )
                row_w.setToolTip(tip)

            self._compare_layout.addWidget(row_w)

        # Summary
        if results:
            cheapest = results[0]
            if cheapest.total_cost < real_total_cost - 0.001:
                savings = real_total_cost - cheapest.total_cost
                cheapest_name = self._cost_engine.get_model_name(cheapest.model_slug)
                summary = QLabel(
                    f"  Best alternative: {cheapest_name} — saves {fmt_cost(savings)}"
                )
                summary.setStyleSheet(
                    f"font-size: 11px; font-weight: bold; color: {COLOR_SAVINGS}; background: transparent;"
                )
                self._compare_layout.addWidget(summary)

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
        import sys as _sys
        if _sys.platform == "win32":
            path = self._project_path.replace("/", "\\")
            if os.path.isdir(path):
                subprocess.Popen(["explorer", path])
        elif _sys.platform == "darwin":
            if os.path.isdir(self._project_path):
                subprocess.Popen(["open", self._project_path])
        else:
            if os.path.isdir(self._project_path):
                subprocess.Popen(["xdg-open", self._project_path])

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
