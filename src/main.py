from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer, QLocalServer, QLocalSocket
import sys
import signal
import logging
from pathlib import Path
import os

from .gui.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Socket server for inter-instance communication
SOCKET_NAME = "ds4linux-socket"


class InstanceChecker:
    """Manages single-instance and inter-instance communication."""
    
    def __init__(self):
        self._server: QLocalServer = None
        self._is_first_instance = False
        self._socket_path = self._get_socket_path()
    
    def _get_socket_path(self) -> str:
        """Get the socket path for this instance."""
        if sys.platform == "win32":
            return f"\\\\.\\pipe\\{SOCKET_NAME}"
        else:
            path = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / f"ds4linux-{os.getuid()}.sock"
            return str(path)
    
    def start(self) -> bool:
        """Start the instance checker.
        
        Returns True if this is the first instance (should show window).
        Returns False if another instance is already running.
        """
        self._server = QLocalServer()
        
        # Remove stale socket from previous crash
        try:
            if os.path.exists(self._socket_path):
                os.remove(self._socket_path)
        except Exception:
            pass
        
        # Try to listen on the socket
        if not self._server.listen(SOCKET_NAME):
            # Another instance is running - signal it to show and exit
            self._signal_existing_instance()
            return False
        
        self._is_first_instance = True
        self._server.newConnection.connect(self._on_new_connection)
        logger.info("First instance started, listening for commands")
        return True
    
    def _signal_existing_instance(self):
        """Send show signal to existing instance."""
        socket = QLocalSocket()
        socket.connectToServer(SOCKET_NAME)
        if socket.waitForConnected(1000):
            socket.write(b"SHOW\n")
            socket.waitForBytesWritten(500)
            socket.close()
            logger.info("Sent SHOW signal to existing instance")
    
    def _on_new_connection(self):
        """Handle incoming connection from another instance."""
        socket = self._server.nextPendingConnection()
        socket.readyRead.connect(lambda: self._on_ready_read(socket))
    
    def _on_ready_read(self, socket: QLocalSocket):
        """Process incoming commands."""
        data = socket.readLine().data().decode().strip()
        if data == "SHOW":
            logger.info("Received SHOW command from another instance")
            # Emit signal to show window
            if hasattr(self, '_show_callback'):
                self._show_callback()
        socket.close()
    
    def get_window(self) -> MainWindow:
        """Get the main window instance."""
        return getattr(self, '_window', None)
    
    def set_window(self, window: MainWindow):
        """Set the main window instance."""
        self._window = window
        self._show_callback = window.show_normal
    

def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("DS4Linux")
    app.setApplicationVersion("1.3.0")
    app.setOrganizationName("DS4Linux")
    app.setOrganizationDomain("ds4linux.app")
    app.setQuitOnLastWindowClosed(False)

    # Check for single instance
    checker = InstanceChecker()
    if not checker.start():
        # Another instance is running
        print("DS4Linux is already running. Bringing existing window to focus.")
        return 0

    window = MainWindow()
    checker.set_window(window)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
