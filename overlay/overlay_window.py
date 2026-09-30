"""Transparent always-on-top overlay window hosting the character."""
from __future__ import annotations

import time

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from agent_bridge import event_bus as ev
from overlay.character_view import CharacterView
from overlay.interaction import MiniPanel, build_character_menu


class OverlayWindow(QWidget):
    def __init__(self, bus: ev.EventBus, bridge, settings, anim, renderer, controller):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus,
        )
        self.bus = bus
        self.bridge = bridge
        self.settings = settings
        self.controller = controller

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowTitle("Sticky Axon Companion")
        self.setFixedSize(settings.overlay_size, settings.overlay_size)

        self.view = CharacterView(anim, renderer, self, fps=settings.fps_idle)
        self.view.setGeometry(0, 0, settings.overlay_size, settings.overlay_size)
        self.view3d = None
        self._status3d = None
        self._try_enable_3d()

        self.panel = MiniPanel(bus, bridge)
        self.panel.hide()

        controller.state_changed.connect(self._on_state)

        # drag / click state
        self._dragging = False
        self._drag_offset = QPoint()
        self._press_pos = QPoint()
        self._press_time = 0.0
        self._moved = False

        self._restore_position()
        # keep position valid when monitors change
        app = QGuiApplication.instance()
        if app is not None:
            try:
                app.screenAdded.connect(lambda *a: self._clamp_to_screen())
                app.screenRemoved.connect(lambda *a: self._clamp_to_screen())
            except Exception:
                pass

    # ---------- state visuals ----------
    def _on_state(self, state_value: str):
        labels = {
            "idle": "",
            "listening": "🎤 listening…",
            "thinking": "💭 thinking…",
            "executing": "⚙ working…",
            "success": "✅ done!",
            "error": "❌ failed",
            "waiting_for_user": "",
            "speaking": "🔊 speaking…",
            "sleeping": "💤 paused",
        }
        self.view.set_status(labels.get(state_value, ""))
        if self.view3d is not None:
            self.view3d.set_state(state_value)
            if self._status3d is not None:
                self._status3d.setText(labels.get(state_value, ""))
        if state_value == "sleeping" and self.settings.click_through_when_sleeping:
            self.setWindowFlag(Qt.WindowTransparentForInput, True)
            self.show()
        elif state_value != "sleeping":
            self.setWindowFlag(Qt.WindowTransparentForInput, False)
            self.show()

    # ---------- position persistence + multi-monitor ----------
    def _restore_position(self):
        screens = QGuiApplication.screens()
        target = None
        if self.settings.screen_name:
            for s in screens:
                if s.name() == self.settings.screen_name:
                    target = s
                    break
        if target is None:
            target = QGuiApplication.primaryScreen()
        if target is None and screens:
            target = screens[0]
        if target is None:
            self.move(self.settings.pos_x, self.settings.pos_y)
            return
        geo = target.availableGeometry()
        # prefer saved ratio (DPI / resolution independent)
        x = geo.x() + int(geo.width() * self.settings.pos_ratio_x)
        y = geo.y() + int(geo.height() * self.settings.pos_ratio_y)
        # validate saved absolute pos is still on some screen
        for s in screens:
            if s.availableGeometry().contains(self.settings.pos_x, self.settings.pos_y):
                x, y = self.settings.pos_x, self.settings.pos_y
                target = s
                break
        self.move(x, y)
        self._clamp_to_screen()
        self._remember_screen()

    def _clamp_to_screen(self):
        screen = QGuiApplication.screenAt(self.geometry().center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = max(geo.x(), min(self.x(), geo.x() + geo.width() - self.width()))
        y = max(geo.y(), min(self.y(), geo.y() + geo.height() - self.height()))
        self.move(x, y)

    def _remember_screen(self):
        screen = QGuiApplication.screenAt(self.geometry().center())
        if screen is not None:
            geo = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else screen.availableGeometry()
            sgeo = screen.availableGeometry()
            self.settings.screen_name = screen.name()
            # ratio within current screen
            if sgeo.width() > 0 and sgeo.height() > 0:
                self.settings.pos_ratio_x = (self.x() - sgeo.x()) / sgeo.width()
                self.settings.pos_ratio_y = (self.y() - sgeo.y()) / sgeo.height()
        self.settings.pos_x = self.x()
        self.settings.pos_y = self.y()
        self.settings.save()

    # ---------- 3D model view (QtQuick3D) with 2D fallback ----------
    def _model_path(self):
        from pathlib import Path
        base = Path(__file__).resolve().parent.parent / "assets" / "character"
        for name in ("octahedron_low.json", "octahedron.obj"):
            p = base / name
            if p.exists():
                return p
        return None

    def _try_enable_3d(self):
        try:
            mp = self._model_path()
            if mp is None:
                return
            from overlay.model_view3d import ModelView3D
            v = ModelView3D(mp, self)
            v.setGeometry(0, 0, self.settings.overlay_size, self.settings.overlay_size)
            v.load_failed.connect(self._on_3d_failed)
            self.view3d = v
            self.view3d.set_state(self.controller.state.value)
            self.view.set_running(False)
            self.view.hide()
            self.view3d.show()
            from PySide6.QtWidgets import QLabel
            w, h = self.settings.overlay_size, self.settings.overlay_size
            self._status3d = QLabel("", self)
            self._status3d.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self._status3d.setGeometry(0, h - 26, w, 22)
            self._status3d.setStyleSheet("color: white; background: transparent; font-size: 13px;")
            self._status3d.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._status3d.show()
            self._status3d.raise_()
            print(f"[Overlay] 3D character enabled ({mp.name}, software raster)")
        except Exception as e:
            print(f"[Overlay] 3D disabled, using 2D: {e}")

    def _on_3d_failed(self, msg: str):
        print(f"[Overlay] 3D viewer error, falling back to 2D: {msg}")
        if self.view3d is not None:
            self.view3d.hide()
            self.view3d.deleteLater()
            self.view3d = None
        if self._status3d is not None:
            self._status3d.hide()
            self._status3d.deleteLater()
            self._status3d = None
        self.view.set_running(True)
        self.view.show()

    # ---------- mouse: drag vs click vs double-click vs right-click ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = e.globalPosition().toPoint()
            self._press_time = time.monotonic()
            self._moved = False
        elif e.button() == Qt.RightButton:
            self.bus.emit_character(ev.CHAR_MENU_REQUESTED, {"x": e.globalPosition().x(), "y": e.globalPosition().y()})
            menu = build_character_menu(self, self.bus, self.bridge, self)
            menu.exec(e.globalPosition().toPoint())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging and (e.buttons() & Qt.LeftButton):
            new_pos = e.globalPosition().toPoint() - self._drag_offset
            if (e.globalPosition().toPoint() - self._press_pos).manhattanLength() > 6:
                self._moved = True
            self.move(new_pos)
            self.bus.emit_character(ev.CHAR_DRAGGED, {"x": new_pos.x(), "y": new_pos.y()})
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            if self._moved:
                self._remember_screen()
            else:
                # treat as single click (double-click handled separately)
                QTimer.singleShot(220, self._maybe_single_click)
        super().mouseReleaseEvent(e)

    def _click_guard(self) -> bool:
        return not self._moved

    def _maybe_single_click(self):
        if self._moved:
            return
        # if panel visible -> hide, else show near character
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self.bus.emit_character(ev.CHAR_CLICKED, {})
            pos = self.geometry().topRight()
            self.panel.move(pos.x() + 8, pos.y())
            self.panel.show()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._moved = True  # suppress pending single-click
            self.bus.emit_character(ev.CHAR_DOUBLE_CLICKED, {})
            self.open_main_interface()
        super().mouseDoubleClickEvent(e)

    # ---------- actions invoked from tray / menu ----------
    def open_main_interface(self):
        QMessageBox.information(
            self, "Sticky Axon",
            "Main agent interface goes here.\n\nWire your existing agent UI or chat window to this slot.\n(Double-click works ✅)",
        )

    def open_settings_placeholder(self):
        QMessageBox.information(
            self, "Settings",
            f"Settings file:\n{self.settings.file_path()}\n\nAlways-on-top: {self.settings.always_on_top}\nSize: {self.settings.overlay_size}px",
        )

    def set_paused_visual(self, paused: bool):
        pass  # state comes via agent events (agent.paused -> SLEEPING)
