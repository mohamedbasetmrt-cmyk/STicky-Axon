"""Sticky Axon entry point: tray + floating companion + agent bridge."""
from __future__ import annotations

import sys

from PySide6.QtCore import QLockFile, QDir
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running in tray
    app.setApplicationName("Sticky Axon")
    app.setOrganizationName("StickyAxon")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Sticky Axon", "System tray not available on this system.")
        return 1

    # single instance
    lock = QLockFile(QDir.temp().absoluteFilePath("sticky-axon.lock"))
    if not lock.tryLock(100):
        QMessageBox.warning(None, "Sticky Axon", "Already running! Check the system tray.")
        return 0

    from agent_bridge.event_bus import EventBus
    from agent_bridge.agent_bridge import AgentBridge
    from agent_bridge.mock_agent import MockAgent
    from character.animation_manager import AnimationManager
    from character.character_controller import CharacterController
    from character.renderers.qt_painter_renderer import QtPainterRenderer
    from config.settings import Settings
    from overlay.overlay_window import OverlayWindow
    from tray.system_tray import SystemTray

    settings = Settings.load()
    bus = EventBus.instance()
    bridge = AgentBridge(bus)
    if settings.paused:
        bridge._paused = True

    anim = AnimationManager()
    renderer = QtPainterRenderer()
    controller = CharacterController(bus, anim, renderer)
    overlay = OverlayWindow(bus, bridge, settings, anim, renderer, controller)
    overlay.show()

    tray = SystemTray(bus, bridge, overlay, settings)
    if bridge.paused:
        tray.act_pause.setText("▶ Resume Agent")

    # Demo agent: remove/replace with your real agent wiring.
    # Your agent only needs: bridge.thinking(...) etc.
    mock = MockAgent(bridge, interval_ms=4000)
    bridge.started({"demo": True})

    # log character interactions (your agent can subscribe instead)
    bus.character_event.connect(lambda n, p: print(f"[UI] {n} {p}"))

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
