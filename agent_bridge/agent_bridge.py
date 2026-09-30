"""Clean interface between existing Python AI agent and the companion UI.

Your AI agent imports ONLY this file (never Qt widgets).
The companion UI subscribes to EventBus.

Example in your agent:
    from agent_bridge.agent_bridge import AgentBridge
    bridge = AgentBridge(bus)
    bridge.thinking({"task": "open notepad"})
"""
from __future__ import annotations

from . import event_bus as ev


class AgentBridge:
    """Agent-side facade. UI-side code should use EventBus directly."""

    def __init__(self, bus: ev.EventBus):
        self.bus = bus
        self._paused = False

    # ---- agent -> UI ----
    def started(self, payload: dict | None = None):
        self.bus.emit_agent(ev.AGENT_STARTED, payload)

    def listening(self, payload: dict | None = None):
        self.bus.emit_agent(ev.AGENT_LISTENING, payload)

    def thinking(self, payload: dict | None = None):
        self.bus.emit_agent(ev.AGENT_THINKING, payload)

    def executing(self, payload: dict | None = None):
        self.bus.emit_agent(ev.AGENT_EXECUTING, payload)

    def task_completed(self, payload: dict | None = None):
        self.bus.emit_agent(ev.AGENT_TASK_COMPLETED, payload)

    def task_failed(self, payload: dict | None = None):
        self.bus.emit_agent(ev.AGENT_TASK_FAILED, payload)

    def waiting(self, payload: dict | None = None):
        self.bus.emit_agent(ev.AGENT_WAITING, payload)

    def speaking(self, payload: dict | None = None):
        self.bus.emit_agent(ev.AGENT_SPEAKING, payload)

    def idle(self, payload: dict | None = None):
        self.bus.emit_agent(ev.AGENT_IDLE, payload)

    # ---- UI -> agent control ----
    @property
    def paused(self) -> bool:
        return self._paused

    def set_paused(self, paused: bool):
        self._paused = paused
        self.bus.emit_agent(ev.AGENT_PAUSED if paused else ev.AGENT_RESUMED, {})

    def on_character_event(self, handler):
        """Subscribe your agent logic to UI events: handler(name, payload)."""
        self.bus.character_event.connect(handler)

    def restart(self):
        """Hook: your real agent should override/replace this."""
        self.started({"restart": True})
