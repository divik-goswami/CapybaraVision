"""Screen-region capture overlay with monochrome aesthetic, conical glow animation,
and frosted glass answer panel for Capybara Vision search.
"""

import io
import sys
from pathlib import Path
from typing import Optional, List
from PIL import Image

from PySide6.QtCore import (
    Qt, QRect, QRectF, QPoint, QVariantAnimation, QSize, Signal,
    QByteArray, QBuffer, QIODevice
)
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QPixmap, QImage,
    QConicalGradient, QLinearGradient, QFont, QKeySequence, QShortcut,
    QCursor, QDesktopServices
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect, QFrame,
    QApplication, QScrollArea
)

import config
from gemini_client import GeminiStreamWorker


def convert_pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    """Convert PIL image to QPixmap."""
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


def convert_pil_to_grayscale_qpixmap(pil_img: Image.Image) -> QPixmap:
    """Convert PIL image to grayscale QPixmap."""
    gray_pil = pil_img.convert("L").convert("RGBA")
    data = gray_pil.tobytes("raw", "RGBA")
    qimg = QImage(data, gray_pil.width, gray_pil.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


class AnswerCard(QFrame):
    """Frosted dark card anchored next to the selection with streaming response and follow-up."""
    close_requested = Signal()
    followup_submitted = Signal(str)
    retry_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(460)
        self.setObjectName("AnswerCard")
        self.setStyleSheet("""
            QFrame#AnswerCard {
                background-color: rgba(18, 18, 20, 0.94);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 16px;
            }
            QLabel#TitleLabel {
                color: #ffffff;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            QLabel#StatusLabel {
                color: #888888;
                font-size: 11px;
            }
            QTextBrowser {
                background: transparent;
                border: none;
                color: #e2e2e2;
                font-size: 13px;
                line-height: 1.5;
            }
            QLineEdit#FollowUpInput {
                background-color: rgba(30, 30, 34, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 10px;
                color: #ffffff;
                font-size: 12px;
                padding: 8px 12px;
            }
            QLineEdit#FollowUpInput:focus {
                border: 1px solid rgba(255, 255, 255, 0.45);
                background-color: rgba(38, 38, 44, 0.95);
            }
            QPushButton.ActionButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                color: #cccccc;
                font-size: 11px;
                padding: 5px 10px;
                font-weight: 600;
            }
            QPushButton.ActionButton:hover {
                background-color: rgba(255, 255, 255, 0.18);
                color: #ffffff;
            }
            QPushButton#CloseButton {
                background: transparent;
                border: none;
                color: #888888;
                font-size: 14px;
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton#CloseButton:hover {
                color: #ffffff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header bar
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        # Capybara Avatar Icon
        icon_path = None
        if getattr(sys, 'frozen', False):
            base_dir = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
            for cand in [base_dir / "assets" / "icon.png", base_dir / "icon.png"]:
                if cand.exists():
                    icon_path = cand
                    break
        if not icon_path:
            script_dir = Path(__file__).resolve().parent
            for cand in [script_dir / "assets" / "icon.png", script_dir / "icon.png"]:
                if cand.exists():
                    icon_path = cand
                    break

        if icon_path:
            self.avatar_label = QLabel(self)
            pix = QPixmap(str(icon_path)).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.avatar_label.setPixmap(pix)
            header.addWidget(self.avatar_label)

        self.title_label = QLabel("CAPYBARA VISION", self)
        self.title_label.setObjectName("TitleLabel")
        header.addWidget(self.title_label)

        self.status_label = QLabel("Thinking...", self)
        self.status_label.setObjectName("StatusLabel")
        header.addWidget(self.status_label)
        header.addStretch()

        self.btn_copy = QPushButton("Copy", self)
        self.btn_copy.setObjectName("btn_copy")
        self.btn_copy.setProperty("class", "ActionButton")
        self.btn_copy.clicked.connect(self.copy_content)
        header.addWidget(self.btn_copy)

        self.btn_close = QPushButton("✕", self)
        self.btn_close.setObjectName("CloseButton")
        self.btn_close.clicked.connect(self.close_requested.emit)
        header.addWidget(self.btn_close)
        layout.addLayout(header)

        # Content text browser
        self.text_browser = QTextBrowser(self)
        self.text_browser.setOpenExternalLinks(False)
        self.text_browser.anchorClicked.connect(self.on_link_clicked)
        self.text_browser.setMinimumHeight(120)
        self.text_browser.setMaximumHeight(340)
        layout.addWidget(self.text_browser)

        # Follow up bar
        follow_bar = QHBoxLayout()
        follow_bar.setContentsMargins(0, 0, 0, 0)
        follow_bar.setSpacing(8)

        self.input_followup = QLineEdit(self)
        self.input_followup.setObjectName("FollowUpInput")
        self.input_followup.setPlaceholderText("Ask a follow-up question...")
        self.input_followup.returnPressed.connect(self.on_followup_submit)
        follow_bar.addWidget(self.input_followup)

        self.btn_send = QPushButton("Ask", self)
        self.btn_send.setProperty("class", "ActionButton")
        self.btn_send.clicked.connect(self.on_followup_submit)
        follow_bar.addWidget(self.btn_send)
        layout.addLayout(follow_bar)

        self.raw_text = ""

    def append_text(self, chunk: str):
        self.raw_text += chunk
        # Render as markdown
        self.text_browser.setMarkdown(self.raw_text)
        # Scroll to bottom
        sb = self.text_browser.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_content(self, text: str):
        self.raw_text = text
        self.text_browser.setMarkdown(text)

    def on_followup_submit(self):
        query = self.input_followup.text().strip()
        if query:
            self.input_followup.clear()
            self.followup_submitted.emit(query)

    def copy_content(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.raw_text)
        orig_text = self.btn_copy.text()
        self.btn_copy.setText("Copied!")
        self.btn_copy.setEnabled(False)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: [self.btn_copy.setText(orig_text), self.btn_copy.setEnabled(True)])

    def on_link_clicked(self, url):
        """Only allow verified http and https web links to open externally."""
        scheme = url.scheme().lower()
        if scheme in ("http", "https"):
            QDesktopServices.openUrl(url)
        else:
            # Block unsafe schemes like file:, ms-settings:, cmd:, etc.
            print(f"Blocked opening untrusted URL scheme: {scheme}")


class CaptureOverlay(QWidget):
    """Full-screen interactive region selection overlay with animated monochrome effects."""

    closed = Signal()

    def __init__(self, raw_screenshot, screen_bbox: dict):
        super().__init__()
        if isinstance(raw_screenshot, QPixmap):
            self.raw_pixmap = raw_screenshot
        else:
            self.raw_pixmap = convert_pil_to_qpixmap(raw_screenshot)

        self.screen_bbox = screen_bbox
        self.cfg = config.load_config()

        # States: 'idle', 'selecting', 'thinking', 'result'
        self.state = 'idle'
        self.sel: Optional[QRectF] = None
        self.drag_start = QPoint()
        self.angle = 0.0
        self.shimmer_pos = 0.0
        self.chat_history: List[dict] = []
        self.worker: Optional[GeminiStreamWorker] = None
        self.cropped_png_bytes: Optional[bytes] = None

        # Window configuration - top level standalone window across all monitors
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

        # Position over the full virtual desktop
        self.setGeometry(
            screen_bbox["left"],
            screen_bbox["top"],
            screen_bbox["width"],
            screen_bbox["height"],
        )

        # Convert screenshot to grayscale pixmap natively in Qt (<25ms)
        qimg = self.raw_pixmap.toImage().convertToFormat(QImage.Format_Grayscale8)
        self.frozen_gray = QPixmap.fromImage(qimg)

        # Gradient rotation animation (0 to 360)
        self.angle_anim = QVariantAnimation(self)
        self.angle_anim.setStartValue(0.0)
        self.angle_anim.setEndValue(360.0)
        self.angle_anim.setDuration(int(2400 / max(0.2, self.cfg.get("animation_speed", 1.0))))
        self.angle_anim.setLoopCount(-1)
        self.angle_anim.valueChanged.connect(self._on_angle_change)
        self.angle_anim.start()

        # Shimmer animation during thinking
        self.shimmer_anim = QVariantAnimation(self)
        self.shimmer_anim.setStartValue(0.0)
        self.shimmer_anim.setEndValue(1.0)
        self.shimmer_anim.setDuration(1200)
        self.shimmer_anim.setLoopCount(-1)
        self.shimmer_anim.valueChanged.connect(self._on_shimmer_change)

        # Answer card
        self.card = AnswerCard(self)
        self.card.hide()
        self.card.close_requested.connect(self.close_overlay)
        self.card.followup_submitted.connect(self.handle_followup)

        # ESC shortcut to exit
        QShortcut(QKeySequence("Escape"), self, self.close_overlay)

    def _on_angle_change(self, val):
        self.angle = val
        if self.sel and self.sel.isValid():
            self.update()

    def _on_shimmer_change(self, val):
        self.shimmer_pos = val
        if self.state == 'thinking' and self.sel and self.sel.isValid():
            self.update()

    def close_overlay(self):
        if self.worker:
            self.worker.cancel()
        self.angle_anim.stop()
        self.shimmer_anim.stop()
        self.close()
        self.closed.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.close_overlay()
            return

        if event.button() == Qt.LeftButton:
            # Check if click is inside answer card
            if self.card.isVisible() and self.card.geometry().contains(event.pos()):
                return super().mousePressEvent(event)

            self.state = 'selecting'
            self.drag_start = event.pos()
            self.sel = QRectF(self.drag_start, self.drag_start)
            self.card.hide()
            self.update()

    def mouseMoveEvent(self, event):
        if self.state == 'selecting':
            self.sel = QRectF(self.drag_start, event.pos()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.state == 'selecting':
            self.sel = QRectF(self.drag_start, event.pos()).normalized()
            # If selection is too small, ignore or dismiss
            if self.sel.width() < 15 or self.sel.height() < 15:
                self.sel = None
                self.state = 'idle'
                self.update()
                return

            self.crop_and_search()

    def crop_and_search(self):
        """Crop the selected region from the original screenshot and query Capybara Vision."""
        if not self.sel:
            return

        self.state = 'thinking'
        self.shimmer_anim.start()

        # Crop from raw color pixmap
        rx = int(self.sel.x())
        ry = int(self.sel.y())
        rw = int(self.sel.width())
        rh = int(self.sel.height())

        # Clamp bounds
        rx = max(0, min(rx, self.raw_pixmap.width() - 1))
        ry = max(0, min(ry, self.raw_pixmap.height() - 1))
        rw = max(1, min(rw, self.raw_pixmap.width() - rx))
        rh = max(1, min(rh, self.raw_pixmap.height() - ry))

        cropped = self.raw_pixmap.copy(rx, ry, rw, rh)

        # Performance Optimization:
        # Scale oversized regions down to max 1400px to drastically reduce network transfer and inference latency
        max_dim = 1400
        if cropped.width() > max_dim or cropped.height() > max_dim:
            cropped = cropped.scaled(max_dim, max_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Fast JPEG encoding (quality 90) produces ~50-150KB payloads instead of 2-8MB PNGs
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        cropped.toImage().save(buffer, "JPEG", 90)
        self.cropped_png_bytes = bytes(byte_array.data())

        # Position Answer Card
        self.position_card()
        self.card.set_status("Analyzing region...")
        self.card.set_content("*Analyzing the selected screen region with Capybara Vision...*")
        self.card.show()
        self.card.raise_()

        # Launch Capybara Vision Worker
        api_key = config.get_api_key()
        model_name = self.cfg.get("model", "gemini-3.8-flash")
        prompt = self.cfg.get("default_prompt", "Explain what's in this region in detail.")
        sys_inst = self.cfg.get("system_instruction", "")

        self.worker = GeminiStreamWorker(
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
            image_bytes=self.cropped_png_bytes,
            mime_type="image/jpeg",
            system_instruction=sys_inst,
            chat_history=[]
        )
        self.worker.chunk_received.connect(self.on_chunk)
        self.worker.finished_success.connect(self.on_search_finished)
        self.worker.failed.connect(self.on_search_failed)
        self.first_chunk = True
        self.worker.start()

    def handle_followup(self, query: str):
        """Submit a follow-up prompt to Capybara Vision."""
        if not self.cropped_png_bytes or not self.worker:
            return

        self.card.set_status("Thinking...")
        self.card.append_text(f"\n\n**You:** {query}\n\n**Capybara Vision:** ")

        # Append previous exchange to history
        self.chat_history.append({"text": f"User question: {query}"})

        api_key = config.get_api_key()
        model_name = self.cfg.get("model", "gemini-3.8-flash")
        sys_inst = self.cfg.get("system_instruction", "")

        self.worker = GeminiStreamWorker(
            api_key=api_key,
            model_name=model_name,
            prompt=query,
            image_bytes=None,  # image already discussed or context continued
            system_instruction=sys_inst,
            chat_history=self.chat_history
        )
        self.worker.chunk_received.connect(self.on_chunk)
        self.worker.finished_success.connect(self.on_search_finished)
        self.worker.failed.connect(self.on_search_failed)
        self.first_chunk = False
        self.worker.start()

    def on_chunk(self, chunk: str):
        if self.first_chunk:
            self.card.set_content("")  # clear placeholder
            self.first_chunk = False
        self.card.append_text(chunk)

    def on_search_finished(self):
        self.state = 'result'
        self.shimmer_anim.stop()
        self.card.set_status("Complete")
        self.update()

    def on_search_failed(self, err_msg: str):
        self.state = 'result'
        self.shimmer_anim.stop()
        self.card.set_status("Error")
        self.card.set_content(f"⚠️ **Error:** {err_msg}")
        self.update()

    def position_card(self):
        """Anchor the answer card intelligently below or above the selected region."""
        if not self.sel:
            return

        margin = 16
        card_w = self.card.width()
        card_h = self.card.sizeHint().height()

        # Default: centered horizontally relative to selection
        cx = self.sel.center().x() - (card_w / 2)
        # Clamp within screen bounds
        cx = max(margin, min(cx, self.width() - card_w - margin))

        # Check if space below selection
        below_y = self.sel.bottom() + margin
        above_y = self.sel.top() - card_h - margin

        if below_y + card_h + margin <= self.height():
            cy = below_y
        elif above_y >= margin:
            cy = above_y
        else:
            # Fallback to right side or center
            cy = max(margin, min(self.sel.top(), self.height() - card_h - margin))
            if self.sel.right() + card_w + margin <= self.width():
                cx = self.sel.right() + margin
            elif self.sel.left() - card_w - margin >= margin:
                cx = self.sel.left() - card_w - margin

        self.card.move(int(cx), int(cy))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 1. Frozen grayscale screenshot backdrop
        p.drawPixmap(0, 0, self.frozen_gray)

        # Dimming & selection mask
        dim_alpha = int(255 * self.cfg.get("dim_opacity", 0.65))
        radius = self.cfg.get("corner_radius", 18)
        border_w = self.cfg.get("border_width", 3)

        if not self.sel or not self.sel.isValid():
            # Dim the entire screen uniformly when nothing is selected
            p.fillRect(self.rect(), QColor(0, 0, 0, dim_alpha))
            return

        # 2. Dim mask with rounded-rect hole cut out where selected
        full = QPainterPath()
        full.addRect(QRectF(self.rect()))

        hole = QPainterPath()
        hole.addRoundedRect(self.sel, radius, radius)

        # Draw the darkened surroundings
        p.fillPath(full.subtracted(hole), QColor(0, 0, 0, dim_alpha))

        # 3. Shimmer band moving across the cropped area during Thinking state
        if self.state == 'thinking':
            p.save()
            p.setClipPath(hole)
            shimmer_w = max(60.0, self.sel.width() * 0.4)
            start_x = self.sel.left() - shimmer_w + (self.sel.width() + shimmer_w * 2) * self.shimmer_pos
            shimmer_grad = QLinearGradient(start_x, self.sel.top(), start_x + shimmer_w, self.sel.bottom())
            shimmer_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            shimmer_grad.setColorAt(0.5, QColor(255, 255, 255, 45))
            shimmer_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillRect(self.sel, QBrush(shimmer_grad))
            p.restore()

        # 4. Animated conical gradient border & glows
        g = QConicalGradient(self.sel.center(), self.angle)
        for pos, col in [(0.0, "#ffffff"), (0.35, "#555555"), (0.6, "#111111"), (0.8, "#bbbbbb"), (1.0, "#ffffff")]:
            g.setColorAt(pos, QColor(col))

        # Glow layers: wide & faint -> thin & opaque
        if self.cfg.get("glow_enabled", True):
            passes = [(16, 0.12), (8, 0.32), (border_w, 1.0)]
        else:
            passes = [(border_w, 1.0)]

        for stroke_width, alpha in passes:
            p.save()
            p.setOpacity(alpha)
            p.setPen(QPen(QBrush(g), stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawRoundedRect(self.sel, radius, radius)
            p.restore()
