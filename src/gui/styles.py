DARK_QSS = """
/* ===== DS4Linux Dark Theme ===== */

QWidget {
    background-color: #1e1e2e;
    color: #e0e0e0;
    font-family: "Inter", "Segoe UI", "Ubuntu", "Cantarell", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #1e1e2e;
    border: none;
}

QMainWindow::separator {
    background: #3a3a5c;
    width: 1px;
    height: 1px;
}

QToolBar {
    background: #252536;
    border: none;
    border-bottom: 1px solid #3a3a5c;
    spacing: 8px;
    padding: 4px 8px;
}

QToolBar::separator {
    background: #3a3a5c;
    width: 1px;
    margin: 4px 8px;
}

QPushButton {
    background-color: #2d2d44;
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    padding: 8px 16px;
    color: #e0e0e0;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #3a3a5c;
    border-color: #00d4aa;
}

QPushButton:pressed {
    background-color: #4a4a7c;
    border-color: #00c099;
}

QPushButton:disabled {
    background-color: #252536;
    border-color: #3a3a5c;
    color: #6a6a8a;
}

QPushButton#primaryButton {
    background-color: #00d4aa;
    border-color: #00d4aa;
    color: #1e1e2e;
}

QPushButton#primaryButton:hover {
    background-color: #00e8bb;
    border-color: #00e8bb;
}

QPushButton#primaryButton:pressed {
    background-color: #00c099;
    border-color: #00c099;
}

QPushButton#dangerButton {
    background-color: #ff6b6b;
    border-color: #ff6b6b;
    color: #1e1e2e;
}

QPushButton#dangerButton:hover {
    background-color: #ff5555;
    border-color: #ff5555;
}

QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #2d2d44;
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    padding: 8px 12px;
    color: #e0e0e0;
    selection-background-color: #00d4aa;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #00d4aa;
}

QLineEdit:disabled {
    background-color: #252536;
    color: #6a6a8a;
}

QComboBox {
    background-color: #2d2d44;
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    padding: 6px 12px;
    min-width: 120px;
    color: #e0e0e0;
}

QComboBox:hover {
    border-color: #00d4aa;
}

QComboBox:focus {
    border-color: #00d4aa;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
    subcontrol-origin: padding;
    subcontrol-position: top right;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #a0a0b0;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #2d2d44;
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    selection-background-color: #00d4aa;
    selection-color: #1e1e2e;
    padding: 4px;
    outline: none;
}

QSpinBox, QDoubleSpinBox {
    background-color: #2d2d44;
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    padding: 6px 12px;
    color: #e0e0e0;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #00d4aa;
}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: transparent;
    border: none;
    width: 20px;
    subcontrol-origin: padding;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: #3a3a5c;
    border-radius: 3px;
}

QSlider::groove:horizontal {
    background: #2d2d44;
    height: 6px;
    border-radius: 3px;
    border: 1px solid #3a3a5c;
}

QSlider::handle:horizontal {
    background: #00d4aa;
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: #00e8bb;
}

QSlider::sub-page:horizontal {
    background: #00d4aa;
    border-radius: 3px;
}

QSlider::groove:vertical {
    background: #2d2d44;
    width: 6px;
    border-radius: 3px;
    border: 1px solid #3a3a5c;
}

QSlider::handle:vertical {
    background: #00d4aa;
    width: 18px;
    height: 18px;
    margin: 0 -7px;
    border-radius: 9px;
}

QSlider::sub-page:vertical {
    background: #00d4aa;
    border-radius: 3px;
}

QCheckBox, QRadioButton {
    spacing: 8px;
    color: #e0e0e0;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid #3a3a5c;
    background: #2d2d44;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #00d4aa;
}

QCheckBox::indicator:checked {
    background: #00d4aa;
    border-color: #00d4aa;
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOSIgdmlld0JveD0iMCAwIDEyIDkiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0iTTEgNC41TDQuNSA4TDExIDEiIHN0cm9rZT0iIzFlMWUyZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=);
}

QRadioButton::indicator {
    border-radius: 9px;
}

QRadioButton::indicator:checked {
    background: #2d2d44;
    border-color: #00d4aa;
}

QRadioButton::indicator:checked::after {
    content: "";
    display: block;
    width: 8px;
    height: 8px;
    margin: 3px;
    border-radius: 4px;
    background: #00d4aa;
}

QGroupBox {
    background-color: #252536;
    border: 1px solid #3a3a5c;
    border-radius: 8px;
    margin-top: 16px;
    padding-top: 16px;
    font-weight: 600;
    color: #e0e0e0;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: #00d4aa;
    background-color: #252536;
}

QTabWidget::pane {
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    background: #252536;
    top: -1px;
}

QTabBar::tab {
    background: #2d2d44;
    border: 1px solid #3a3a5c;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 10px 20px;
    margin-right: 2px;
    color: #a0a0b0;
}

QTabBar::tab:selected {
    background: #252536;
    border-color: #3a3a5c;
    color: #00d4aa;
    border-bottom: 1px solid #252536;
}

QTabBar::tab:hover:!selected {
    background: #3a3a5c;
    color: #e0e0e0;
}

QScrollBar:vertical {
    background: #252536;
    width: 10px;
    border: none;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #3a3a5c;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #6a6a8a;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: #252536;
    height: 10px;
    border: none;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background: #3a3a5c;
    border-radius: 5px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background: #6a6a8a;
}

QListWidget, QTreeWidget, QTableWidget {
    background: #252536;
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    outline: none;
    alternate-background-color: #2d2d44;
}

QListWidget::item, QTreeWidget::item {
    padding: 8px 12px;
    border: none;
}

QListWidget::item:selected, QTreeWidget::item:selected {
    background: #00d4aa;
    color: #1e1e2e;
}

QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {
    background: #3a3a5c;
}

QHeaderView::section {
    background: #2d2d44;
    border: none;
    border-bottom: 1px solid #3a3a5c;
    padding: 8px 12px;
    font-weight: 600;
    color: #a0a0b0;
}

QProgressBar {
    background: #2d2d44;
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    text-align: center;
    color: #e0e0e0;
    height: 20px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00d4aa, stop:1 #00e8bb);
    border-radius: 5px;
}

QToolTip {
    background: #2d2d44;
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    padding: 8px 12px;
    color: #e0e0e0;
}

QMenu {
    background: #252536;
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
    color: #e0e0e0;
}

QMenu::item:selected {
    background: #00d4aa;
    color: #1e1e2e;
}

QMenu::separator {
    height: 1px;
    background: #3a3a5c;
    margin: 4px 8px;
}

QDockWidget {
    titlebar-close-icon: url(close.png);
    titlebar-normal-icon: url(undock.png);
}

QDockWidget::title {
    background: #252536;
    padding: 8px 12px;
    border-bottom: 1px solid #3a3a5c;
    font-weight: 600;
}

QStatusBar {
    background: #252536;
    border-top: 1px solid #3a3a5c;
    color: #a0a0b0;
}

QSplitter::handle {
    background: #3a3a5c;
}

QSplitter::handle:horizontal {
    width: 2px;
}

QSplitter::handle:vertical {
    height: 2px;
}

QSplitter::handle:hover {
    background: #00d4aa;
}
"""

def get_stylesheet() -> str:
    return DARK_QSS