"""Maps agent events -> character states with auto-return for transient states."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from agent_bridge import event_bus as ev
from .states import AGENT_EVENT_TO_STATE, CharacterState


class CharacterController(QObject):
    state_changed = Signal(str)  # CharacterState value

    TRANSIENT = {CharacterState.SUCCESS, CharacterState.ERROR}
    TRANSIENT_MS = 2500

    def __init__(self, bus: ev.EventBus, anim, renderer):
        super().__init__()
        self.bus = bus
        self.anim = anim
        self.renderer = renderer
        self.state = CharacterState.IDLE
        self._return_timer = QTimer(self)
        self._return_timer.setSingleShot(True)
        self._return_timer.timeout.connect(self._auto_return)
        bus.agent_event.connect(self._on_agent_event)

    def _on_agent_event(self, name: str, payload: dict):
        st = AGENT_EVENT_TO_STATE.get(name)
        if st is None:
            return
        self.set_state(st)

    def set_state(self, state: CharacterState):
        self._return_timer.stop()
        self.state = state
        self.anim.set_state(state)
        self.renderer.set_state(state)
        self.state_changed.emit(state.value)
        if state in self.TRANSIENT:
            self._return_timer.start(self.TRANSIENT_MS)

    def _auto_return(self):
        # SUCCESS/ERROR -> attentive idle (waiting semantics)
        self.set_state(CharacterState.IDLE)
        self.bus.emit_agent(ev.AGENT_WAITING, {"auto": True})
        # controller immediately reflects waiting as WAITING_FOR_USER visuals
        self._return_timer.stop()
        self.state = CharacterState.WAITING_FOR_USER
        self.anim.set_state(CharacterState.WAITING_FOR_USER)
        self.renderer.set_state(CharacterState.WAITING_FOR_USER)
        self.state_changed.emit(CharacterState.WAITING_FOR_USER.value)
