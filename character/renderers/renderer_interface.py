"""Renderer abstraction: replace character art without touching agent/UI logic."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CharacterRenderer(ABC):
    """Any renderer (2D painter, Lottie, QtQuick3D, Three.js) implements this."""

    @abstractmethod
    def set_state(self, state) -> None:
        ...

    @abstractmethod
    def update(self, dt: float, params: dict[str, Any]) -> None:
        """Advance animation by dt seconds."""
        ...

    @abstractmethod
    def paint(self, painter, rect) -> None:
        """Draw current frame into rect using QPainter."""
        ...
