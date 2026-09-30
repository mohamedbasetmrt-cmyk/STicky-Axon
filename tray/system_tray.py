"""Windows System Tray icon (notification area, no taskbar button)."""
from __future__ import annotations

from PySide6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon


def make_tray_icon(size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QBrush(QColor(24, 33, 48)))
    p.setPen(QColor(90, 220, 255))
    p.drawRoundedRect(4, 10, size - 8, size - 20, 12, 12)
    p.setBrush(QBrush(QColor(140, 235, 255)))
    p.drawEllipse(14, 24, 14, 14)
    p.drawEllipse(size - 28, 24, 14, 14)
    p.end()
    return QIcon(pm)


class SystemTray(QSystemTrayIcon):
    def __init__(self, bus, bridge, overlay, settings, parent=None):
        super().__init__(parent)
        from agent_bridge import event_bus as ev
        self.bus = bus
        self.bridge = bridge
        self.overlay = overlay
        self.settings = settings
        self._ev = ev

        self.setIcon(make_tray_icon())
        self.setToolTip("Sticky Axon — AI Companion")
        self.setVisible(True)

        menu = QMenu()
        self.act_show = QAction("👁 Open / Show Companion", menu)
        self.act_pause = QAction("⏸ Pause Agent", menu)
        self.act_settings = QAction("⚙ Settings", menu)
        self.act_restart = QAction("🔄 Restart Agent", menu)
        self.act_quit = QAction("❌ Exit", menu)
        for a in (self.act_show, self.act_pause, self.act_settings, self.act_restart, self.act_quit):
            menu.addAction(a)
        self.act_show.triggered.connect(self.show_companion)
        self.act_pause.triggered.connect(self.toggle_pause)
        self.act_settings.triggered.connect(self.open_settings)
        self.act_restart.triggered.connect(self.restart_agent)
        self.act_quit.triggered.connect(self.quit_app)
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)
        self.messageClicked.connect(lambda: self.show_companion())
        self.showMessage("Sticky Axon", "Companion running in tray 🟢", QSystemTrayIcon.Information, 3000)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_companion()
        elif reason == QSystemTrayIcon.Trigger:
            self.show_companion()

    # ---- slots ----
    def show_companion(self):
        self.overlay.show()
        self.overlay.raise_()
        self.overlay._clamp_to_screen()

    def toggle_pause(self):
        new_state = not self.bridge.paused
        self.bridge.set_paused(new_state)
        self.act_pause.setText("▶ Resume Agent" if new_state else "⏸ Pause Agent")
        self.setToolTip(f"Sticky Axon — {'Paused ⏸' if new_state else 'Running 🟢'}")

    def open_settings(self):
        self.overlay.open_settings_placeholder()

    def restart_agent(self):
        self.bridge.restart()
        self.showMessage("Sticky Axon", "Agent restarted 🔄", QSystemTrayIcon.Information, 2000)

    def quit_app(self):
        from PySide6.QtWidgets import QApplication
        self.hide()
        QApplication.quit()

    def confirm_quit(self, parent=None) -> bool:
        r = QMessageBox.question(parent, "Exit?", "Quit Sticky Axon companion?")
        return r == QMessageBox.Yes
