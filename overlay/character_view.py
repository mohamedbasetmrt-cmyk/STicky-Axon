"""CharacterView: transparent widget hosting the renderer + 30fps loop."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget


class CharacterView(QWidget):
    def __init__(self, anim, renderer, parent=None, fps: int = 30):
        super().__init__(parent)
        self.anim = anim
        self.renderer = renderer
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._frame)
        self._timer.start(int(1000 / max(1, fps)))
        self._status_text = ""

    def _frame(self):
        params = self.anim.tick()
        self.renderer.update(0.033, params)
        self.update()

    def set_running(self, running: bool):
        if running and not self._timer.isActive():
            self._timer.start()
        elif not running and self._timer.isActive():
            self._timer.stop()

    def set_status(self, text: str):
        self._status_text = text
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        self.renderer.paint(p, self.rect())
        if self._status_text:
            p.setPen(Qt.white)
            p.drawText(self.rect().adjusted(0, 0, 0, -4), Qt.AlignHCenter | Qt.AlignBottom, self._status_text)
        p.end()
