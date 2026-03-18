from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QComboBox, QStackedWidget,
)

from core.aggregator import Aggregator
from core.event_bus import EventBus
from ui.project_card import ProjectCard, fmt_cost
from ui.detail_panel import DetailPanel
from ui.styles import COLOR_BG, COLOR_ACCENT, COLOR_COST, COLOR_TEXT_DIM, DARK_THEME


PERIODS = [
    ("All Time", "all"),
    ("Today", "today"),
    ("This Week", "week"),
    ("This Month", "month"),
]


class PopupPanel(QWidget):
    def __init__(self, aggregator: Aggregator, parent: QWidget | None = None):
        super().__init__(parent)
        self.aggregator = aggregator
        self._cards: list[ProjectCard] = []
        self._current_period = "all"

        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setObjectName("popup")
        self.setFixedWidth(380)
        self.setMinimumHeight(200)
        self.setMaximumHeight(560)
        self.setStyleSheet(DARK_THEME)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)

        # Page 0: Project list
        list_page = QWidget()
        list_layout = QVBoxLayout(list_page)
        list_layout.setContentsMargins(12, 10, 12, 10)
        list_layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("AI Token Monitor")
        title.setObjectName("header")
        header.addWidget(title)
        header.addStretch()

        self._period_combo = QComboBox()
        for label, _ in PERIODS:
            self._period_combo.addItem(label)
        self._period_combo.currentIndexChanged.connect(self._on_period_changed)
        header.addWidget(self._period_combo)
        list_layout.addLayout(header)

        cost_row = QHBoxLayout()
        self._global_cost_label = QLabel("$0.00")
        self._global_cost_label.setObjectName("globalCost")
        cost_row.addWidget(self._global_cost_label)
        cost_row.addStretch()

        self._project_count_label = QLabel("0 projects")
        self._project_count_label.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 12px;")
        cost_row.addWidget(self._project_count_label)
        list_layout.addLayout(cost_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_widget = QWidget()
        self._scroll_widget.setStyleSheet(f"background: {COLOR_BG};")
        self._scroll_layout = QVBoxLayout(self._scroll_widget)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(6)
        self._scroll_layout.addStretch()
        self._scroll.setWidget(self._scroll_widget)
        list_layout.addWidget(self._scroll)

        self._stack.addWidget(list_page)

        # Page 1: Detail
        self._detail = DetailPanel()
        self._detail.back_requested.connect(lambda: self._stack.setCurrentIndex(0))
        self._stack.addWidget(self._detail)

    def _connect_signals(self) -> None:
        bus = EventBus.instance()
        bus.projects_updated.connect(self._on_projects_updated)

    def _on_period_changed(self, index: int) -> None:
        _, period = PERIODS[index]
        self._current_period = period
        self.refresh()

    def _on_projects_updated(self, _project_ids: list[int]) -> None:
        if self.isVisible():
            self.refresh()

    def refresh(self) -> None:
        projects = self.aggregator.get_all_projects(self._current_period)
        global_cost = self.aggregator.get_global_cost(self._current_period)

        self._global_cost_label.setText(fmt_cost(global_cost))
        self._project_count_label.setText(f"{len(projects)} project{'s' if len(projects) != 1 else ''}")

        # Clear old cards
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        # Remove stretch
        while self._scroll_layout.count():
            item = self._scroll_layout.takeAt(0)

        for p in projects:
            card = ProjectCard(p)
            card.clicked.connect(self._show_detail)
            self._scroll_layout.addWidget(card)
            self._cards.append(card)

        self._scroll_layout.addStretch()

    def _show_detail(self, project_id: int) -> None:
        detail = self.aggregator.get_project_detail(project_id, self._current_period)
        self._detail.load_project(detail)
        self._stack.setCurrentIndex(1)

    def show_at_tray(self, tray_geometry) -> None:
        self.refresh()
        self._stack.setCurrentIndex(0)

        self.adjustSize()

        screen = self.screen()
        if screen:
            avail = screen.availableGeometry()
        else:
            from PySide6.QtWidgets import QApplication
            avail = QApplication.primaryScreen().availableGeometry()

        x = tray_geometry.x() + tray_geometry.width() // 2 - self.width() // 2
        y = avail.bottom() - self.height()

        if x + self.width() > avail.right():
            x = avail.right() - self.width()
        if x < avail.left():
            x = avail.left()

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
