from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QBrush, QPen
from PySide6.QtWidgets import QWidget

from ui.styles import COLOR_INPUT, COLOR_OUTPUT, COLOR_BG_CARD_HOVER


class TokenBar(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._input_tokens = 0
        self._output_tokens = 0
        self.setFixedHeight(12)
        self.setMinimumWidth(100)

    def set_values(self, input_tokens: int, output_tokens: int) -> None:
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        total = f"IN: {_fmt(input_tokens)}  OUT: {_fmt(output_tokens)}"
        self.setToolTip(total)
        self.update()

    def paintEvent(self, event) -> None:
        total = self._input_tokens + self._output_tokens
        if total == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        r = h / 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(COLOR_BG_CARD_HOVER)))
        painter.drawRoundedRect(0, 0, w, h, r, r)

        input_w = int(w * self._input_tokens / total)
        output_w = w - input_w

        if input_w > 0:
            painter.setBrush(QBrush(QColor(COLOR_INPUT)))
            painter.drawRoundedRect(0, 0, input_w, h, r, r)
            if output_w > 0:
                painter.drawRect(int(input_w - r), 0, int(r), h)

        if output_w > 0:
            painter.setBrush(QBrush(QColor(COLOR_OUTPUT)))
            painter.drawRoundedRect(input_w, 0, output_w, h, r, r)
            if input_w > 0:
                painter.drawRect(input_w, 0, int(r), h)

        painter.end()


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)
