from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import sys
import signal
import logging
from pathlib import Path

from .gui.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("DS4Linux")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("DS4Linux")
    app.setOrganizationDomain("ds4linux.app")
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())