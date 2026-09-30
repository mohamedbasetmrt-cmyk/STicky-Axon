"""Application settings with persistence (position, screen, behavior)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def default_settings_dir() -> Path:
    # %LOCALAPPDATA%\StickyAxon on Windows, fallback to ./config
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "StickyAxon"
    return Path(__file__).resolve().parent


@dataclass
class Settings:
    # overlay geometry
    pos_x: int = 1100
    pos_y: int = 600
    pos_ratio_x: float = 0.85
    pos_ratio_y: float = 0.75
    screen_name: str = ""
    overlay_size: int = 220
    always_on_top: bool = True
    paused: bool = False
    # behavior
    fps_idle: int = 30
    click_through_when_sleeping: bool = False

    @classmethod
    def file_path(cls) -> Path:
        return default_settings_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        p = cls.file_path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                s = cls()
                for k, v in data.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
                return s
            except Exception:
                return cls()
        return cls()

    def save(self) -> None:
        p = self.file_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except Exception:
            pass
