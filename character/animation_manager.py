"""AnimationManager: time-based params shared by renderers.

Keeps per-state procedural motion (bob, blink, tilt, glow pulse)
so renderers stay dumb drawing functions.
"""
from __future__ import annotations

import math
import random
import time

from .states import CharacterState


class AnimationManager:
    def __init__(self):
        self.state: CharacterState = CharacterState.IDLE
        self.t_state: float = 0.0  # seconds in current state
        self.t_global: float = 0.0
        self._last = time.monotonic()
        self._next_blink = 2.0
        self._blink = 0.0
        self.look_x: float = 0.0
        self.look_y: float = 0.0
        self._look_target = (0.0, 0.0)
        self._look_timer = 0.0

    def set_state(self, state: CharacterState):
        if state != self.state:
            self.state = state
            self.t_state = 0.0
            self._look_timer = 0.0

    def tick(self) -> dict:
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        self.t_global += dt
        self.t_state += dt

        # blink logic
        self._blink = max(0.0, self._blink - dt)
        if self.t_global > self._next_blink:
            self._blink = 0.15
            self._next_blink = self.t_global + random.uniform(1.8, 4.5)

        # look-around for THINKING
        if self.state == CharacterState.THINKING:
            self._look_timer -= dt
            if self._look_timer <= 0:
                self._look_target = (random.uniform(-1, 1), random.uniform(-0.4, 0.4))
                self._look_timer = random.uniform(0.5, 1.2)
        else:
            self._look_target = (0.0, 0.0)
        k = min(1.0, dt * 8)
        self.look_x += (self._look_target[0] - self.look_x) * k
        self.look_y += (self._look_target[1] - self.look_y) * k

        t = self.t_global
        ts = self.t_state
        bob = math.sin(t * 2.2) * 4.0
        tilt = math.sin(t * 1.3) * 3.0

        if self.state == CharacterState.THINKING:
            bob = math.sin(t * 3.0) * 3.0
            tilt = math.sin(t * 0.9) * 8.0
        elif self.state == CharacterState.EXECUTING:
            bob = abs(math.sin(t * 6.0)) * -5.0
            tilt = math.sin(t * 5.0) * 4.0
        elif self.state == CharacterState.SUCCESS:
            bob = -abs(math.sin(min(ts, 1.2) * 5.0)) * 10.0
        elif self.state == CharacterState.ERROR:
            tilt = math.sin(t * 30.0) * 3.0 if ts < 0.6 else 0.0
        elif self.state == CharacterState.SPEAKING:
            bob = math.sin(t * 4.0) * 3.0
        elif self.state == CharacterState.SLEEPING:
            bob = math.sin(t * 1.0) * 2.0
            tilt = 6.0
        elif self.state == CharacterState.LISTENING:
            bob = math.sin(t * 2.8) * 5.0

        return {
            "bob": bob,
            "tilt": tilt,
            "blink": self._blink > 0,
            "look_x": self.look_x,
            "look_y": self.look_y,
            "t": t,
            "t_state": ts,
            "mouth_open": self._mouth_open(),
        }

    def _mouth_open(self) -> float:
        import math as m

        if self.state == CharacterState.SPEAKING:
            return 0.4 + 0.6 * abs(m.sin(self.t_global * 8.0))
        if self.state == CharacterState.LISTENING:
            return 0.15
        if self.state == CharacterState.SUCCESS:
            return 0.7
        if self.state == CharacterState.ERROR:
            return 0.25
        return 0.1
