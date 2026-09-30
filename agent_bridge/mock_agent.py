"""Demo/mock agent cycling states so companion can be tested standalone.

Replace with your real agent: just call AgentBridge methods.
Run: python -m agent_bridge.mock_agent (needs QApplication event loop,
but this helper can also run headless with QCoreApplication).
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer


class MockAgent(QObject):
    """Cycles: idle -> listening -> thinking -> executing -> completed -> speaking."""

    def __init__(self, bridge, interval_ms: int = 3500):
        super().__init__()
        self.bridge = bridge
        self._steps = [
            ("idle", lambda: self.bridge.idle()),
            ("listening", lambda: self.bridge.listening()),
            ("thinking", lambda: self.bridge.thinking({"task": "demo"})),
            ("executing", lambda: self.bridge.executing({"task": "demo"})),
            ("completed", lambda: self.bridge.task_completed({})),
            ("speaking", lambda: self.bridge.speaking({"text": "Done!"})),
        ]
        self._i = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(interval_ms)
        # log UI -> agent events
        self.bridge.bus.character_event.connect(self._on_ui)

    def _tick(self):
        if self.bridge.paused:
            return
        name, fn = self._steps[self._i % len(self._steps)]
        fn()
        self._i += 1

    def _on_ui(self, name: str, payload: dict):
        print(f"[MockAgent] UI event: {name} {payload}")
        if name == "character.double_clicked":
            self.bridge.executing({"task": "opened by double-click"})
