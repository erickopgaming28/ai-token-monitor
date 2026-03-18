COLOR_BG = "#1e1e2e"
COLOR_BG_SURFACE = "#181825"
COLOR_BG_CARD = "#313244"
COLOR_BG_CARD_HOVER = "#45475a"
COLOR_TEXT = "#cdd6f4"
COLOR_TEXT_DIM = "#a6adc8"
COLOR_TEXT_MUTED = "#6c7086"
COLOR_INPUT = "#89b4fa"
COLOR_OUTPUT = "#a6e3a1"
COLOR_CACHE = "#f9e2af"
COLOR_COST = "#a6e3a1"
COLOR_ACCENT = "#89b4fa"
COLOR_BORDER = "#45475a"
COLOR_RED = "#f38ba8"

DARK_THEME = f"""
QWidget {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT};
    font-family: "Segoe UI", "SF Pro Display", "Noto Sans", sans-serif;
    font-size: 13px;
}}
QWidget#popup {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: {COLOR_BG_SURFACE};
    width: 6px;
    margin: 0;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    min-height: 30px;
    border-radius: 3px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QLabel#header {{
    font-size: 15px;
    font-weight: bold;
    color: {COLOR_ACCENT};
}}
QLabel#globalCost {{
    font-size: 20px;
    font-weight: bold;
    color: {COLOR_COST};
}}
QLabel#sectionTitle {{
    font-size: 12px;
    font-weight: bold;
    color: {COLOR_TEXT_DIM};
    text-transform: uppercase;
}}
QPushButton {{
    background-color: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    color: {COLOR_TEXT};
}}
QPushButton:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
}}
QComboBox {{
    background-color: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    color: {COLOR_TEXT};
    min-width: 80px;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT};
    selection-background-color: {COLOR_BG_CARD_HOVER};
    border: 1px solid {COLOR_BORDER};
}}
QToolTip {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    padding: 4px;
    font-size: 12px;
}}
"""
