from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from core.aggregator import Aggregator
from core.event_bus import EventBus
from ui.popup import PopupPanel


def _create_icon() -> QIcon:
    px = QPixmap(64, 64)
    px.fill(QColor(0, 0, 0, 0))
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#89b4fa"))
    painter.setPen(QColor("#1e1e2e"))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    painter.setPen(QColor("#1e1e2e"))
    font = QFont("Segoe UI", 24, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(px.rect(), 0x0084, "AI")  # AlignCenter
    painter.end()
    return QIcon(px)


class TrayManager:
    def __init__(self, aggregator: Aggregator):
        self._aggregator = aggregator
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(_create_icon())
        self._tray.setToolTip("AI Token Monitor")

        self._popup = PopupPanel(aggregator)
        self._paused = False

        self._build_menu()
        self._tray.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()

        dashboard_action = QAction("Dashboard", menu)
        dashboard_action.triggered.connect(self._show_popup)
        menu.addAction(dashboard_action)

        menu.addSeparator()

        self._pause_action = QAction("Pause Monitoring", menu)
        self._pause_action.triggered.connect(self._toggle_pause)
        menu.addAction(self._pause_action)

        rescan_action = QAction("Rescan Now", menu)
        rescan_action.triggered.connect(lambda: EventBus.instance().force_rescan.emit())
        menu.addAction(rescan_action)

        menu.addSeparator()

        exit_action = QAction("Exit", menu)
        exit_action.triggered.connect(QApplication.quit)
        menu.addAction(exit_action)

        self._tray.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_popup()

    def _show_popup(self) -> None:
        if self._popup.isVisible():
            self._popup.hide()
            return
        geo = self._tray.geometry()
        self._popup.show_at_tray(geo)

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        EventBus.instance().pause_scanning.emit(self._paused)
        self._pause_action.setText("Resume Monitoring" if self._paused else "Pause Monitoring")

    def show(self) -> None:
        self._tray.show()
