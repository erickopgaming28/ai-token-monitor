from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from ui.token_bar import TokenBar
from ui.styles import COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_COST, COLOR_TEXT_DIM, COLOR_INPUT, COLOR_OUTPUT


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fmt_cost(c: float) -> str:
    if c >= 1:
        return f"${c:.2f}"
    if c >= 0.01:
        return f"${c:.3f}"
    if c > 0:
        return f"${c:.4f}"
    return "$0.00"


class ProjectCard(QWidget):
    clicked = Signal(int)

    def __init__(self, project_data: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self._project_id = project_data["id"]
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet(f"""
            ProjectCard {{
                background-color: {COLOR_BG_CARD};
                border-radius: 8px;
                padding: 0px;
            }}
            ProjectCard:hover {{
                background-color: {COLOR_BG_CARD_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        name_label = QLabel(project_data["name"])
        name_label.setStyleSheet("font-weight: bold; font-size: 14px; background: transparent;")

        cost_label = QLabel(fmt_cost(project_data.get("total_cost", 0)))
        cost_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {COLOR_COST}; background: transparent;")
        cost_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        top_row.addWidget(name_label)
        top_row.addStretch()
        top_row.addWidget(cost_label)
        layout.addLayout(top_row)

        total = project_data.get("total_input", 0) + project_data.get("total_output", 0)
        total_label = QLabel(f"{fmt_tokens(total)} tokens")
        total_label.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 12px; background: transparent;")
        layout.addWidget(total_label)

        self._bar = TokenBar(self)
        self._bar.set_values(project_data.get("total_input", 0), project_data.get("total_output", 0))
        layout.addWidget(self._bar)

        counts_row = QHBoxLayout()
        in_label = QLabel(f"IN: {fmt_tokens(project_data.get('total_input', 0))}")
        in_label.setStyleSheet(f"color: {COLOR_INPUT}; font-size: 11px; background: transparent;")
        out_label = QLabel(f"OUT: {fmt_tokens(project_data.get('total_output', 0))}")
        out_label.setStyleSheet(f"color: {COLOR_OUTPUT}; font-size: 11px; background: transparent;")
        counts_row.addWidget(in_label)
        counts_row.addStretch()
        counts_row.addWidget(out_label)
        layout.addLayout(counts_row)

        path = project_data.get("path", "")
        self.setToolTip(f"{path}\nLast activity: {project_data.get('last_activity', 'N/A')}")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._project_id)

    def update_data(self, data: dict) -> None:
        self._bar.set_values(data.get("total_input", 0), data.get("total_output", 0))
