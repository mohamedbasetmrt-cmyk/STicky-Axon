"""Software-rasterized 3D character view (QPainter).

Why software: on this machine GL contexts report success but render nothing
(verified: shaders link, glDrawArrays returns no error, framebuffer stays
black). So the 3D character is rasterized on the CPU with numpy + QPainter,
which composites correctly inside the transparent overlay window.

API matches what OverlayWindow expects:
    ModelView3D(model_path, parent)  # raises on bad input -> 2D fallback
    set_state(state_value: str)
    ok -> bool
    load_failed(str) signal
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPolygonF
from PySide6.QtWidgets import QWidget

STATUS_LABELS = {
    "idle": "",
    "listening": "🎤 listening…",
    "thinking": "💭 thinking…",
    "executing": "⚙ working…",
    "success": "✅ done!",
    "error": "❌ failed",
    "waiting_for_user": "",
    "speaking": "🔊 speaking…",
    "sleeping": "💤 paused",
}

# spin deg/s, bob amp, bob freq, tilt amp deg, pulse, glow rgb
STATE_PARAMS = {
    "idle": (25.0, 0.07, 2.2, 3.0, 0.02, (0.31, 0.78, 1.00)),
    "listening": (35.0, 0.10, 2.8, 4.0, 0.05, (0.31, 1.00, 0.67)),
    "thinking": (60.0, 0.06, 3.0, 10.0, 0.03, (0.71, 0.55, 1.00)),
    "executing": (200.0, 0.08, 6.0, 5.0, 0.06, (1.00, 0.71, 0.31)),
    "success": (90.0, 0.16, 5.0, 3.0, 0.10, (0.35, 1.00, 0.55)),
    "error": (15.0, 0.03, 9.0, 14.0, 0.02, (1.00, 0.35, 0.35)),
    "waiting_for_user": (25.0, 0.07, 2.2, 3.0, 0.02, (0.31, 0.78, 1.00)),
    "speaking": (45.0, 0.09, 4.0, 4.0, 0.07, (0.47, 0.86, 1.00)),
    "sleeping": (8.0, 0.04, 1.0, 8.0, 0.01, (0.47, 0.47, 0.61)),
}


class ModelView3D(QWidget):
    load_failed = Signal(str)

    def __init__(self, model_path: Path, parent=None, fps: int = 30):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._dead = False

        P, C, F = _load_model(Path(model_path))
        self.P = P                      # (n,3) local positions
        self.C = np.clip(C, 0.0, 1.0)   # (n,3) colors
        self.F = F                      # (m,3) indices
        self.center = P.mean(axis=0)
        self.P = P - self.center
        self.radius = float(np.linalg.norm(self.P, axis=1).max())

        # animation state
        self._state = "idle"
        self._angle = 0.0
        self._t = 0.0
        self._last = time.monotonic()
        self._spin = 25.0
        self._glow = np.array([0.31, 0.78, 1.0])
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._frame)
        self._timer.start(int(1000 / max(1, fps)))

    # ---- API ----
    @property
    def ok(self) -> bool:
        return not self._dead

    def set_state(self, state_value: str):
        self._state = state_value

    # ---- animation ----
    def _frame(self):
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        if self._dead:
            return
        self._t += dt
        P6 = STATE_PARAMS.get(self._state, STATE_PARAMS["idle"])
        target = math.radians(P6[0])
        k = min(1.0, dt * 3.0)
        self._spin += (target - self._spin) * k
        self._angle += self._spin * dt
        self._glow += (np.array(P6[5]) - self._glow) * k
        self.update()

    # ---- paint ----
    def paintEvent(self, _event):
        if self._dead or self.P is None or len(self.F) == 0:
            return
        p6 = STATE_PARAMS.get(self._state, STATE_PARAMS["idle"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            p.end()
            return
        cx, cy = w / 2.0, h / 2.0
        bob = math.sin(self._t * p6[2]) * p6[1] * h
        pulse = 1.0 + p6[4] * math.sin(self._t * 3.0)
        if self._state == "success":
            pulse *= 1.0 + 0.08 * abs(math.sin(self._t * 5.0))

        # transform: scale -> rotate Y -> tilt Z -> translate to camera
        P = self.P * (0.9 * pulse)
        a = math.radians(self._angle)
        ca, sa = math.cos(a), math.sin(a)
        R = np.array([[ca, 0.0, sa], [0.0, 1.0, 0.0], [-sa, 0.0, ca]], dtype=np.float32)
        P = P @ R.T
        tilt = math.radians(p6[3]) * math.sin(self._t * p6[2] * 0.6)
        ct, st = math.cos(tilt), math.sin(tilt)
        Rz = np.array([[ct, -st, 0.0], [st, ct, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
        P = P @ Rz.T
        P[:, 1] += bob / max(1.0, h)

        # perspective
        dist = 3.0
        f = min(w, h) * 1.15
        z = P[:, 2] - dist
        ok = z < -0.05
        if not ok.any():
            p.end()
            return
        safe = np.where(ok, z, -1.0)
        sx = cx + (P[:, 0] / safe) * f
        sy = cy - (P[:, 1] / safe) * f
        depth = np.where(ok, safe, 1.0)

        tri = self.F
        z0 = depth[tri[:, 0]]
        z1 = depth[tri[:, 1]]
        z2 = depth[tri[:, 2]]
        front = ok[tri].all(axis=1) & (z0 < z1) & (z1 < z2)
        if not front.any():
            p.end()
            return
        tri = tri[front]

        # face normals in view space for lambert shading
        v0 = P[tri[:, 0]]
        v1 = P[tri[:, 1]]
        v2 = P[tri[:, 2]]
        n = np.cross(v1 - v0, v2 - v0)
        ln = np.linalg.norm(n, axis=1) + 1e-9
        n = n / ln[:, None]
        L = np.array([0.45, 0.75, 0.55], dtype=np.float32)
        L /= np.linalg.norm(L)
        diff = np.clip(n @ L, 0.0, 1.0)
        # cull back faces
        vis = n[:, 2] < 0.02
        if not vis.any():
            p.end()
            return
        tri_v = tri[vis]
        diff = diff[vis]

        base = self.C[tri_v].mean(axis=1)
        light = 0.34 + 0.78 * diff[:, None]
        rgb = np.clip(base * light + self._glow * (0.10 + p6[4] * 2.0), 0.0, 1.0)

        # painter's algorithm: far to near
        order = np.argsort(-depth[tri_v].mean(axis=1))
        coords = np.stack([sx, sy], axis=1)
        p.setPen(Qt.NoPen)
        for i in order:
            idx = tri_v[i]
            poly = QPolygonF([QPointFLike(coords[idx[0], 0], coords[idx[0], 1]),
                              QPointFLike(coords[idx[1], 0], coords[idx[1], 1]),
                              QPointFLike(coords[idx[2], 0], coords[idx[2], 1])])
            c = rgb[i]
            p.setBrush(QBrush(QColor.fromRgbF(float(c[0]), float(c[1]), float(c[2]))))
            p.drawPolygon(poly)
        p.end()


def QPointFLike(x, y):
    from PySide6.QtCore import QPointF
    return QPointF(float(x), float(y))


def _load_model(path: Path):
    """Accept .json (pre-decimated) or .obj (decimated on the fly)."""
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        P = np.asarray(data["positions"], dtype=np.float32)
        C = np.asarray(data["colors"], dtype=np.float32)
        F = np.asarray(data["faces"], dtype=np.int32)
        return P, C, F
    if path.suffix.lower() == ".obj":
        from PySide6.QtCore import QThread  # noqa: F401  (kept for clarity)
        P, C, F = _decimate_obj_live(path)
        return P, C, F
    raise ValueError(f"unsupported model: {path.suffix}")


def _decimate_obj_live(path: Path, target: int = 2600):
    verts = []
    faces = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3]),
                              float(p[4]) if len(p) >= 7 else 0.8,
                              float(p[5]) if len(p) >= 7 else 0.8,
                              float(p[6]) if len(p) >= 7 else 0.8))
            elif line.startswith("f "):
                p = line.split()[1:4]
                faces.append((int(p[0].split("/")[0]) - 1,
                              int(p[1].split("/")[0]) - 1,
                              int(p[2].split("/")[0]) - 1))
    V = np.asarray(verts, dtype=np.float32)
    T = np.asarray(faces, dtype=np.int32)
    for grid in (64, 48, 32, 24, 16):
        rng = np.ptp(V[:, :3], axis=0) + 1e-9
        keys = np.floor((V[:, :3] - V[:, :3].min(0)) / rng * grid).astype(np.int32)
        _, inv = np.unique(keys, axis=0, return_inverse=True)
        remap = inv[T]
        keep = ((remap[:, 0] != remap[:, 1]) & (remap[:, 1] != remap[:, 2])
                & (remap[:, 0] != remap[:, 2]))
        FT = remap[keep]
        if len(FT) <= target:
            break
    used, inv = np.unique(FT.reshape(-1), return_inverse=True)
    return V[used][:, :3], V[used][:, 3:6], inv.reshape(-1, 3).astype(np.int32)
