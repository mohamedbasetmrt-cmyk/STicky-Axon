"""Central event bus decoupling AI agent from UI.

Agent -> UI: agent_event(str, dict)
UI -> Agent: character_event(str, dict)

Event names (agent -> UI):
  agent.started, agent.listening, agent.thinking, agent.executing,
  agent.task_completed, agent.task_failed, agent.waiting,
  agent.speaking, agent.idle, agent.paused, agent.resumed
Events (UI -> agent):
  character.clicked, character.double_clicked,
  character.dragged, character.menu_requested
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

# agent -> UI
AGENT_STARTED = "agent.started"
AGENT_LISTENING = "agent.listening"
AGENT_THINKING = "agent.thinking"
AGENT_EXECUTING = "agent.executing"
AGENT_TASK_COMPLETED = "agent.task_completed"
AGENT_TASK_FAILED = "agent.task_failed"
AGENT_WAITING = "agent.waiting"
AGENT_SPEAKING = "agent.speaking"
AGENT_IDLE = "agent.idle"
AGENT_PAUSED = "agent.paused"
AGENT_RESUMED = "agent.resumed"

# UI -> agent
CHAR_CLICKED = "character.clicked"
CHAR_DOUBLE_CLICKED = "character.double_clicked"
CHAR_DRAGGED = "character.dragged"
CHAR_MENU_REQUESTED = "character.menu_requested"


class EventBus(QObject):
    agent_event = Signal(str, dict)
    character_event = Signal(str, dict)

    _instance = None

    @classmethod
    def instance(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def emit_agent(self, name: str, payload: dict | None = None) -> None:
        self.agent_event.emit(name, payload or {})

    def emit_character(self, name: str, payload: dict | None = None) -> None:
        self.character_event.emit(name, payload or {})
