"""Capybara Vision — Standalone Windows App
Clean, compact dark interface with low-level Windows key recording,
API key management, automatic startup, and persistent background tray.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal, QTimer, QThread
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen, QAction, QGuiApplication
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QMessageBox, QSystemTrayIcon, QMenu, QGroupBox
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SINGLE_INSTANCE_IPC = "CapybaraVision_IPC_Server"

import config
from gemini_client import test_api_key
from capture_overlay import CaptureOverlay
from pynput import keyboard
from pynput.keyboard import Key, KeyCode


def create_app_icon() -> QIcon:
    """Load the Capybara Vision app icon from assets or fallback."""
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
    p.setBrush(QColor(22, 22, 26))
    p.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
    p.drawEllipse(2, 2, 28, 28)
    p.setPen(QPen(QColor(255, 255, 255), 2))
    p.drawEllipse(8, 8, 10, 10)
    p.drawLine(16, 16, 22, 22)
    p.end()
    return QIcon(pixmap)


def grab_virtual_desktop():
    """Grab all monitors seamlessly via Qt and return a unified QPixmap and bbox dict."""
    screens = QGuiApplication.screens()
    if not screens:
        primary = QGuiApplication.primaryScreen()
        if primary:
            pm = primary.grabWindow(0)
            geom = primary.geometry()
            return pm, {"left": geom.x(), "top": geom.y(), "width": geom.width(), "height": geom.height()}
        return None, None

    min_x = min(s.geometry().x() for s in screens)
    min_y = min(s.geometry().y() for s in screens)
    max_x = max(s.geometry().x() + s.geometry().width() for s in screens)
    max_y = max(s.geometry().y() + s.geometry().height() for s in screens)
    total_w = max_x - min_x
    total_h = max_y - min_y

    full_pixmap = QPixmap(total_w, total_h)
    full_pixmap.fill(Qt.black)
    p = QPainter(full_pixmap)
    for s in screens:
        geom = s.geometry()
        pm = s.grabWindow(0)
        p.drawPixmap(geom.x() - min_x, geom.y() - min_y, pm)
    p.end()

    bbox = {
        "left": min_x,
        "top": min_y,
        "width": total_w,
        "height": total_h
    }
    return full_pixmap, bbox


def normalize_pynput_hotkey(hotkey_str: str) -> str:
    """Ensure all special keys and modifiers in the hotkey string are properly enclosed in <...> for pynput."""
    parts = hotkey_str.split("+")
    normalized = []
    for p in parts:
        p = p.strip()
        if p.startswith("<") and p.endswith(">"):
            name = p[1:-1].lower()
        else:
            name = p.lower()

        if name in (
            "ctrl", "control", "shift", "alt", "cmd", "win", "windows",
            "space", "enter", "return", "tab", "backspace", "esc", "escape",
            "delete", "insert", "home", "end", "page_up", "page_down",
            "up", "down", "left", "right"
        ) or (name.startswith("f") and name[1:].isdigit()) or len(name) > 1:
            if name in ("control", "ctrl"):
                normalized.append("<ctrl>")
            elif name in ("win", "windows", "cmd"):
                normalized.append("<cmd>")
            else:
                normalized.append(f"<{name}>")
        else:
            normalized.append(name)
    return "+".join(normalized)


class ShortcutCaptureThread(QThread):
    """Low-level Windows keyboard hook thread that captures any shortcut including the Windows key."""
    shortcut_detected = Signal(str, str)  # (display_format, pynput_format)
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.pressed_mods = set()
        self.listener = None
        self._running = True

    def run(self):
        def on_press(k):
            if not self._running:
                return False

            # Check modifier keys
            if k in (Key.cmd, Key.cmd_l, Key.cmd_r):
                self.pressed_mods.add("Win")
                return
            if k in (Key.ctrl, Key.ctrl_l, Key.ctrl_r):
                self.pressed_mods.add("Ctrl")
                return
            if k in (Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr):
                self.pressed_mods.add("Alt")
                return
            if k in (Key.shift, Key.shift_l, Key.shift_r):
                self.pressed_mods.add("Shift")
                return

            # Esc alone cancels
            if k == Key.esc and not self.pressed_mods:
                self.cancelled.emit()
                return False

            # Normal key pressed
            char = None
            if hasattr(k, "char") and k.char:
                char = k.char.upper()
            elif hasattr(k, "name") and k.name:
                char = k.name.upper()

            if char:
                # Need at least one modifier, or an F1-F12 function key
                if self.pressed_mods or char.startswith("F"):
                    order = ["Win", "Ctrl", "Alt", "Shift"]
                    mods_display = [m for m in order if m in self.pressed_mods]
                    display_str = "+".join(mods_display + [char])

                    pynput_map = {"Win": "<cmd>", "Ctrl": "<ctrl>", "Alt": "<alt>", "Shift": "<shift>"}
                    pynput_mods = [pynput_map[m] for m in order if m in self.pressed_mods]
                    if char.startswith("F") or len(char) > 1:
                        pynput_str = "+".join(pynput_mods + [f"<{char.lower()}>"])
                    else:
                        pynput_str = "+".join(pynput_mods + [char.lower()])

                    pynput_str = normalize_pynput_hotkey(pynput_str)
                    self.shortcut_detected.emit(display_str, pynput_str)
                    return False

        def on_release(k):
            if k in (Key.cmd, Key.cmd_l, Key.cmd_r):
                self.pressed_mods.discard("Win")
            elif k in (Key.ctrl, Key.ctrl_l, Key.ctrl_r):
                self.pressed_mods.discard("Ctrl")
            elif k in (Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr):
                self.pressed_mods.discard("Alt")
            elif k in (Key.shift, Key.shift_l, Key.shift_r):
                self.pressed_mods.discard("Shift")

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            self.listener = listener
            listener.join()

    def stop(self):
        self._running = False
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass


class HotkeyBridge(QObject):
    trigger = Signal()


class MainWindow(QMainWindow):
    def __init__(self, start_minimized=False):
        super().__init__()
        self.cfg = config.load_config()
        self.active_overlay = None
        self.was_gui_initiated = False
        self.hotkey_listener = None
        self.record_thread = None

        self.bridge = HotkeyBridge()
        self.bridge.trigger.connect(self.on_hotkey_triggered)

        # Enforce startup settings
        if self.cfg.get("start_with_windows", True):
            config.configure_windows_startup(True)

        self.setWindowTitle("Capybara Vision")
        self.setFixedSize(390, 480)
        self.setWindowIcon(create_app_icon())

        self.setup_ui()
        self.setup_tray()
        self.setup_hotkey()

        if not start_minimized:
            self.show()

    def setup_ui(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#CentralWidget {
                background-color: #121215;
                color: #e2e2e2;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton#CaptureBtn {
                background-color: #ffffff;
                color: #000000;
                border: none;
                border-radius: 9px;
                font-size: 13px;
                font-weight: 700;
                padding: 12px 18px;
            }
            QPushButton#CaptureBtn:hover {
                background-color: #e2e2e2;
            }
            QPushButton#CaptureBtn:pressed {
                background-color: #cccccc;
            }
            QGroupBox {
                background-color: #17171c;
                border: 1px solid #25252e;
                border-radius: 8px;
                margin-top: 14px;
                padding: 10px 10px 10px 10px;
                font-size: 11px;
                font-weight: 600;
                color: #888892;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #aaaaaa;
            }
            QLabel {
                color: #bbbbbb;
                font-size: 12px;
            }
            QLabel.SubText {
                color: #666672;
                font-size: 11px;
            }
            QLineEdit, QComboBox {
                background-color: #1e1e24;
                border: 1px solid #2d2d38;
                border-radius: 6px;
                color: #ffffff;
                font-size: 12px;
                padding: 6px 9px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #ffffff;
            }
            QPushButton.ActionBtn {
                background-color: #212128;
                color: #ffffff;
                border: 1px solid #33333f;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
                padding: 7px 12px;
            }
            QPushButton.ActionBtn:hover {
                background-color: #2a2a35;
                border-color: #444455;
            }
            QPushButton#RecordBtn {
                background-color: #1e1e24;
                border: 1px solid #383848;
                border-radius: 6px;
                color: #ffffff;
                font-size: 12px;
                font-weight: 700;
                padding: 8px 12px;
            }
            QPushButton#RecordBtn:hover {
                background-color: #262632;
                border-color: #55556a;
            }
            QCheckBox {
                color: #cccccc;
                font-size: 12px;
                spacing: 6px;
            }
        """)

        central = QWidget(self)
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. Main Action Button: Capture Now
        self.btn_capture = QPushButton("⛶   Capture Screen Region", self)
        self.btn_capture.setObjectName("CaptureBtn")
        self.btn_capture.setCursor(Qt.PointingHandCursor)
        self.btn_capture.clicked.connect(self.manual_capture)
        layout.addWidget(self.btn_capture)

        # 2. Hotkey Section with One-Click Recording Button
        box_hotkey = QGroupBox("SHORTCUT", self)
        l_hk = QVBoxLayout(box_hotkey)
        l_hk.setContentsMargins(10, 8, 10, 8)
        l_hk.setSpacing(6)

        initial_display = self.cfg.get("hotkey_display", "Ctrl+Shift+S")
        self.btn_record = QPushButton(f"Shortcut: {initial_display}  (Click to change)", self)
        self.btn_record.setObjectName("RecordBtn")
        self.btn_record.setCursor(Qt.PointingHandCursor)
        self.btn_record.clicked.connect(self.start_hotkey_recording)
        l_hk.addWidget(self.btn_record)

        lbl_hk_hint = QLabel("Supports Windows key combinations (e.g. Win+S, Win+Shift+S)", self)
        lbl_hk_hint.setProperty("class", "SubText")
        l_hk.addWidget(lbl_hk_hint)
        layout.addWidget(box_hotkey)

        # 3. Capybara Vision API Key Section
        box_gemini = QGroupBox("CAPYBARA VISION API", self)
        l_gem = QVBoxLayout(box_gemini)
        l_gem.setContentsMargins(10, 8, 10, 8)
        l_gem.setSpacing(8)

        # Key Input
        self.input_key = QLineEdit(self)
        self.input_key.setEchoMode(QLineEdit.Password)
        self.input_key.setText(config.get_api_key())
        self.input_key.setPlaceholderText("Paste Capybara Vision API Key (AIzaSy...)")
        l_gem.addWidget(self.input_key)

        # Buttons: "Set API Key" and "Test Key"
        row_key_btns = QHBoxLayout()
        row_key_btns.setSpacing(8)

        self.btn_set_key = QPushButton("Set API Key", self)
        self.btn_set_key.setProperty("class", "ActionBtn")
        self.btn_set_key.clicked.connect(self.save_api_key)
        row_key_btns.addWidget(self.btn_set_key)

        self.btn_test_key = QPushButton("Test Key", self)
        self.btn_test_key.setProperty("class", "ActionBtn")
        self.btn_test_key.clicked.connect(self.test_api)
        row_key_btns.addWidget(self.btn_test_key)
        l_gem.addLayout(row_key_btns)

        # Status & Model row
        row_model = QHBoxLayout()
        self.lbl_key_status = QLabel("")
        row_model.addWidget(self.lbl_key_status, 1)

        self.combo_model = QComboBox(self)
        default_models = ["gemini-3.8-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        curr_model = self.cfg.get("model", "gemini-3.8-flash")
        for m in default_models:
            self.combo_model.addItem(m)
        if curr_model not in default_models:
            self.combo_model.addItem(curr_model)
        self.combo_model.setCurrentText(curr_model)
        self.combo_model.currentTextChanged.connect(self.on_model_changed)
        row_model.addWidget(self.combo_model, 1)
        l_gem.addLayout(row_model)

        layout.addWidget(box_gemini)

        # 4. Preferences Section
        box_settings = QGroupBox("OPTIONS", self)
        l_set = QVBoxLayout(box_settings)
        l_set.setContentsMargins(10, 8, 10, 8)
        l_set.setSpacing(8)

        self.chk_startup = QCheckBox("Start automatically with Windows", self)
        self.chk_startup.setChecked(self.cfg.get("start_with_windows", True))
        self.chk_startup.toggled.connect(self.on_startup_toggled)
        l_set.addWidget(self.chk_startup)

        self.chk_glow = QCheckBox("Glow & shimmer visual animations", self)
        self.chk_glow.setChecked(self.cfg.get("glow_enabled", True))
        self.chk_glow.toggled.connect(self.on_glow_toggled)
        l_set.addWidget(self.chk_glow)

        layout.addWidget(box_settings)

        layout.addStretch()

        # 5. Bottom Info Bar
        bottom = QHBoxLayout()
        lbl_info = QLabel("Runs in background tray", self)
        lbl_info.setProperty("class", "SubText")
        bottom.addWidget(lbl_info)
        bottom.addStretch()

        btn_exit = QPushButton("Exit App", self)
        btn_exit.setProperty("class", "ActionBtn")
        btn_exit.clicked.connect(self.exit_app)
        bottom.addWidget(btn_exit)

        layout.addLayout(bottom)

    def start_hotkey_recording(self):
        """Start listening for keyboard combination including Windows key."""
        if self.record_thread and self.record_thread.isRunning():
            return

        # Temporarily pause background hotkey listener
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
                self.hotkey_listener = None
            except Exception:
                pass

        self.btn_record.setText("Listening... Press any keys (e.g. Win+S)")
        self.btn_record.setStyleSheet("border: 1px solid #4ade80; color: #4ade80; background-color: #192b20;")

        self.record_thread = ShortcutCaptureThread()
        self.record_thread.shortcut_detected.connect(self.on_shortcut_captured)
        self.record_thread.cancelled.connect(self.on_shortcut_cancelled)
        self.record_thread.start()

    def on_shortcut_captured(self, display_str: str, pynput_str: str):
        self.cfg["hotkey"] = pynput_str
        self.cfg["hotkey_display"] = display_str
        config.save_config(self.cfg)

        self.btn_record.setText(f"Shortcut: {display_str}  (Click to change)")
        self.btn_record.setStyleSheet("")
        self.setup_hotkey()

        self.lbl_key_status.setText(f"✓ Shortcut: {display_str}")
        self.lbl_key_status.setStyleSheet("color: #4ade80;")
        QTimer.singleShot(2500, lambda: self.lbl_key_status.setText(""))

    def on_shortcut_cancelled(self):
        current_display = self.cfg.get("hotkey_display", "Ctrl+Shift+S")
        self.btn_record.setText(f"Shortcut: {current_display}  (Click to change)")
        self.btn_record.setStyleSheet("")
        self.setup_hotkey()

    def save_api_key(self):
        key = self.input_key.text().strip()
        if not key:
            self.lbl_key_status.setText("Key is empty")
            self.lbl_key_status.setStyleSheet("color: #f87171;")
            return
        config.set_api_key(key)
        self.lbl_key_status.setText("✓ Key saved")
        self.lbl_key_status.setStyleSheet("color: #4ade80;")
        QTimer.singleShot(2500, lambda: self.lbl_key_status.setText(""))

    def test_api(self):
        key = self.input_key.text().strip()
        if not key:
            self.lbl_key_status.setText("Enter key first")
            self.lbl_key_status.setStyleSheet("color: #f87171;")
            return
        self.lbl_key_status.setText("Connecting...")
        self.lbl_key_status.setStyleSheet("color: #aaaaaa;")
        QApplication.processEvents()

        ok, msg, models = test_api_key(key)
        if ok:
            self.lbl_key_status.setText("✓ Connected")
            self.lbl_key_status.setStyleSheet("color: #4ade80;")
            config.set_api_key(key)
            self.combo_model.clear()
            self.combo_model.addItems(models)
            if "gemini-3.8-flash" in models:
                self.combo_model.setCurrentText("gemini-3.8-flash")
        else:
            self.lbl_key_status.setText("❌ Failed")
            self.lbl_key_status.setStyleSheet("color: #f87171;")
            QMessageBox.warning(self, "API Test Failed", msg)

    def on_model_changed(self, model_name: str):
        if model_name:
            self.cfg["model"] = model_name
            config.save_config(self.cfg)

    def on_startup_toggled(self, enabled: bool):
        self.cfg["start_with_windows"] = enabled
        config.save_config(self.cfg)
        config.configure_windows_startup(enabled)

    def on_glow_toggled(self, enabled: bool):
        self.cfg["glow_enabled"] = enabled
        config.save_config(self.cfg)

    def manual_capture(self):
        """User clicked the manual capture button in the GUI."""
        if self.active_overlay is not None and self.active_overlay.isVisible():
            return

        self.was_gui_initiated = True
        self.hide()
        QTimer.singleShot(180, self._perform_capture)

    def on_hotkey_triggered(self):
        """Global hotkey pressed."""
        if self.active_overlay is not None and self.active_overlay.isVisible():
            return

        # If window is currently open, remember to restore it
        self.was_gui_initiated = self.isVisible()
        if self.isVisible():
            self.hide()

        QTimer.singleShot(180, self._perform_capture)

    def _perform_capture(self):
        try:
            full_pixmap, bbox = grab_virtual_desktop()
            if full_pixmap is None or full_pixmap.isNull():
                raise RuntimeError("Failed to capture screen image.")

            self.active_overlay = CaptureOverlay(full_pixmap, bbox)
            self.active_overlay.closed.connect(self._on_overlay_closed)
            self.active_overlay.show()
            self.active_overlay.raise_()
            self.active_overlay.activateWindow()
        except Exception as e:
            if self.was_gui_initiated:
                self.showNormal()
            QMessageBox.critical(self, "Capture Error", f"Failed to take screenshot: {str(e)}")
            self.was_gui_initiated = False

    def _on_overlay_closed(self):
        self.active_overlay = None
        # Restore GUI interface if and only if it was open prior to capture!
        if self.was_gui_initiated:
            self.showNormal()
            self.activateWindow()
            self.raise_()
            self.was_gui_initiated = False

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(create_app_icon())
        self.tray.setToolTip("Capybara Vision")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background: #17171c; color: #fff; border: 1px solid #2a2a35; padding: 4px; border-radius: 6px; }
            QMenu::item { padding: 6px 18px; border-radius: 4px; font-size: 12px; }
            QMenu::item:selected { background: #282833; }
        """)

        a_capture = QAction("Capture Region", self)
        a_capture.triggered.connect(self.manual_capture)
        menu.addAction(a_capture)

        a_open = QAction("Open Capybara Vision", self)
        a_open.triggered.connect(self.open_from_tray)
        menu.addAction(a_open)

        menu.addSeparator()

        a_exit = QAction("Exit", self)
        a_exit.triggered.connect(self.exit_app)
        menu.addAction(a_exit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible():
                self.hide()
            else:
                self.open_from_tray()

    def open_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def setup_hotkey(self):
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
                self.hotkey_listener = None
            except Exception:
                pass

        raw_hotkey = self.cfg.get("hotkey", "<ctrl>+<shift>+s")
        hotkey_str = normalize_pynput_hotkey(raw_hotkey)

        def on_triggered():
            self.bridge.trigger.emit()

        try:
            self.hotkey_listener = keyboard.GlobalHotKeys({hotkey_str: on_triggered})
            self.hotkey_listener.daemon = True
            self.hotkey_listener.start()
        except Exception as e:
            print(f"Failed to bind hotkey '{hotkey_str}': {e}")
            try:
                self.hotkey_listener = keyboard.GlobalHotKeys({"<ctrl>+<shift>+s": on_triggered})
                self.hotkey_listener.daemon = True
                self.hotkey_listener.start()
            except Exception:
                pass

    def closeEvent(self, event):
        # Stop recording hook if user closes window while listening
        if self.record_thread and self.record_thread.isRunning():
            self.record_thread.stop()
            self.on_shortcut_cancelled()

        # Minimize to tray instead of quitting
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Capybara Vision",
            f"Running in tray. Press {self.cfg.get('hotkey_display', 'shortcut')} anytime to capture.",
            QSystemTrayIcon.Information,
            2000
        )

    def exit_app(self):
        if self.record_thread:
            self.record_thread.stop()
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
        QApplication.quit()


def main():
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
        # Existing instance found! Send wake-up command and exit immediately
        cmd = "TRAY" if "--tray" in sys.argv else "SHOW"
        test_socket.write(cmd.encode("utf-8"))
        test_socket.waitForBytesWritten(1000)
        test_socket.disconnectFromServer()
        sys.exit(0)
    elif is_already_running:
        # Another instance holds the mutex even if IPC socket was unresponsive
        sys.exit(0)

    # Retain mutex handle for lifetime of process
    app._single_instance_mutex = mutex

    # 2. Primary instance: Launch app window
    start_minimized = "--tray" in sys.argv
    win = MainWindow(start_minimized=start_minimized)

    # Start local server to listen for any subsequent launch attempts
    QLocalServer.removeServer(SINGLE_INSTANCE_IPC)
    ipc_server = QLocalServer(win)
    ipc_server.listen(SINGLE_INSTANCE_IPC)

    def on_ipc_connection():
        client = ipc_server.nextPendingConnection()
        if client:
            client.waitForReadyRead(500)
            msg = bytes(client.readAll()).decode("utf-8", errors="ignore").strip()
            if msg == "SHOW":
                win.open_from_tray()
            elif msg == "CAPTURE":
                win.manual_capture()
            client.disconnectFromServer()

    ipc_server.newConnection.connect(on_ipc_connection)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
