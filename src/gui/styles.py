def get_stylesheet():
    return """
    QWidget {
        background-color: #1e1e1e;
        color: #cfcfcf;
        font-family: "Segoe UI", sans-serif;
        font-size: 13px;
    }
    QListWidget {
        background-color: #252526;
        border: none;
        outline: none;
        font-size: 14px;
    }
    QListWidget::item {
        padding: 12px;
        color: #cfcfcf;
    }
    QListWidget::item:selected {
        background-color: #37373d;
        border-left: 3px solid #007acc;
    }
    QPushButton {
        background-color: #3c3c3c;
        border: 1px solid #555;
        border-radius: 2px;
        padding: 5px 15px;
        color: #ffffff;
    }
    QPushButton:hover {
        background-color: #505050;
    }
    QTabWidget::pane {
        border: none;
        background: #1e1e1e;
    }
    QGroupBox {
        border: 1px solid #333;
        margin-top: 10px;
        padding-top: 10px;
        font-weight: bold;
    }
    """
