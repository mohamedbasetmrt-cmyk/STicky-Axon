"""Procedural 2D robot renderer (QPainter). No assets needed.

Replace later with Lottie/QtQuick3D by implementing CharacterRenderer.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen

from .renderer_interface import CharacterRenderer
from character.states import CharacterState

STATE_GLOW = {
    CharacterState.IDLE: QColor(80, 200, 255, 90),
    CharacterState.LISTENING: QColor(80, 255, 170, 110),
    CharacterState.THINKING: QColor(180, 140, 255, 120),
    CharacterState.EXECUTING: QColor(255, 180, 80, 130),
    CharacterState.SUCCESS: QColor(90, 255, 140, 140),
    CharacterState.ERROR: QColor(255, 90, 90, 140),
    CharacterState.WAITING_FOR_USER: QColor(80, 200, 255, 90),
    CharacterState.SPEAKING: QColor(120, 220, 255, 120),
    CharacterState.SLEEPING: QColor(120, 120, 160, 70),
}


class QtPainterRenderer(CharacterRenderer):
    def __init__(self):
        self.state = CharacterState.IDLE
        self.params: dict = {"bob": 0, "tilt": 0, "blink": False,
                             "look_x": 0, "look_y": 0, "t": 0,
                             "t_state": 0, "mouth_open": 0.1}

    def set_state(self, state) -> None:
        self.state = state

    def update(self, dt: float, params: dict) -> None:
        self.params = params

    def paint(self, painter: QPainter, rect) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        cx = rect.center().x()
        cy = rect.center().y()
        bob = self.params.get("bob", 0)
        tilt = self.params.get("tilt", 0)
        t = self.params.get("t", 0)

        size = min(rect.width(), rect.height())
        s = size / 200.0  # normalize to 200px design

        # ground shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 70)))
        painter.drawEllipse(QRectF(cx - 45 * s, cy + 62 * s + bob * 0.3, 90 * s, 16 * s))

        # glow
        glow = STATE_GLOW.get(self.state, QColor(80, 200, 255, 90))
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QRectF(cx - 70 * s, cy - 70 * s + bob, 140 * s, 150 * s))

        painter.translate(cx, cy + bob)
        painter.rotate(tilt * 0.4)

        # --- body ---
        body_w, body_h = 84 * s, 62 * s
        body_rect = QRectF(-body_w / 2, 2 * s, body_w, body_h)
        painter.setBrush(QBrush(QColor(32, 42, 58)))
        painter.setPen(QPen(QColor(90, 220, 255, 160), 2 * s))
        painter.drawRoundedRect(body_rect, 18 * s, 18 * s)

        # chest core
        pulse = 0.5 + 0.5 * math.sin(t * (6 if self.state == CharacterState.EXECUTING else 2.5))
        core_c = QColor(90, 220, 255)
        if self.state == CharacterState.ERROR:
            core_c = QColor(255, 90, 90)
        elif self.state == CharacterState.SUCCESS:
            core_c = QColor(90, 255, 150)
        elif self.state == CharacterState.THINKING:
            core_c = QColor(180, 140, 255)
        painter.setBrush(QBrush(core_c))
        painter.setPen(Qt.NoPen)
        r = (10 + 3 * pulse) * s
        painter.drawEllipse(QRectF(-r, 24 * s - r, r * 2, r * 2))

        # --- arms ---
        arm_c = QColor(48, 62, 84)
        painter.setBrush(QBrush(arm_c))
        swing = math.sin(t * 5) * (8 if self.state == CharacterState.EXECUTING else 3) * s
        painter.drawRoundedRect(QRectF(-58 * s, 10 * s + swing, 16 * s, 38 * s), 8 * s, 8 * s)
        painter.drawRoundedRect(QRectF(42 * s, 10 * s - swing, 16 * s, 38 * s), 8 * s, 8 * s)

        # --- head ---
        hw, hh = 96 * s, 64 * s
        head_rect = QRectF(-hw / 2, -62 * s, hw, hh)
        painter.setBrush(QBrush(QColor(24, 33, 48)))
        painter.setPen(QPen(QColor(110, 230, 255, 180), 2 * s))
        painter.drawRoundedRect(head_rect, 20 * s, 20 * s)

        # antenna
        painter.setPen(QPen(QColor(110, 230, 255, 160), 3 * s))
        painter.drawLine(0, -62 * s, 0, -78 * s)
        blink_on = int(t * 2) % 2 == 0
        ant_c = QColor(255, 200, 80) if blink_on else QColor(255, 120, 120)
        if self.state == CharacterState.THINKING:
            ant_c = QColor(190, 150, 255)
        painter.setBrush(QBrush(ant_c))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(-6 * s, -90 * s, 12 * s, 12 * s))

        # eyes
        look_x = self.params.get("look_x", 0) * 6 * s
        look_y = self.params.get("look_y", 0) * 4 * s
        if self.params.get("blink"):
            painter.setPen(QPen(QColor(120, 220, 255), 3 * s))
            painter.drawLine(-30 * s, -32 * s, -12 * s, -32 * s)
            painter.drawLine(12 * s, -32 * s, 30 * s, -32 * s)
        else:
            eye_h = 20 * s
            if self.state == CharacterState.SLEEPING:
                painter.setPen(QPen(QColor(120, 220, 255), 3 * s))
                painter.drawLine(-30 * s, -32 * s, -12 * s, -32 * s)
                painter.drawLine(12 * s, -32 * s, 30 * s, -32 * s)
            else:
                painter.setBrush(QBrush(QColor(140, 235, 255)))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QRectF(-32 * s, -42 * s, 22 * s, eye_h))
                painter.drawEllipse(QRectF(10 * s, -42 * s, 22 * s, eye_h))
                painter.setBrush(QBrush(QColor(10, 20, 35)))
                painter.drawEllipse(QRectF(-26 * s + look_x, -36 * s + look_y, 10 * s, 10 * s))
                painter.drawEllipse(QRectF(16 * s + look_x, -36 * s + look_y, 10 * s, 10 * s))

        # mouth
        mo = self.params.get("mouth_open", 0.1)
        mh = max(2 * s, mo * 12 * s)
        painter.setBrush(QBrush(QColor(140, 235, 255, 200)))
        painter.drawRoundedRect(QRectF(-14 * s, -14 * s, 28 * s, mh), 4 * s, 4 * s)

        painter.restore()
        self._paint_state_overlay(painter, rect, s, cx, cy, t)

    # ---- per-state badges ----
    def _paint_state_overlay(self, p: QPainter, rect, s: float, cx: float, cy: float, t: float):
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.state in (CharacterState.THINKING, CharacterState.EXECUTING):
            # orbiting dots
            n = 3
            for i in range(n):
                a = t * 4 + i * 2.09
                x = cx + math.cos(a) * 62 * s
                y = cy - 30 * s + math.sin(a) * 52 * s
                c = QColor(190, 150, 255) if self.state == CharacterState.THINKING else QColor(255, 190, 90)
                p.setBrush(QBrush(c))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QRectF(x - 5 * s, y - 5 * s, 10 * s, 10 * s))
        elif self.state == CharacterState.SUCCESS:
            p.setPen(QPen(QColor(90, 255, 150), 6 * s, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(cx - 22 * s, cy + 78 * s, cx - 6 * s, cy + 92 * s)
            p.drawLine(cx - 6 * s, cy + 92 * s, cx + 24 * s, cy + 62 * s)
        elif self.state == CharacterState.ERROR:
            p.setPen(QPen(QColor(255, 100, 100), 6 * s, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(cx - 14 * s, cy + 66 * s, cx + 14 * s, cy + 90 * s)
            p.drawLine(cx + 14 * s, cy + 66 * s, cx - 14 * s, cy + 90 * s)
        elif self.state == CharacterState.LISTENING:
            pulse = (t * 1.5) % 1.0
            p.setPen(QPen(QColor(90, 255, 170, int(180 * (1 - pulse))), 2 * s))
            r = (60 + pulse * 22) * s
            p.drawEllipse(QRectF(cx - r, cy - 20 * s - r, r * 2, r * 2))
        elif self.state == CharacterState.SPEAKING:
            for i in range(3):
                h = (6 + 8 * abs(math.sin(t * 8 + i))) * s
                x = cx + (i - 1) * 16 * s
                p.setBrush(QBrush(QColor(120, 220, 255, 180)))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(x - 3 * s, cy + 74 * s - h, 6 * s, h), 3 * s, 3 * s)
        elif self.state == CharacterState.SLEEPING:
            p.setPen(QPen(QColor(150, 160, 200), 2 * s))
            font = QFont("Segoe UI", int(14 * s))
            p.setFont(font)
            for i, ch in enumerate(["z", "Z"]):
                off = (t * 12 + i * 18) % 40
                p.drawText(int(cx + 44 * s + i * 8), int(cy - 50 * s - off), ch)
        p.restore()
