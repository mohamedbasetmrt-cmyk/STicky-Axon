"""Small floating interaction panel + context menu builders."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMenu, QPushButton, QVBoxLayout, QWidget


class MiniPanel(QWidget):
    """Tiny transparent card shown on single-click near the character."""

    def __init__(self, bus, bridge, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.bus = bus
        self.bridge = bridge
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("""
            MiniPanel { background: rgba(18,26,40,230); border: 1px solid rgba(90,220,255,90);
                        border-radius: 12px; }
            QLabel { color: white; font-size: 13px; }
            QPushButton { background: rgba(90,220,255,30); color: white;
                          border-radius: 8px; padding: 6px; }
            QPushButton:hover { background: rgba(90,220,255,60); }
        """)
        layout = QVBoxLayout(self)
        self.label = QLabel("👋 Hi! I'm your AI companion.\nDouble-click me to open the agent.")
        layout.addWidget(self.label)
        self.btn_talk = QPushButton("Talk (simulate listening)")
        self.btn_think = QPushButton("Think (simulate task)")
        self.btn_hide = QPushButton("Hide panel")
        layout.addWidget(self.btn_talk)
        layout.addWidget(self.btn_think)
        layout.addWidget(self.btn_hide)
        self.btn_talk.clicked.connect(lambda: bus.emit_agent("agent.listening", {}))
        self.btn_think.clicked.connect(lambda: bus.emit_agent("agent.thinking", {"task": "panel demo"}))
        self.btn_hide.clicked.connect(self.hide)

    def focusOutEvent(self, e):
        self.hide()
        super().focusOutEvent(e)


def build_character_menu(parent, bus, bridge, overlay) -> QMenu:
    from agent_bridge import event_bus as ev

    m = QMenu(parent)
    m.setStyleSheet("QMenu { background: #141e30; color: white; } QMenu::item:selected { background: #24435e; }")
    m.addAction("💬 Talk", lambda: bus.emit_agent(ev.AGENT_LISTENING, {}))
    m.addAction("🧠 Simulate task", lambda: bus.emit_agent(ev.AGENT_EXECUTING, {"task": "menu demo"}))
    m.addSeparator()
    pause_act = m.addAction("⏸ Pause agent" if not bridge.paused else "▶ Resume agent")
    pause_act.triggered.connect(lambda: bridge.set_paused(not bridge.paused))
    m.addAction("⚙ Settings", overlay.open_settings_placeholder)
    m.addAction("❌ Hide companion", overlay.hide)
    return m
