"""Qt stylesheet — modern flat dark theme with a teal accent.

Colors are defined once here so every widget stays consistent:
background #16161e · surface #1e1e2e · raised #262637 · border #33334d
text #d8dae5 · dim #8a8fa3 · accent #00d4aa · danger #ff5c7a
"""

ACCENT = "#00d4aa"
ACCENT_HOVER = "#00e8bb"
DANGER = "#ff5c7a"
BG = "#16161e"
SURFACE = "#1e1e2e"
RAISED = "#262637"
BORDER = "#33334d"
TEXT = "#d8dae5"
DIM = "#8a8fa3"


def get_stylesheet() -> str:
    return f"""
    * {{
        font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif;
    }}
    QWidget {{
        background-color: {BG};
        color: {TEXT};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{
        background-color: {BG};
    }}

    /* ---------- Tabs ---------- */
    QTabWidget::pane {{
        border: 1px solid {BORDER};
        border-radius: 8px;
        background: {SURFACE};
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {DIM};
        padding: 8px 16px;
        margin-right: 2px;
        border: 1px solid transparent;
        border-bottom: 2px solid transparent;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    QTabBar::tab:selected {{
        background: {SURFACE};
        color: {TEXT};
        border-color: {BORDER};
        border-bottom: 2px solid {ACCENT};
    }}
    QTabBar::tab:hover:!selected {{
        color: {TEXT};
        background: {RAISED};
    }}
    QTabWidget::tab-bar {{
        left: 4px;
    }}

    /* ---------- Buttons ---------- */
    QPushButton {{
        background-color: {RAISED};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 14px;
        color: {TEXT};
        min-height: 16px;
    }}
    QPushButton:hover {{
        background-color: #2f2f45;
        border-color: #454567;
    }}
    QPushButton:pressed {{
        background-color: #22223322;
    }}
    QPushButton:disabled {{
        color: #5a5f73;
        background-color: #1c1c29;
        border-color: #262637;
    }}
    QPushButton#primaryButton {{
        background-color: {ACCENT};
        border: 1px solid {ACCENT};
        color: #0d0d15;
        font-weight: bold;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {ACCENT_HOVER};
        border-color: {ACCENT_HOVER};
    }}
    QPushButton#dangerButton {{
        background-color: transparent;
        border: 1px solid {DANGER};
        color: {DANGER};
    }}
    QPushButton#dangerButton:hover {{
        background-color: {DANGER};
        color: #0d0d15;
    }}

    /* ---------- Inputs ---------- */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {RAISED};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 5px 8px;
        selection-background-color: {ACCENT};
        selection-color: #0d0d15;
        min-height: 16px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {DIM};
        margin-right: 6px;
    }}
    QComboBox QAbstractItemView {{
        background: {RAISED};
        border: 1px solid {BORDER};
        border-radius: 6px;
        selection-background-color: {ACCENT};
        selection-color: #0d0d15;
        outline: none;
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background: {BORDER};
        border: none;
        width: 16px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
        background: {ACCENT};
    }}

    /* ---------- Group boxes ---------- */
    QGroupBox {{
        border: 1px solid {BORDER};
        border-radius: 8px;
        margin-top: 14px;
        padding: 10px 10px 6px 10px;
        background: {SURFACE};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        top: 0px;
        padding: 0 6px;
        color: {ACCENT};
        font-weight: bold;
        background: {BG};
    }}

    /* ---------- Lists & tables ---------- */
    QListWidget, QTableWidget, QTreeWidget {{
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 8px;
        outline: none;
        alternate-background-color: #202031;
    }}
    QListWidget::item {{
        padding: 7px 10px;
        border-radius: 6px;
        color: {TEXT};
    }}
    QListWidget::item:selected {{
        background-color: {ACCENT};
        color: #0d0d15;
    }}
    QListWidget::item:hover:!selected {{
        background-color: {RAISED};
    }}
    QTableWidget::item {{
        padding: 6px 8px;
    }}
    QTableWidget::item:selected {{
        background-color: {ACCENT};
        color: #0d0d15;
    }}
    QHeaderView::section {{
        background-color: {RAISED};
        color: {DIM};
        padding: 7px 8px;
        border: none;
        border-bottom: 1px solid {BORDER};
        border-right: 1px solid {SURFACE};
        font-weight: bold;
    }}
    QTableCornerButton::section {{
        background-color: {RAISED};
        border: none;
    }}

    /* ---------- Scrollbars ---------- */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {ACCENT};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        height: 0;
        background: none;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {ACCENT};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        width: 0;
        background: none;
    }}

    /* ---------- Sliders & progress ---------- */
    QSlider::groove:horizontal {{
        height: 6px;
        background: {RAISED};
        border-radius: 3px;
    }}
    QSlider::sub-page:horizontal {{
        background: {ACCENT};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: #ffffff;
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }}
    QSlider::handle:horizontal:hover {{
        background: {ACCENT_HOVER};
    }}
    QProgressBar {{
        background-color: {RAISED};
        border: none;
        border-radius: 6px;
        min-height: 12px;
    }}
    QProgressBar::chunk {{
        background-color: {ACCENT};
        border-radius: 6px;
    }}

    /* ---------- Checkboxes ---------- */
    QCheckBox {{
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {BORDER};
        border-radius: 4px;
        background: {RAISED};
    }}
    QCheckBox::indicator:hover {{
        border-color: {ACCENT};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}

    /* ---------- Labels & misc ---------- */
    QLabel#sectionTitle {{
        font-size: 14px;
        font-weight: bold;
        color: {TEXT};
    }}
    QLabel#columnHeader {{
        color: {ACCENT};
        font-weight: bold;
        padding-bottom: 2px;
    }}
    QLabel#dimLabel {{
        color: {DIM};
    }}
    QToolTip {{
        background-color: #10101a;
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 5px 8px;
    }}
    QStatusBar {{
        background: {SURFACE};
        color: {DIM};
        border-top: 1px solid {BORDER};
    }}
    QTextEdit, QPlainTextEdit {{
        background-color: #12121a;
        border: 1px solid {BORDER};
        border-radius: 8px;
        color: #b9c0d4;
        font-family: "JetBrains Mono", "Fira Code", monospace;
        font-size: 12px;
    }}
    QMenu {{
        background-color: {RAISED};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 18px;
        border-radius: 5px;
    }}
    QMenu::item:selected {{
        background-color: {ACCENT};
        color: #0d0d15;
    }}
    QSplitter::handle {{
        background: {BORDER};
    }}
    QSplitter::handle:horizontal {{
        width: 1px;
    }}
    """
