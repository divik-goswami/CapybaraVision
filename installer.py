"""Capybara Vision — Modern Windows Binary Installer
Provides an elegant dark-themed wizard that installs Capybara Vision,
creates Desktop and Start Menu shortcuts, and registers in Windows Add/Remove Programs.
"""

import os
import sys
import time
import shutil
import winreg
import tempfile
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QRect
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QLineEdit, QCheckBox,
    QProgressBar, QFileDialog, QMessageBox, QFrame
)

APP_NAME = "Capybara Vision"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "Capybara Vision"
DEFAULT_INSTALL_SUBDIR = Path("Programs") / "CapybaraVision"


def get_bundle_dir() -> Path:
    """Return the base directory for bundled files."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def get_app_icon() -> QIcon:
    """Load the Capybara icon."""
    base = get_bundle_dir()
    for candidate in [base / "assets" / "icon.png", base / "icon.png"]:
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


def create_windows_shortcut(target_exe: str, lnk_path: str, icon_path: str = "", work_dir: str = "", desc: str = ""):
    """Create a Windows .lnk shortcut safely via PowerShell COM object without temporary script files."""
    target_exe = str(Path(target_exe).resolve())
    lnk_path = str(Path(lnk_path).resolve())
    work_dir = str(Path(work_dir).resolve() if work_dir else Path(target_exe).parent)
    icon_path = str(Path(icon_path).resolve()) if icon_path else ""

    ps_cmd = (
        "$ws = New-Object -COM WScript.Shell; "
        "$s = $ws.CreateShortcut($env:SHORTCUT_LNK); "
        "$s.TargetPath = $env:SHORTCUT_TARGET; "
        "$s.WorkingDirectory = $env:SHORTCUT_WORKDIR; "
        "if ($env:SHORTCUT_ICON) { $s.IconLocation = $env:SHORTCUT_ICON }; "
        "if ($env:SHORTCUT_DESC) { $s.Description = $env:SHORTCUT_DESC }; "
        "$s.Save()"
    )
    env = os.environ.copy()
    env["SHORTCUT_LNK"] = lnk_path
    env["SHORTCUT_TARGET"] = target_exe
    env["SHORTCUT_WORKDIR"] = work_dir
    env["SHORTCUT_ICON"] = icon_path
    env["SHORTCUT_DESC"] = desc

    ps_exe = shutil.which("powershell") or os.path.expandvars(r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
    subprocess.run(
        [ps_exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
        env=env,
        check=True,
        capture_output=True
    )


class InstallWorker(QThread):
    """Background worker that copies files and sets up system shortcuts."""
    progress = Signal(int, str)
    finished_success = Signal()
    failed = Signal(str)

    def __init__(self, dest_dir: Path, create_desktop: bool, create_startmenu: bool, autostart: bool):
        super().__init__()
        self.dest_dir = dest_dir
        self.create_desktop = create_desktop
        self.create_startmenu = create_startmenu
        self.autostart = autostart

    def run(self):
        try:
            bundle_dir = get_bundle_dir()
            self.progress.emit(10, "Preparing installation folder...")
            self.dest_dir.mkdir(parents=True, exist_ok=True)
            (self.dest_dir / "assets").mkdir(parents=True, exist_ok=True)
            time.sleep(0.3)

            # 1. Copy main executable
            self.progress.emit(25, "Copying CapybaraVision.exe...")
            exe_src = bundle_dir / "CapybaraVision.exe"
            if not exe_src.exists():
                exe_src = bundle_dir / "CAPI_Search.exe"
            if not exe_src.exists():
                raise FileNotFoundError("CapybaraVision.exe not found in installer package.")

            dest_exe = self.dest_dir / "CapybaraVision.exe"
            shutil.copy2(exe_src, dest_exe)
            time.sleep(0.3)

            # 2. Copy icons and assets
            self.progress.emit(45, "Copying application assets and icons...")
            for icon_name in ["icon.ico", "icon.png"]:
                src_icon = bundle_dir / "assets" / icon_name
                if not src_icon.exists():
                    src_icon = bundle_dir / icon_name
                if src_icon.exists():
                    shutil.copy2(src_icon, self.dest_dir / "assets" / icon_name)
                    shutil.copy2(src_icon, self.dest_dir / icon_name)

            # Copy README if present
            readme = bundle_dir / "README.md"
            if readme.exists():
                shutil.copy2(readme, self.dest_dir / "README.md")
            time.sleep(0.3)

            # 3. Create Desktop shortcut
            dest_ico = self.dest_dir / "assets" / "icon.ico"
            if not dest_ico.exists():
                dest_ico = self.dest_dir / "icon.ico"
            if not dest_ico.exists():
                dest_ico = dest_exe

            if self.create_desktop:
                self.progress.emit(60, "Creating Desktop shortcut...")
                desktop_dir = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
                lnk_file = desktop_dir / "Capybara Vision.lnk"
                create_windows_shortcut(
                    target_exe=str(dest_exe),
                    lnk_path=str(lnk_file),
                    icon_path=str(dest_ico),
                    desc="Capybara Vision - Screen AI Search"
                )
                time.sleep(0.2)

            # 4. Create Start Menu shortcut
            if self.create_startmenu:
                self.progress.emit(75, "Creating Start Menu shortcut...")
                start_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                start_dir.mkdir(parents=True, exist_ok=True)
                lnk_file = start_dir / "Capybara Vision.lnk"
                create_windows_shortcut(
                    target_exe=str(dest_exe),
                    lnk_path=str(lnk_file),
                    icon_path=str(dest_ico),
                    desc="Capybara Vision - Screen AI Search"
                )
                time.sleep(0.2)

            # 5. Create uninstaller script
            self.progress.emit(85, "Creating uninstaller...")
            uninstall_bat = self.dest_dir / "uninstall.bat"
            uninst_content = f'''@echo off
setlocal
echo Uninstalling Capybara Vision...
taskkill /f /im CapybaraVision.exe >nul 2>&1
taskkill /f /im CAPI_Search.exe >nul 2>&1

set "DESKTOP_LNK=%USERPROFILE%\\Desktop\\Capybara Vision.lnk"
if exist "%DESKTOP_LNK%" del /f /q "%DESKTOP_LNK%"

set "START_LNK=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Capybara Vision.lnk"
if exist "%START_LNK%" del /f /q "%START_LNK%"

reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\CapybaraVision" /f >nul 2>&1
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "CAPIVision" /f >nul 2>&1
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "CAPISearch" /f >nul 2>&1

set "INSTALL_DIR=%~dp0"
if "%INSTALL_DIR:~-1%"=="\\" set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"

:: Safety verification: ensure we are in a valid CapybaraVision folder before recursive deletion
if exist "%INSTALL_DIR%\\CapybaraVision.exe" (
    cd ..
    start "" cmd /c "timeout /t 1 /nobreak >nul & rd /s /q \\"%INSTALL_DIR%\\""
) else if exist "%INSTALL_DIR%\\uninstall.bat" (
    cd ..
    start "" cmd /c "timeout /t 1 /nobreak >nul & rd /s /q \\"%INSTALL_DIR%\\""
)
echo Capybara Vision has been completely removed.
'''
            uninstall_bat.write_text(uninst_content, encoding="utf-8")

            # 6. Register in Windows Add/Remove Programs
            self.progress.emit(90, "Registering application in Windows...")
            uninst_reg_key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CapybaraVision"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, uninst_reg_key) as k:
                winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
                winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
                winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
                winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, str(dest_ico))
                winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, str(self.dest_dir))
                winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, f'cmd.exe /c "{uninstall_bat}"')
                winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, 65000)

            # Optional Windows Startup
            if self.autostart:
                run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as rk:
                    winreg.SetValueEx(rk, "CAPIVision", 0, winreg.REG_SZ, f'"{dest_exe}" --tray')

            self.progress.emit(100, "Installation complete!")
            time.sleep(0.4)
            self.finished_success.emit()
        except Exception as e:
            self.failed.emit(str(e))


class InstallerWindow(QMainWindow):
    """Multi-step installation wizard."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Capybara Vision Setup")
        self.setFixedSize(540, 420)
        self.setWindowIcon(get_app_icon())

        # Default path: %LOCALAPPDATA%\Programs\CapybaraVision
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        self.install_path = local_app_data / DEFAULT_INSTALL_SUBDIR

        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#CentralWidget {
                background-color: #121215;
                color: #e2e2e2;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel.Title {
                color: #ffffff;
                font-size: 19px;
                font-weight: 700;
            }
            QLabel.SubTitle {
                color: #9999a5;
                font-size: 12px;
            }
            QLabel.BodyText {
                color: #c5c5cf;
                font-size: 13px;
                line-height: 1.4;
            }
            QLineEdit {
                background-color: #1a1a20;
                border: 1px solid #2a2a35;
                border-radius: 6px;
                color: #ffffff;
                font-size: 12px;
                padding: 7px 10px;
            }
            QLineEdit:focus {
                border-color: #ffffff;
            }
            QCheckBox {
                color: #dddddd;
                font-size: 13px;
                spacing: 8px;
            }
            QPushButton.NavBtn {
                background-color: #202028;
                color: #ffffff;
                border: 1px solid #323242;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 8px 18px;
            }
            QPushButton.NavBtn:hover {
                background-color: #2a2a35;
                border-color: #454558;
            }
            QPushButton.PrimaryBtn {
                background-color: #ffffff;
                color: #000000;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 8px 22px;
            }
            QPushButton.PrimaryBtn:hover {
                background-color: #e2e2e2;
            }
            QPushButton.PrimaryBtn:pressed {
                background-color: #cccccc;
            }
            QProgressBar {
                background-color: #1a1a22;
                border: 1px solid #2c2c3a;
                border-radius: 6px;
                text-align: center;
                color: #ffffff;
                font-weight: 600;
                font-size: 11px;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #4ade80;
                border-radius: 5px;
            }
        """)

        central = QWidget(self)
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # Header with Logo & App Title
        header = QHBoxLayout()
        header.setSpacing(14)

        self.logo_label = QLabel(self)
        base = get_bundle_dir()
        icon_path = base / "assets" / "icon.png"
        if not icon_path.exists():
            icon_path = base / "icon.png"
        if icon_path.exists():
            pix = QPixmap(str(icon_path)).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(pix)
        header.addWidget(self.logo_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        lbl_head = QLabel("Capybara Vision Setup", self)
        lbl_head.setProperty("class", "Title")
        title_col.addWidget(lbl_head)

        lbl_sub = QLabel("Screen-Region Visual AI Search • Version 1.0.0", self)
        lbl_sub.setProperty("class", "SubTitle")
        title_col.addWidget(lbl_sub)
        header.addLayout(title_col)
        header.addStretch()

        main_layout.addLayout(header)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #23232c; border: 1px solid #23232c;")
        main_layout.addWidget(sep)

        # Wizard pages
        self.pages = QStackedWidget(self)
        self.build_page_welcome()
        self.build_page_options()
        self.build_page_installing()
        self.build_page_completed()
        main_layout.addWidget(self.pages)

        # Bottom Button Bar
        self.bottom_bar = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setProperty("class", "NavBtn")
        self.btn_cancel.clicked.connect(self.close)
        self.bottom_bar.addWidget(self.btn_cancel)

        self.bottom_bar.addStretch()

        self.btn_back = QPushButton("< Back", self)
        self.btn_back.setProperty("class", "NavBtn")
        self.btn_back.clicked.connect(self.go_back)
        self.bottom_bar.addWidget(self.btn_back)

        self.btn_next = QPushButton("Next >", self)
        self.btn_next.setProperty("class", "PrimaryBtn")
        self.btn_next.clicked.connect(self.go_next)
        self.bottom_bar.addWidget(self.btn_next)

        main_layout.addLayout(self.bottom_bar)

        self.update_nav_buttons()

    # PAGE 0: WELCOME
    def build_page_welcome(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        layout.setContentsMargins(6, 12, 6, 12)

        lbl_w1 = QLabel("Welcome to the Capybara Vision Setup Wizard", self)
        lbl_w1.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffffff;")
        layout.addWidget(lbl_w1)

        desc = (
            "Capybara Vision brings instant screen-region visual search to Windows.\n\n"
            "This installer will guide you through setting up Capybara Vision on your computer "
            "and create desktop and system tray shortcuts for immediate access.\n\n"
            "Click Next to choose your installation settings."
        )
        lbl_w2 = QLabel(desc, self)
        lbl_w2.setProperty("class", "BodyText")
        lbl_w2.setWordWrap(True)
        layout.addWidget(lbl_w2)

        layout.addStretch()
        self.pages.addWidget(page)

    # PAGE 1: OPTIONS & DIRECTORY
    def build_page_options(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(6, 6, 6, 6)

        lbl_dir = QLabel("Destination Directory", self)
        lbl_dir.setStyleSheet("font-size: 13px; font-weight: 600; color: #ffffff;")
        layout.addWidget(lbl_dir)

        row_dir = QHBoxLayout()
        row_dir.setSpacing(8)
        self.txt_path = QLineEdit(str(self.install_path), self)
        row_dir.addWidget(self.txt_path)

        btn_browse = QPushButton("Browse...", self)
        btn_browse.setProperty("class", "NavBtn")
        btn_browse.clicked.connect(self.browse_directory)
        row_dir.addWidget(btn_browse)
        layout.addLayout(row_dir)

        lbl_space = QLabel("Space required: ~65 MB", self)
        lbl_space.setProperty("class", "SubTitle")
        layout.addWidget(lbl_space)

        layout.addSpacing(6)

        lbl_opt = QLabel("Shortcuts & Integration", self)
        lbl_opt.setStyleSheet("font-size: 13px; font-weight: 600; color: #ffffff;")
        layout.addWidget(lbl_opt)

        self.chk_desktop = QCheckBox("Create a Desktop Shortcut", self)
        self.chk_desktop.setChecked(True)
        layout.addWidget(self.chk_desktop)

        self.chk_startmenu = QCheckBox("Create a Start Menu Shortcut", self)
        self.chk_startmenu.setChecked(True)
        layout.addWidget(self.chk_startmenu)

        self.chk_autostart = QCheckBox("Start Capybara Vision automatically with Windows", self)
        self.chk_autostart.setChecked(True)
        layout.addWidget(self.chk_autostart)

        layout.addStretch()
        self.pages.addWidget(page)

    # PAGE 2: INSTALLING
    def build_page_installing(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        layout.setContentsMargins(6, 20, 6, 20)

        self.lbl_status = QLabel("Installing Capybara Vision...", self)
        self.lbl_status.setStyleSheet("font-size: 14px; font-weight: 600; color: #ffffff;")
        layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.lbl_detail = QLabel("Please wait while setup copies files...", self)
        self.lbl_detail.setProperty("class", "SubTitle")
        layout.addWidget(self.lbl_detail)

        layout.addStretch()
        self.pages.addWidget(page)

    # PAGE 3: COMPLETED
    def build_page_completed(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        layout.setContentsMargins(6, 16, 6, 16)

        lbl_done = QLabel("Installation Complete!", self)
        lbl_done.setStyleSheet("font-size: 17px; font-weight: 700; color: #4ade80;")
        layout.addWidget(lbl_done)

        info = (
            "Capybara Vision has been successfully installed on your computer.\n\n"
            "A desktop shortcut has been created. You can use your global hotkey anytime "
            "to freeze the screen and query the visual AI."
        )
        lbl_info = QLabel(info, self)
        lbl_info.setProperty("class", "BodyText")
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        self.chk_launch = QCheckBox("Launch Capybara Vision now", self)
        self.chk_launch.setChecked(True)
        layout.addWidget(self.chk_launch)

        layout.addStretch()
        self.pages.addWidget(page)

    def browse_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Installation Folder", self.txt_path.text())
        if folder:
            self.txt_path.setText(folder)

    def update_nav_buttons(self):
        idx = self.pages.currentIndex()
        if idx == 0:
            self.btn_back.setVisible(False)
            self.btn_cancel.setVisible(True)
            self.btn_next.setText("Next >")
        elif idx == 1:
            self.btn_back.setVisible(True)
            self.btn_cancel.setVisible(True)
            self.btn_next.setText("Install")
        elif idx == 2:
            self.btn_back.setVisible(False)
            self.btn_cancel.setVisible(False)
            self.btn_next.setVisible(False)
        elif idx == 3:
            self.btn_back.setVisible(False)
            self.btn_cancel.setVisible(False)
            self.btn_next.setVisible(True)
            self.btn_next.setText("Finish")

    def go_back(self):
        cur = self.pages.currentIndex()
        if cur > 0:
            self.pages.setCurrentIndex(cur - 1)
            self.update_nav_buttons()

    def go_next(self):
        cur = self.pages.currentIndex()
        if cur == 0:
            self.pages.setCurrentIndex(1)
            self.update_nav_buttons()
        elif cur == 1:
            self.start_installation()
        elif cur == 3:
            # Finish
            if self.chk_launch.isChecked():
                exe_path = Path(self.txt_path.text().strip()) / "CapybaraVision.exe"
                if exe_path.exists():
                    subprocess.Popen([str(exe_path)])
            self.close()

    def start_installation(self):
        raw_path = self.txt_path.text().strip()
        if not raw_path:
            QMessageBox.warning(self, "Invalid Path", "Please provide a valid installation folder path.")
            return

        dest = Path(raw_path).resolve()
        # Prevent installing directly to filesystem root or user profile root
        user_home = Path(os.environ.get("USERPROFILE", Path.home())).resolve()
        if dest == dest.parent or dest == user_home or str(dest).lower() in ("c:\\", "c:", "d:\\", "d:"):
            QMessageBox.warning(
                self,
                "Unsafe Installation Directory",
                "Installing directly into a drive root or user home directory is not allowed for safety.\n\n"
                "Please choose a dedicated subfolder (such as Programs\\CapybaraVision)."
            )
            return

        self.pages.setCurrentIndex(2)
        self.update_nav_buttons()

        self.worker = InstallWorker(
            dest_dir=dest,
            create_desktop=self.chk_desktop.isChecked(),
            create_startmenu=self.chk_startmenu.isChecked(),
            autostart=self.chk_autostart.isChecked()
        )
        self.worker.progress.connect(self.on_install_progress)
        self.worker.finished_success.connect(self.on_install_success)
        self.worker.failed.connect(self.on_install_failed)
        self.worker.start()

    def on_install_progress(self, val: int, message: str):
        self.progress_bar.setValue(val)
        self.lbl_detail.setText(message)

    def on_install_success(self):
        self.pages.setCurrentIndex(3)
        self.update_nav_buttons()

    def on_install_failed(self, err_msg: str):
        QMessageBox.critical(self, "Installation Failed", f"An error occurred during installation:\n{err_msg}")
        self.pages.setCurrentIndex(1)
        self.update_nav_buttons()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = InstallerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
