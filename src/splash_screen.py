"""
splash_screen.py
----------------
Responsive, frameless startup artwork for PDF Studio.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PyQt6.QtGui import QCursor, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from startup_splash_core import FADE_DURATION_MS, scaled_splash_size

SPLASH_ASSET = "assets/splashscreen.png"


def resource_path(relative_path: str) -> Path:
    """Resolve a bundled PyInstaller resource or a source-tree resource."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / relative_path
    return Path(__file__).resolve().parent.parent / relative_path


class PDFStudioSplash(QWidget):
    """Transparent image-only splash with a controlled fade-out."""

    def __init__(self, image_path: Optional[Path] = None) -> None:
        flags = (
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(None, flags)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("PDF Studio")

        path = image_path or resource_path(SPLASH_ASSET)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            raise FileNotFoundError(f"Could not load splash image: {path}")

        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("No display is available for the splash screen")

        available = screen.availableGeometry()
        width, height = scaled_splash_size(
            pixmap.width(),
            pixmap.height(),
            available.width(),
            available.height(),
        )
        if (width, height) != (pixmap.width(), pixmap.height()):
            pixmap = pixmap.scaled(
                width,
                height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        self._pixmap = pixmap
        self._fade_animation: Optional[QPropertyAnimation] = None
        self.setFixedSize(self._pixmap.size())
        self.move(available.center() - self.rect().center())

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)

    def fade_out(
        self,
        finished_callback: Optional[Callable[[], None]] = None,
        duration_ms: int = FADE_DURATION_MS,
    ) -> None:
        """Fade to transparent, reveal the app, then close the splash."""
        if self._fade_animation is not None:
            return

        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(max(0, int(duration_ms)))
        animation.setStartValue(self.windowOpacity())
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        def _finish() -> None:
            # Show the main window before closing the last visible top-level
            # window, otherwise QApplication may interpret the splash close as
            # a request to quit.
            if finished_callback is not None:
                finished_callback()
            self.hide()
            self.close()

        animation.finished.connect(_finish)
        self._fade_animation = animation
        animation.start()
