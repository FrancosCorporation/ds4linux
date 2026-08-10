DARK_QSS = """
/* ===== DS4Linux Dark Theme ===== */
/* Base colors */
@bg-primary: #1e1e2e;
@bg-secondary: #252536;
@bg-tertiary: #2d2d44;
@bg-hover: #3a3a5c;
@bg-pressed: #4a4a7c;
@fg-primary: #e0e0e0;
@fg-secondary: #a0a0b0;
@fg-muted: #6a6a8a;
@accent: #00d4aa;
@accent-hover: #00e8bb;
@accent-pressed: #00c099;
@border: #3a3a5c;
@border-focus: #00d4aa;
@error: #ff6b6b;
@warning: #ffd93d;
@success: #6bff6b;

/* Global */
* {
    font-family: "Inter", "Segoe UI", "Ubuntu", "Cantarell", sans-serif;
    font-size: 13px;
    color: @fg-primary;
    background-color: transparent;
    selection-background-color: @accent;
    selection-color: @bg-primary;
}

QWidget {
    background-color: @bg-primary;
    color: @fg-primary;
}

/* Main Window */
QMainWindow {
    background-color: @bg-primary;
    border: none;
}

QMainWindow::separator {
    background: @border;
    width: 1px;
    height: 1px;
}

/* Toolbars */
QToolBar {
    background: @bg-secondary;
    border: none;
    border-bottom: 1px solid @border;
    spacing: 8px;
    padding: 4px 8px;
}

QToolBar::separator {
    background: @border;
    width: 1px;
    margin: 4px 8px;
}

/* Buttons */
QPushButton {
    background-color: @bg-tertiary;
    border: 1px solid @border;
    border-radius: 6px;
    padding: 8px 16px;
    color: @fg-primary;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover {
    background-color: @bg-hover;
    border-color: @accent;
}

QPushButton:pressed {
    background-color: @bg-pressed;
    border-color: @accent-pressed;
}

QPushButton:disabled {
    background-color: @bg-secondary;
    border-color: @border;
    color: @fg-muted;
}

QPushButton#primaryButton {
    background-color: @accent;
    border-color: @accent;
    color: @bg-primary;
}

QPushButton#primaryButton:hover {
    background-color: @accent-hover;
    border-color: @accent-hover;
}

QPushButton#primaryButton:pressed {
    background-color: @accent-pressed;
    border-color: @accent-pressed;
}

QPushButton#dangerButton {
    background-color: @error;
    border-color: @error;
    color: @bg-primary;
}

QPushButton#dangerButton:hover {
    background-color: #ff5555;
    border-color: #ff5555;
}

/* Line Edit */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: @bg-tertiary;
    border: 1px solid @border;
    border-radius: 6px;
    padding: 8px 12px;
    color: @fg-primary;
    selection-background-color: @accent;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: @border-focus;
}

QLineEdit:disabled {
    background-color: @bg-secondary;
    color: @fg-muted;
}

/* ComboBox */
QComboBox {
    background-color: @bg-tertiary;
    border: 1px solid @border;
    border-radius: 6px;
    padding: 6px 12px;
    min-width: 120px;
    color: @fg-primary;
}

QComboBox:hover {
    border-color: @accent;
}

QComboBox:focus {
    border-color: @border-focus;
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
    border-top: 6px solid @fg-secondary;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: @bg-tertiary;
    border: 1px solid @border;
    border-radius: 6px;
    selection-background-color: @accent;
    selection-color: @bg-primary;
    padding: 4px;
    outline: none;
}

/* SpinBox */
QSpinBox, QDoubleSpinBox {
    background-color: @bg-tertiary;
    border: 1px solid @border;
    border-radius: 6px;
    padding: 6px 12px;
    color: @fg-primary;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: @border-focus;
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
    background: @bg-hover;
    border-radius: 3px;
}

/* Slider */
QSlider::groove:horizontal {
    background: @bg-tertiary;
    height: 6px;
    border-radius: 3px;
    border: 1px solid @border;
}

QSlider::handle:horizontal {
    background: @accent;
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: @accent-hover;
}

QSlider::sub-page:horizontal {
    background: @accent;
    border-radius: 3px;
}

QSlider::groove:vertical {
    background: @bg-tertiary;
    width: 6px;
    border-radius: 3px;
    border: 1px solid @border;
}

QSlider::handle:vertical {
    background: @accent;
    width: 18px;
    height: 18px;
    margin: 0 -7px;
    border-radius: 9px;
}

QSlider::sub-page:vertical {
    background: @accent;
    border-radius: 3px;
}

/* CheckBox & RadioButton */
QCheckBox, QRadioButton {
    spacing: 8px;
    color: @fg-primary;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid @border;
    background: @bg-tertiary;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: @accent;
}

QCheckBox::indicator:checked {
    background: @accent;
    border-color: @accent;
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOSIgdmlld0JveD0iMCAwIDEyIDkiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0iTTEgNC41TDQuNSA4TDExIDEiIHN0cm9rZT0iIzFlMWUyZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=);
}

QRadioButton::indicator {
    border-radius: 9px;
}

QRadioButton::indicator:checked {
    background: @bg-tertiary;
    border-color: @accent;
}

QRadioButton::indicator:checked::after {
    content: "";
    display: block;
    width: 8px;
    height: 8px;
    margin: 3px;
    border-radius: 4px;
    background: @accent;
}

/* GroupBox */
QGroupBox {
    background-color: @bg-secondary;
    border: 1px solid @border;
    border-radius: 8px;
    margin-top: 16px;
    padding-top: 16px;
    font-weight: 600;
    color: @fg-primary;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: @accent;
    background-color: @bg-secondary;
}

/* TabWidget */
QTabWidget::pane {
    border: 1px solid @border;
    border-radius: 6px;
    background: @bg-secondary;
    top: -1px;
}

QTabBar::tab {
    background: @bg-tertiary;
    border: 1px solid @border;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 10px 20px;
    margin-right: 2px;
    color: @fg-secondary;
}

QTabBar::tab:selected {
    background: @bg-secondary;
    border-color: @border;
    color: @accent;
    border-bottom: 1px solid @bg-secondary;
}

QTabBar::tab:hover:!selected {
    background: @bg-hover;
    color: @fg-primary;
}

/* ScrollBar */
QScrollBar:vertical {
    background: @bg-secondary;
    width: 10px;
    border: none;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: @border;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: @fg-muted;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: @bg-secondary;
    height: 10px;
    border: none;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background: @border;
    border-radius: 5px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background: @fg-muted;
}

/* ListWidget / TreeWidget */
QListWidget, QTreeWidget, QTableWidget {
    background: @bg-secondary;
    border: 1px solid @border;
    border-radius: 6px;
    outline: none;
    alternate-background-color: @bg-tertiary;
}

QListWidget::item, QTreeWidget::item {
    padding: 8px 12px;
    border: none;
}

QListWidget::item:selected, QTreeWidget::item:selected {
    background: @accent;
    color: @bg-primary;
}

QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {
    background: @bg-hover;
}

QHeaderView::section {
    background: @bg-tertiary;
    border: none;
    border-bottom: 1px solid @border;
    padding: 8px 12px;
    font-weight: 600;
    color: @fg-secondary;
}

/* ProgressBar */
QProgressBar {
    background: @bg-tertiary;
    border: 1px solid @border;
    border-radius: 6px;
    text-align: center;
    color: @fg-primary;
    height: 20px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 @accent, stop:1 @accent-hover);
    border-radius: 5px;
}

/* ToolTip */
QToolTip {
    background: @bg-tertiary;
    border: 1px solid @border;
    border-radius: 6px;
    padding: 8px 12px;
    color: @fg-primary;
}

/* Menu */
QMenu {
    background: @bg-secondary;
    border: 1px solid @border;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
    color: @fg-primary;
}

QMenu::item:selected {
    background: @accent;
    color: @bg-primary;
}

QMenu::separator {
    height: 1px;
    background: @border;
    margin: 4px 8px;
}

/* DockWidget */
QDockWidget {
    titlebar-close-icon: url(close.png);
    titlebar-normal-icon: url(undock.png);
}

QDockWidget::title {
    background: @bg-secondary;
    padding: 8px 12px;
    border-bottom: 1px solid @border;
    font-weight: 600;
}

/* StatusBar */
QStatusBar {
    background: @bg-secondary;
    border-top: 1px solid @border;
    color: @fg-secondary;
}

/* Splitter */
QSplitter::handle {
    background: @border;
}

QSplitter::handle:horizontal {
    width: 2px;
}

QSplitter::handle:vertical {
    height: 2px;
}

QSplitter::handle:hover {
    background: @accent;
}
"""

def get_stylesheet() -> str:
    return DARK_QSS