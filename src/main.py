import logging
import os
import signal
import sys
from pathlib import Path

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .constants import APP_VERSION
from .engine.system_checker import (
    _has_stored_password,
    auto_setup,
    needs_setup,
)
from .gui.main_window import MainWindow
from .gui.setup_dialog import SetupDialog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Socket server for inter-instance communication
SOCKET_NAME = f"ds4linux-socket-{os.getuid()}"


class InstanceChecker:
    """Manages single-instance and inter-instance communication."""

    def __init__(self):
        self._server: QLocalServer = None
        self._is_first_instance = False
        self._socket_path = self._get_socket_path()

    def _get_socket_path(self) -> str:
        if sys.platform == "win32":
            return f"\\\\.\\pipe\\{SOCKET_NAME}"
        else:
            import tempfile
            return str(Path(tempfile.gettempdir()) / SOCKET_NAME)

    def start(self) -> bool:
        self._server = QLocalServer()

        probe = QLocalSocket()
        probe.connectToServer(SOCKET_NAME)
        if probe.waitForConnected(500):
            probe.write(b"SHOW\n")
            probe.waitForBytesWritten(500)
            probe.close()
            logger.info("Another instance is running, sending SHOW signal")
            return False

        try:
            if os.path.exists(self._socket_path):
                os.remove(self._socket_path)
        except Exception:
            pass

        if not self._server.listen(SOCKET_NAME):
            logger.error("Failed to start instance server")
            return False

        self._is_first_instance = True
        self._server.newConnection.connect(self._on_new_connection)
        logger.info("First instance started, listening for commands")
        return True

    def _on_new_connection(self):
        socket = self._server.nextPendingConnection()
        socket.readyRead.connect(lambda: self._on_ready_read(socket))

    def _on_ready_read(self, socket: QLocalSocket):
        data = socket.readLine().data().decode().strip()
        if data == "SHOW":
            logger.info("Received SHOW command from another instance")
            if hasattr(self, '_show_callback'):
                self._show_callback()
        socket.close()

    def get_window(self) -> MainWindow:
        return getattr(self, '_window', None)

    def set_window(self, window: MainWindow):
        self._window = window
        self._show_callback = window.show_normal


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("DS4Linux")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("DS4Linux")
    app.setOrganizationDomain("ds4linux.app")
    app.setQuitOnLastWindowClosed(False)

    # Check for single instance
    checker = InstanceChecker()
    if not checker.start():
        print("DS4Linux is already running. Bringing existing window to focus.")
        return 0

    # Try automatic setup using stored password (no dialog if password exists)
    setup_needed = needs_setup()

    if setup_needed:
        if _has_stored_password():
            # Password exists — try auto-setup silently
            logger.info("Stored password found, running automatic setup...")
            ok, msgs = auto_setup()
            if ok:
                logger.info("Auto-setup succeeded")
            else:
                # Auto-setup failed — show dialog to retry
                logger.warning("Auto-setup failed: %s", msgs)
                dlg = SetupDialog()
                dlg.exec()
        else:
            # No password stored — show setup dialog
            logger.info("No stored password, showing setup dialog...")
            dlg = SetupDialog()
            dlg.exec()

    window = MainWindow()
    checker.set_window(window)
    app.aboutToQuit.connect(window.cleanup)
    window.show()

    # Initial device scan — called directly after show() to avoid
    # race conditions with QTimer across threads
    from .engine.multi_device_manager import MultiDeviceManager
    MultiDeviceManager.scan_and_assign(window._multi_manager)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
