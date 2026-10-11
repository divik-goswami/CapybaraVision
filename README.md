# Capybara Vision

A Windows desktop tool that brings screen-region visual AI search to your desktop.

## Features

- **Region Selection Overlay** — Freeze screen, draw a selection, get AI-powered answers
- **Capybara Vision Integration** — Uses advanced AI vision models for multimodal screen understanding
- **Monochrome Aesthetic** — Grayscale frozen screen with animated gradient border (Capybara sweep animation)
- **Settings App** — Configure API key, hotkey, prompt, visual style, and more
- **System Tray** — Runs quietly in the background, triggered by hotkey (default: `Ctrl+Shift+S`)

## Installation & Quick Start

### Option 1: Full Windows Installer (Recommended)
Double-click **`CapybaraVision_Setup.exe`**.
- Installs Capybara Vision to your system (`%LOCALAPPDATA%\Programs\CapybaraVision`).
- Automatically creates a **Desktop shortcut** with the custom Capybara icon.
- Adds **Start Menu** shortcuts and registers in Windows **Add/Remove Programs**.
- Includes complete uninstaller (`uninstall.bat`).

### Option 2: Portable Standalone App
Double-click **`CapybaraVision.exe`** (or `CAPI_Search.exe`).
- **⛶ Capture Screen Region**: Click the button directly to start selecting.
- **Global Hotkey**: Press `Ctrl+Shift+S` anywhere, anytime.
- **Settings & API Key**: Configure Capybara Vision API key, model, prompt, and visual style.
- **Background Mode**: Minimizes to system tray quietly with custom Capybara icon.

### Option 3: Run with Python
1. Install requirements: `pip install -r requirements.txt`
2. Run `python main.py` or double-click `Run_CapybaraVision.bat` / `Settings.bat`

## Tech Stack

- **PySide6 (Qt)** — Smooth gradients, glows, and animations
- **mss** — Multi-monitor, DPI-aware screenshots
- **AI Vision Engine** — High-performance multimodal models for screen analysis
