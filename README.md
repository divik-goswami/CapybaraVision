# 🦫 Capybara Vision

<p align="center">
  <strong>Instant Screen-Region Visual AI Search for Windows</strong><br>
  <em>Circle to Search / Android-style visual intelligence, right on your desktop.</em>
</p>

<p align="center">
  <img src="assets/icon.png" alt="Capybara Vision Logo" width="120" height="120" />
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue?logo=windows" alt="Platform" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" alt="Python Version" /></a>
  <a href="#"><img src="https://img.shields.io/badge/UI-PySide6%20%28Qt%29-green?logo=qt" alt="PySide6" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Security-Windows%20DPAPI-success?logo=windows" alt="Security" /></a>
  <a href="#"><img src="https://img.shields.io/badge/License-MIT-lightgrey" alt="License" /></a>
</p>

---

## ✨ Overview

**Capybara Vision** brings modern, intuitive visual AI search to Windows desktops. Freeze any part of your screen with a quick shortcut, drag to select an area (code snippet, chart, UI element, foreign text, or image), and instantly receive context-aware analysis, OCR translation, code debugging, or summaries powered by Google Gemini multimodal models.

---

## 🚀 Key Features

* **⛶ Instant Region Capture**: Freezes your virtual desktop across all connected monitors with a seamless monochrome backdrop and an animated glowing selection box.
* **🧠 Multimodal AI Vision Engine**: Directly queries Google Gemini models (`gemini-3.8-flash`, `gemini-2.5-flash`, etc.) for high-speed, high-accuracy screen comprehension.
* **💬 Conversational Follow-Ups**: Streaming markdown answer card anchored right next to your selection, allowing you to ask follow-up questions in natural language.
* **⌨️ Universal Shortcut Recording**: Low-level Windows keyboard hook supporting any shortcut combination—including the **Windows Key** (e.g. `Win+S`, `Win+Shift+S`, `Ctrl+Shift+S`).
* **🛡️ Hardened Security & Privacy**:
  * API keys are stored in **Windows Credential Manager** backed by **Windows DPAPI** (`CryptProtectData`) user-level encryption.
  * Zero plaintext token files on disk.
  * Direct client-to-API communication with zero third-party telemetry.
* **🪟 Persistent System Tray**: Runs quietly in the background without cluttering your taskbar.
* **📦 Standalone Installer & Portable App**: Available as a one-click standalone installer or zero-install portable `.exe`.

---

## 📥 Installation & Usage

### Option 1: Windows Installer (Recommended)
1. Download or run **`CapybaraVision_Setup.exe`**.
2. Follow the setup wizard to install Capybara Vision to your local profile (`%LOCALAPPDATA%\Programs\CapybaraVision`).
3. Launch from the **Desktop** shortcut or **Start Menu**.

### Option 2: Portable Standalone Executable
1. Run **`CapybaraVision.exe`**.
2. No installation required. Runs immediately and minimizes to your system tray.

### Option 3: Run from Source
1. Clone this repository:
   ```bash
   git clone https://github.com/divik-goswami/CapybaraVision.git
   cd CapybaraVision
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python main.py
   ```

---

## ⚙️ Configuration

Capybara Vision includes a full-featured Preferences panel to tailor your experience:

| Setting | Description |
| :--- | :--- |
| **API Key** | Securely save and test your Gemini API Key. |
| **Active Model** | Choose from dynamic Gemini models (default: `gemini-3.8-flash`). |
| **Global Shortcut** | Click to record any key combination (supports Windows key). |
| **Visual Aesthetics** | Adjust corner radius, border width, animated multi-pass glow, and dim opacity. |
| **Windows Startup** | Toggle whether Capybara Vision launches quietly with Windows. |

---

## 🛠️ Building from Source

To build standalone binaries and the installer locally, ensure PyInstaller is installed and run:

```bat
build.bat
```

This will automatically produce:
* `CapybaraVision.exe` — Standalone portable app (~58 MB)
* `CapybaraVision_Setup.exe` — Self-contained Windows installer wizard (~95 MB)

---

## 🔒 Security Architecture

* **Credential Protection**: Uses `keyring` (Windows Credential Manager) and falls back to Windows Data Protection API (DPAPI) binary encryption.
* **Safe External Links**: Links in AI responses are validated to allow only verified `http`/`https` schemes, blocking arbitrary local file or URI handler execution.
* **Prompt Injection Guardrails**: Strict system instructions prevent execution of malicious commands embedded inside analyzed screen images.

---

## 📄 License

This project is licensed under the MIT License.
