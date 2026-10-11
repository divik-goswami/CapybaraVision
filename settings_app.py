"""Settings GUI application for Capybara Vision.
Provides a 5-page black-and-white themed configuration interface.
"""

import sys
import winreg
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, QTimer, QVariantAnimation, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QConicalGradient, QFont, QIcon
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QListWidget, QListWidgetItem, QLabel, QLineEdit,
    QPushButton, QComboBox, QSlider, QCheckBox, QTextEdit,
    QMessageBox, QFrame, QRadioButton, QButtonGroup, QGraphicsDropShadowEffect
)

import config
from gemini_client import test_api_key

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "CAPIVision"


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

    return QIcon()


def set_startup(enable: bool):
    """Enable or disable auto-start with Windows via central config manager."""
    return config.configure_windows_startup(enable)


class PreviewWidget(QWidget):
    """Live interactive preview of the selection border and glow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(260, 160)
        self.angle = 0.0
        self.radius = 18
        self.border_w = 3
        self.glow_enabled = True

        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(360.0)
        self.anim.setDuration(2400)
        self.anim.setLoopCount(-1)
        self.anim.valueChanged.connect(self._on_angle)
        self.anim.start()

    def _on_angle(self, val):
        self.angle = val
        self.update()

    def update_params(self, radius: int, border_w: int, glow: bool, speed: float):
        self.radius = radius
        self.border_w = border_w
        self.glow_enabled = glow
        duration = int(2400 / max(0.2, speed))
        self.anim.setDuration(duration)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Background preview card
        p.fillRect(self.rect(), QColor(14, 14, 16))

        # Sample selection box in preview
        box = QRectF(30, 24, 200, 112)

        # Cutout simulation
        g = QConicalGradient(box.center(), self.angle)
        for pos, col in [(0.0, "#ffffff"), (0.35, "#555555"), (0.6, "#111111"), (0.8, "#bbbbbb"), (1.0, "#ffffff")]:
            g.setColorAt(pos, QColor(col))

        if self.glow_enabled:
            passes = [(14, 0.14), (8, 0.35), (self.border_w, 1.0)]
        else:
            passes = [(self.border_w, 1.0)]

        for w, alpha in passes:
            p.save()
            p.setOpacity(alpha)
            p.setPen(QPen(QBrush(g), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawRoundedRect(box, self.radius, self.radius)
            p.restore()

        # Text inside preview
        p.setPen(QColor(160, 160, 160))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(box, Qt.AlignCenter, "Selection Preview")


class SettingsWindow(QMainWindow):
    """Main Settings Application Window."""

    def __init__(self):
        super().__init__()
        self.cfg = config.load_config()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Capybara Vision — Preferences")
        self.setWindowIcon(create_app_icon())
        self.resize(760, 520)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0f0f11;
            }
            QWidget#CentralWidget {
                background-color: #0f0f11;
            }
            QListWidget#Sidebar {
                background-color: #151518;
                border: 1px solid #222226;
                border-radius: 12px;
                color: #888888;
                font-size: 13px;
                font-weight: 600;
                padding: 10px;
                outline: none;
            }
            QListWidget#Sidebar::item {
                padding: 12px 16px;
                border-radius: 8px;
                margin-bottom: 4px;
            }
            QListWidget#Sidebar::item:hover {
                background-color: #1f1f24;
                color: #ffffff;
            }
            QListWidget#Sidebar::item:selected {
                background-color: #2b2b33;
                color: #ffffff;
            }
            QLabel {
                color: #cccccc;
                font-size: 13px;
            }
            QLabel.SectionHeader {
                color: #ffffff;
                font-size: 18px;
                font-weight: 700;
                margin-bottom: 12px;
            }
            QLabel.SubHeader {
                color: #777777;
                font-size: 12px;
                margin-bottom: 16px;
            }
            QLineEdit, QTextEdit, QComboBox {
                background-color: #18181c;
                border: 1px solid #282830;
                border-radius: 8px;
                color: #ffffff;
                font-size: 13px;
                padding: 8px 12px;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
                border: 1px solid #ffffff;
            }
            QPushButton.PrimaryButton {
                background-color: #ffffff;
                color: #000000;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 9px 18px;
            }
            QPushButton.PrimaryButton:hover {
                background-color: #dddddd;
            }
            QPushButton.SecondaryButton {
                background-color: #202026;
                color: #ffffff;
                border: 1px solid #33333d;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                padding: 8px 16px;
            }
            QPushButton.SecondaryButton:hover {
                background-color: #2a2a33;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #25252b;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #ffffff;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QCheckBox, QRadioButton {
                color: #cccccc;
                font-size: 13px;
                spacing: 8px;
            }
        """)

        central = QWidget(self)
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(18)

        # Sidebar navigation
        self.sidebar = QListWidget(self)
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(190)
        self.sidebar.addItem("Capybara Vision API")
        self.sidebar.addItem("Capture")
        self.sidebar.addItem("Prompt")
        self.sidebar.addItem("Appearance")
        self.sidebar.addItem("General")
        self.sidebar.currentRowChanged.connect(self.on_page_change)
        main_layout.addWidget(self.sidebar)

        # Right side content area
        right_container = QVBoxLayout()
        right_container.setSpacing(14)

        self.pages = QStackedWidget(self)
        self.build_capi_page()
        self.build_capture_page()
        self.build_prompt_page()
        self.build_look_page()
        self.build_general_page()
        right_container.addWidget(self.pages)

        # Bottom Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        self.btn_save = QPushButton("Save Settings", self)
        self.btn_save.setProperty("class", "PrimaryButton")
        self.btn_save.clicked.connect(self.save_all)
        bottom_bar.addWidget(self.btn_save)

        right_container.addLayout(bottom_bar)
        main_layout.addLayout(right_container)

        self.sidebar.setCurrentRow(0)

    def on_page_change(self, idx: int):
        self.pages.setCurrentIndex(idx)

    # PAGE 1: CAPI API
    def build_capi_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        header = QLabel("Capybara Vision Configuration")
        header.setProperty("class", "SectionHeader")
        layout.addWidget(header)

        sub = QLabel("Configure your personal Capybara Vision API key and model selection.")
        sub.setProperty("class", "SubHeader")
        layout.addWidget(sub)

        layout.addWidget(QLabel("Capybara Vision API Key"))
        key_box = QHBoxLayout()
        self.input_key = QLineEdit(self)
        self.input_key.setEchoMode(QLineEdit.Password)
        self.input_key.setText(config.get_api_key())
        self.input_key.setPlaceholderText("Paste Capybara Vision API key (AIzaSy...)")
        key_box.addWidget(self.input_key)

        self.btn_toggle_key = QPushButton("Show", self)
        self.btn_toggle_key.setProperty("class", "SecondaryButton")
        self.btn_toggle_key.clicked.connect(self.toggle_key_visibility)
        key_box.addWidget(self.btn_toggle_key)
        layout.addLayout(key_box)

        test_row = QHBoxLayout()
        self.btn_test = QPushButton("Test Key & Fetch Models", self)
        self.btn_test.setProperty("class", "SecondaryButton")
        self.btn_test.clicked.connect(self.test_and_fetch_models)
        test_row.addWidget(self.btn_test)

        self.lbl_status = QLabel("")
        test_row.addWidget(self.lbl_status)
        test_row.addStretch()
        layout.addLayout(test_row)

        layout.addWidget(QLabel("Active Model"))
        self.combo_model = QComboBox(self)
        curr_model = self.cfg.get("model", "gemini-2.5-flash")
        self.combo_model.addItems(["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"])
        if curr_model in [self.combo_model.itemText(i) for i in range(self.combo_model.count())]:
            self.combo_model.setCurrentText(curr_model)
        else:
            self.combo_model.addItem(curr_model)
            self.combo_model.setCurrentText(curr_model)
        layout.addWidget(self.combo_model)

        layout.addStretch()
        self.pages.addWidget(page)

    def toggle_key_visibility(self):
        if self.input_key.echoMode() == QLineEdit.Password:
            self.input_key.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_key.setText("Hide")
        else:
            self.input_key.setEchoMode(QLineEdit.Password)
            self.btn_toggle_key.setText("Show")

    def test_and_fetch_models(self):
        key = self.input_key.text().strip()
        if not key:
            self.lbl_status.setText("❌ Please enter a key.")
            return

        self.lbl_status.setText("Testing connection...")
        QApplication.processEvents()
        ok, msg, models = test_api_key(key)
        if ok:
            self.lbl_status.setText("✓ Key verified!")
            self.lbl_status.setStyleSheet("color: #4ade80;")
            self.combo_model.clear()
            self.combo_model.addItems(models)
        else:
            self.lbl_status.setText("❌ " + msg[:40])
            self.lbl_status.setStyleSheet("color: #f87171;")

    # PAGE 2: CAPTURE
    def build_capture_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)

        header = QLabel("Capture & Hotkey")
        header.setProperty("class", "SectionHeader")
        layout.addWidget(header)

        sub = QLabel("Configure screen capture trigger and behavior.")
        sub.setProperty("class", "SubHeader")
        layout.addWidget(sub)

        layout.addWidget(QLabel("Global Hotkey"))
        self.input_hotkey = QLineEdit(self)
        self.input_hotkey.setText(self.cfg.get("hotkey", "<ctrl>+<shift>+s"))
        layout.addWidget(self.input_hotkey)

        layout.addWidget(QLabel("Capture Trigger Action"))
        self.radio_auto = QRadioButton("Analyze immediately on mouse release (Android style)", self)
        self.radio_prompt = QRadioButton("Show question input box before searching", self)

        if self.cfg.get("ask_mode", "auto") == "auto":
            self.radio_auto.setChecked(True)
        else:
            self.radio_prompt.setChecked(True)

        layout.addWidget(self.radio_auto)
        layout.addWidget(self.radio_prompt)

        layout.addStretch()
        self.pages.addWidget(page)

    # PAGE 3: PROMPT
    def build_prompt_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        header = QLabel("Prompt Engineering")
        header.setProperty("class", "SectionHeader")
        layout.addWidget(header)

        sub = QLabel("Customize default question and system instructions for Capybara Vision.")
        sub.setProperty("class", "SubHeader")
        layout.addWidget(sub)

        layout.addWidget(QLabel("Default Question"))
        self.input_default_prompt = QLineEdit(self)
        self.input_default_prompt.setText(self.cfg.get("default_prompt", "Explain what's in this region in detail."))
        layout.addWidget(self.input_default_prompt)

        layout.addWidget(QLabel("System Instruction"))
        self.input_sys_inst = QTextEdit(self)
        self.input_sys_inst.setPlainText(self.cfg.get("system_instruction", ""))
        self.input_sys_inst.setMaximumHeight(140)
        layout.addWidget(self.input_sys_inst)

        layout.addStretch()
        self.pages.addWidget(page)

    # PAGE 4: APPEARANCE
    def build_look_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(12)

        header = QLabel("Visual Appearance")
        header.setProperty("class", "SectionHeader")
        left.addWidget(header)

        # Radius
        lbl_r = QLabel(f"Corner Radius: {self.cfg.get('corner_radius', 18)}px")
        left.addWidget(lbl_r)
        self.slider_radius = QSlider(Qt.Horizontal)
        self.slider_radius.setRange(8, 36)
        self.slider_radius.setValue(self.cfg.get("corner_radius", 18))
        self.slider_radius.valueChanged.connect(lambda v: [lbl_r.setText(f"Corner Radius: {v}px"), self.update_live_preview()])
        left.addWidget(self.slider_radius)

        # Border width
        lbl_b = QLabel(f"Border Width: {self.cfg.get('border_width', 3)}px")
        left.addWidget(lbl_b)
        self.slider_border = QSlider(Qt.Horizontal)
        self.slider_border.setRange(1, 6)
        self.slider_border.setValue(self.cfg.get("border_width", 3))
        self.slider_border.valueChanged.connect(lambda v: [lbl_b.setText(f"Border Width: {v}px"), self.update_live_preview()])
        left.addWidget(self.slider_border)

        # Glow checkbox
        self.chk_glow = QCheckBox("Conical Multi-pass Glow Effect", self)
        self.chk_glow.setChecked(self.cfg.get("glow_enabled", True))
        self.chk_glow.toggled.connect(lambda _: self.update_live_preview())
        left.addWidget(self.chk_glow)

        # Dim opacity
        lbl_dim = QLabel(f"Screen Dimming: {int(self.cfg.get('dim_opacity', 0.65) * 100)}%")
        left.addWidget(lbl_dim)
        self.slider_dim = QSlider(Qt.Horizontal)
        self.slider_dim.setRange(20, 90)
        self.slider_dim.setValue(int(self.cfg.get("dim_opacity", 0.65) * 100))
        self.slider_dim.valueChanged.connect(lambda v: lbl_dim.setText(f"Screen Dimming: {v}%"))
        left.addWidget(self.slider_dim)

        left.addStretch()
        layout.addLayout(left)

        # Live Preview Panel
        right = QVBoxLayout()
        right.addWidget(QLabel("Live Effect Preview"))
        self.preview = PreviewWidget(self)
        right.addWidget(self.preview)
        right.addStretch()
        layout.addLayout(right)

        self.pages.addWidget(page)

    def update_live_preview(self):
        self.preview.update_params(
            radius=self.slider_radius.value(),
            border_w=self.slider_border.value(),
            glow=self.chk_glow.isChecked(),
            speed=self.cfg.get("animation_speed", 1.0)
        )

    # PAGE 5: GENERAL
    def build_general_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)

        header = QLabel("General Settings")
        header.setProperty("class", "SectionHeader")
        layout.addWidget(header)

        sub = QLabel("Application lifecycle and system integration.")
        sub.setProperty("class", "SubHeader")
        layout.addWidget(sub)

        self.chk_startup = QCheckBox("Start Capybara Vision automatically with Windows", self)
        self.chk_startup.setChecked(self.cfg.get("start_with_windows", False))
        layout.addWidget(self.chk_startup)

        btn_launch = QPushButton("Launch Capybara Vision Now", self)
        btn_launch.setProperty("class", "SecondaryButton")
        btn_launch.clicked.connect(self.launch_region_search)
        layout.addWidget(btn_launch)

        btn_reset = QPushButton("Reset All to Defaults", self)
        btn_reset.setProperty("class", "SecondaryButton")
        btn_reset.clicked.connect(self.reset_defaults)
        layout.addWidget(btn_reset)

        layout.addStretch()
        self.pages.addWidget(page)

    def launch_region_search(self):
        import subprocess
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable, "--tray"])
        else:
            main_path = Path(__file__).parent / "main.py"
            target = main_path if main_path.exists() else Path(__file__).parent / "region_search.py"
            subprocess.Popen([sys.executable, str(target), "--tray"])
        QMessageBox.information(self, "Launched", "Capybara Vision tray tool has been started in the background!")

    def reset_defaults(self):
        reply = QMessageBox.question(self, "Reset", "Reset all settings to original defaults?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.cfg = dict(config.DEFAULT_CONFIG)
            config.save_config(self.cfg)
            QMessageBox.information(self, "Reset", "Settings reset to defaults. Please restart the app.")

    def save_all(self):
        key = self.input_key.text().strip()
        if key:
            config.set_api_key(key)

        self.cfg["model"] = self.combo_model.currentText()
        self.cfg["hotkey"] = self.input_hotkey.text().strip()
        self.cfg["ask_mode"] = "auto" if self.radio_auto.isChecked() else "prompt"
        self.cfg["default_prompt"] = self.input_default_prompt.text().strip()
        self.cfg["system_instruction"] = self.input_sys_inst.toPlainText().strip()
        self.cfg["corner_radius"] = self.slider_radius.value()
        self.cfg["border_width"] = self.slider_border.value()
        self.cfg["glow_enabled"] = self.chk_glow.isChecked()
        self.cfg["dim_opacity"] = self.slider_dim.value() / 100.0
        self.cfg["start_with_windows"] = self.chk_startup.isChecked()

        config.save_config(self.cfg)
        set_startup(self.chk_startup.isChecked())

        QMessageBox.information(self, "Saved", "Preferences saved successfully!")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = SettingsWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
