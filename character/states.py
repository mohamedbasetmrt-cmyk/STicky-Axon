"""Character states (UI animation states)."""
from __future__ import annotations

from enum import Enum


class CharacterState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    EXECUTING = "executing"
    SUCCESS = "success"
    ERROR = "error"
    WAITING_FOR_USER = "waiting_for_user"
    SPEAKING = "speaking"
    SLEEPING = "sleeping"


# agent event name -> CharacterState
AGENT_EVENT_TO_STATE: dict[str, CharacterState] = {
    "agent.started": CharacterState.IDLE,
    "agent.idle": CharacterState.IDLE,
    "agent.listening": CharacterState.LISTENING,
    "agent.thinking": CharacterState.THINKING,
    "agent.executing": CharacterState.EXECUTING,
    "agent.task_completed": CharacterState.SUCCESS,
    "agent.task_failed": CharacterState.ERROR,
    "agent.waiting": CharacterState.WAITING_FOR_USER,
    "agent.speaking": CharacterState.SPEAKING,
    "agent.paused": CharacterState.SLEEPING,
    "agent.resumed": CharacterState.IDLE,
}
