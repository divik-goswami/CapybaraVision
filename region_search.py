"""System Tray Tool and Global Hotkey Listener for Capybara Vision.
Runs quietly in the background and activates the screen search overlay on hotkey.
"""

import sys
import threading
import subprocess
from pathlib import Path
from PIL import Image
import mss

from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox

import config
from capture_overlay import CaptureOverlay
from pynput import keyboard


def create_tray_icon() -> QIcon:
    """Load the Capybara Vision icon for the system tray."""
    candidates = []
    if getattr(sys, 'frozen', False):
        base_dir = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
        candidates.extend([
            base_dir / "assets" / "icon.png",
            base_dir / "icon.png",
            Path(sys.executable).parent / "assets" / "icon.png",
            Path(sys.executable).parent / "icon.png",
        ])

    script_dir = Path(__file__).resolve().parent
    candidates.extend([
        script_dir / "assets" / "icon.png",
        script_dir / "icon.png",
    ])

    for p in candidates:
        if p.exists():
            return QIcon(str(p))

    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(24, 24, 28))
    p.setPen(QPen(QColor(255, 255, 255, 180), 1.5))
    p.drawEllipse(2, 2, 28, 28)
    p.setPen(QPen(QColor(255, 255, 255), 2))
    p.drawEllipse(8, 8, 11, 11)
    p.drawLine(17, 17, 23, 23)
    p.end()
    return QIcon(pixmap)


class HotkeyBridge(QObject):
    """Bridge signal from background hotkey thread to Qt main thread."""
    trigger_capture = Signal()


class RegionSearchApp(QObject):
    """System tray manager and capture coordinator."""

    def __init__(self):
        super().__init__()
        self.cfg = config.load_config()
        self.bridge = HotkeyBridge()
        self.bridge.trigger_capture.connect(self.start_capture)
        self.active_overlay: CaptureOverlay = None
        self.hotkey_listener: keyboard.GlobalHotKeys = None

        self.setup_tray()
        self.setup_hotkey()

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(create_tray_icon())
        self.tray.setToolTip("Capybara Vision (Screen Search)")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #16161a;
                color: #ffffff;
                border: 1px solid #2a2a33;
                border-radius: 8px;
                padding: 6px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c2c36;
            }
        """)

        action_capture = QAction(f"Capture Region ({self.cfg.get('hotkey', 'Ctrl+Shift+S')})", self)
        action_capture.triggered.connect(self.start_capture)
        menu.addAction(action_capture)

        action_settings = QAction("Preferences...", self)
        action_settings.triggered.connect(self.open_settings)
        menu.addAction(action_settings)

        menu.addSeparator()

        action_quit = QAction("Exit", self)
        action_quit.triggered.connect(self.quit_app)
        menu.addAction(action_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.start_capture()

    def setup_hotkey(self):
        """Register the global hotkey using pynput."""
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass

        hotkey_str = self.cfg.get("hotkey", "<ctrl>+<shift>+s").lower()

        # Map common human readable hotkeys to pynput format if needed
        # e.g. "ctrl+shift+s" -> "<ctrl>+<shift>+s"
        formatted_hotkey = hotkey_str
        if not formatted_hotkey.startswith("<") and "+" in formatted_hotkey:
            parts = formatted_hotkey.split("+")
            formatted_hotkey = "+".join(f"<{p.strip()}>" if len(p.strip()) > 1 else p.strip() for p in parts)

        def on_triggered():
            self.bridge.trigger_capture.emit()

        try:
            hotkey_map = {formatted_hotkey: on_triggered}
            self.hotkey_listener = keyboard.GlobalHotKeys(hotkey_map)
            self.hotkey_listener.daemon = True
            self.hotkey_listener.start()
        except Exception as e:
            print(f"Failed to bind hotkey {formatted_hotkey}: {e}")

    def start_capture(self):
        """Freeze screen and show capture overlay."""
        if self.active_overlay is not None:
            # Already active
            return

        # Reload configuration
        self.cfg = config.load_config()

        # Capture virtual desktop across all monitors
        try:
            with mss.mss() as sct:
                # monitor 0 covers all monitors combined
                monitor = sct.monitors[0]
                sct_img = sct.grab(monitor)
                raw_img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            self.active_overlay = CaptureOverlay(raw_img, monitor)
            self.active_overlay.closed.connect(self.on_overlay_closed)
            self.active_overlay.show()
        except Exception as e:
            QMessageBox.critical(None, "Capture Error", f"Failed to grab screenshot: {str(e)}")

    def on_overlay_closed(self):
        self.active_overlay = None

    def open_settings(self):
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable])
        else:
            main_script = Path(__file__).parent / "main.py"
            if main_script.exists():
                subprocess.Popen([sys.executable, str(main_script)])
            else:
                script = Path(__file__).parent / "settings_app.py"
                subprocess.Popen([sys.executable, str(script)])

    def quit_app(self):
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
        QApplication.quit()


from PySide6.QtNetwork import QLocalServer, QLocalSocket

SINGLE_INSTANCE_IPC = "CapybaraVision_IPC_Server"


def main():
    # Set high DPI attributes
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")

    # 1. Single Instance Check: Mutex + Local Socket IPC
    import ctypes
    MUTEX_NAME = "CapybaraVision_SingleInstance_Mutex"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    is_already_running = (ctypes.windll.kernel32.GetLastError() == 183)  # ERROR_ALREADY_EXISTS

    test_socket = QLocalSocket()
    test_socket.connectToServer(SINGLE_INSTANCE_IPC)
    if test_socket.waitForConnected(400):
        # Existing instance found! Signal capture and exit
        test_socket.write(b"CAPTURE")
        test_socket.waitForBytesWritten(1000)
        test_socket.disconnectFromServer()
        sys.exit(0)
    elif is_already_running:
        sys.exit(0)

    app._single_instance_mutex = mutex

    # 2. Primary instance setup
    api_key = config.get_api_key()
    app_coordinator = RegionSearchApp()
    if not api_key:
        app_coordinator.tray.showMessage(
            "Capybara Vision Ready",
            "Tip: Set your Capybara Vision API key in Preferences or press Ctrl+Shift+S to start.",
            QSystemTrayIcon.Information,
            4000
        )

    # Listen for duplicate launches
    QLocalServer.removeServer(SINGLE_INSTANCE_IPC)
    ipc_server = QLocalServer(app_coordinator)
    ipc_server.listen(SINGLE_INSTANCE_IPC)

    def on_ipc_connection():
        client = ipc_server.nextPendingConnection()
        if client:
            client.waitForReadyRead(500)
            msg = bytes(client.readAll()).decode("utf-8", errors="ignore").strip()
            if msg == "CAPTURE":
                app_coordinator.start_capture()
            elif msg == "SHOW":
                app_coordinator.open_settings()
            client.disconnectFromServer()

    ipc_server.newConnection.connect(on_ipc_connection)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
