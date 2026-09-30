"""Software-rasterized 3D character view (QPainter + numpy).

Supports: .glb / .gltf, .obj (+ .mtl, textures), and the pre-decimated .json.

Fixes vs. the previous version (why nothing was visible):
  1. A bogus filter `(z0 < z1) & (z1 < z2)` threw away ~5/6 of all triangles.
  2. Back-face culling assumed a winding order; the wrong guess = culled everything.
     Winding is now auto-detected once at load time.
  3. Painter's-algorithm order was reversed (near drawn first, far on top).
  4. Model was never normalised -> a GLB in cm/mm/m units was huge or tiny and
     fell outside the camera. Now auto-centered and auto-scaled to fit.
  5. OBJ decimation indexed the wrong array (cluster ids used as vertex ids)
     and only read the first 3 vertices of quads. Rewritten.
  6. Spin angle was converted deg->rad twice.

Standalone test (dark window, prints stats):
    python -m overlay.model_view3d path/to/model.glb
"""
from __future__ import annotations

import base64
import json
import math
import struct
import time
from pathlib import Path
from urllib.parse import unquote

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF
from PySide6.QtWidgets import QWidget

STATUS_LABELS = {
    "idle": "", "listening": "🎤 listening…", "thinking": "💭 thinking…",
    "executing": "⚙ working…", "success": "✅ done!", "error": "❌ failed",
    "waiting_for_user": "", "speaking": "🔊 speaking…", "sleeping": "💤 paused",
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

    MAX_FACES = 8000        # lower = faster (Python draws every triangle)
    CULL_BACKFACES = True   # set False if your mesh has inconsistent winding

    def __init__(self, model_path: Path, parent=None, fps: int = 30):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._dead = False
        self._reported = False

        P, C, F = load_model(Path(model_path), self.MAX_FACES)
        P, C, F = _clean(P, C, F)
        if len(F) == 0 or len(P) == 0:
            raise ValueError("model has no usable triangles")

        # center on bbox + normalise to radius 1 (any source unit works)
        P = P.astype(np.float64)
        P -= (P.min(axis=0) + P.max(axis=0)) / 2.0
        radius = float(np.linalg.norm(P, axis=1).max())
        if radius < 1e-12:
            raise ValueError("model is degenerate (zero size)")
        P /= radius
        F = _fix_winding(P, F)

        self.P = P.astype(np.float32)
        self.C = np.clip(C, 0.0, 1.0).astype(np.float32)
        self.F = F.astype(np.int32)
        print(f"[ModelView3D] {Path(model_path).name}: {len(self.P)} verts, "
              f"{len(self.F)} tris, original radius {radius:.4g}")

        self._L = np.array([0.40, 0.60, 0.70], dtype=np.float32)
        self._L /= np.linalg.norm(self._L)

        self._state = "idle"
        self._angle = 0.0      # degrees
        self._spin = 25.0      # deg/s
        self._t = 0.0
        self._last = time.monotonic()
        self._glow = np.array([0.31, 0.78, 1.0], dtype=np.float32)
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
        if self._dead:
            return
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        self._t += dt
        st = STATE_PARAMS.get(self._state, STATE_PARAMS["idle"])
        k = min(1.0, dt * 3.0)
        self._spin += (st[0] - self._spin) * k
        self._angle = (self._angle + self._spin * dt) % 360.0
        self._glow += (np.array(st[5], dtype=np.float32) - self._glow) * k
        self.update()

    def _fail(self, msg: str):
        self._dead = True
        self._timer.stop()
        QTimer.singleShot(0, lambda: self.load_failed.emit(msg))

    # ---- paint ----
    def paintEvent(self, _event):
        if self._dead:
            return
        p = QPainter(self)
        try:
            self._draw(p)
        except Exception as exc:  # never crash inside paintEvent
            import traceback
            traceback.print_exc()
            self._fail(f"render error: {exc!r}")
        finally:
            p.end()

    def _draw(self, p: QPainter):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        p.setRenderHint(QPainter.Antialiasing, True)
        st = STATE_PARAMS.get(self._state, STATE_PARAMS["idle"])
        t = self._t

        pulse = 1.0 + st[4] * math.sin(t * 3.0)
        if self._state == "success":
            pulse *= 1.0 + 0.08 * abs(math.sin(t * 5.0))
        bob = math.sin(t * st[2]) * st[1] * 1.2
        yaw = math.radians(self._angle)
        tilt = math.radians(st[3]) * math.sin(t * st[2] * 0.6)
        cyw, syw = math.cos(yaw), math.sin(yaw)
        ctl, stl = math.cos(tilt), math.sin(tilt)
        Ry = np.array([[cyw, 0, syw], [0, 1, 0], [-syw, 0, cyw]], dtype=np.float32)
        Rz = np.array([[ctl, -stl, 0], [stl, ctl, 0], [0, 0, 1]], dtype=np.float32)
        M = Rz @ Ry
        P = (self.P * pulse) @ M.T
        P[:, 1] += bob

        # camera at z=+dist looking down -Z (view space z is negative ahead)
        dist = 5.0
        f = 0.36 * min(w, h) * dist
        cx, cy = w * 0.5, h * 0.46
        z = P[:, 2] - dist
        d = -z                                   # positive distance, bigger = farther
        sx = cx + P[:, 0] / d * f
        sy = cy - P[:, 1] / d * f                # Y up
        V = np.stack([P[:, 0], P[:, 1], z], axis=1)

        tri = self.F
        v0, v1, v2 = V[tri[:, 0]], V[tri[:, 1]], V[tri[:, 2]]
        n = np.cross(v1 - v0, v2 - v0)
        facing = -(n * v0).sum(axis=1)           # dot(normal, toward-camera)
        n /= (np.linalg.norm(n, axis=1) + 1e-12)[:, None]
        if self.CULL_BACKFACES:
            vis = facing > 0
        else:
            vis = np.ones(len(tri), dtype=bool)
            n[facing < 0] *= -1.0
        if not vis.any():
            return
        tri, n = tri[vis], n[vis]

        diff = np.clip(n @ self._L, 0.0, 1.0)
        base = np.maximum(self.C[tri].mean(axis=1), 0.10)
        light = 0.38 + 0.72 * diff
        rgb = np.clip(base * light[:, None] + self._glow * (0.08 + st[4] * 1.5), 0.0, 1.0)
        rgb255 = (rgb * 255).astype(np.int32).tolist()

        order = np.argsort(-d[tri].mean(axis=1)).tolist()   # far -> near
        pts = np.stack([sx, sy], axis=1).tolist()
        tri_l = tri.tolist()

        if not self._reported:
            self._reported = True
            print(f"[ModelView3D] first frame: drawing {len(order)}/{len(self.F)} triangles "
                  f"in {w}x{h}")

        for i in order:
            a, b, c = tri_l[i]
            col = QColor(*rgb255[i])
            p.setBrush(col)
            p.setPen(col)            # same-color outline hides AA seams between triangles
            p.drawPolygon(QPolygonF([QPointF(*pts[a]), QPointF(*pts[b]), QPointF(*pts[c])]))


# =====================================================================
# mesh helpers
# =====================================================================
def _clean(P, C, F):
    P = np.asarray(P, dtype=np.float64)
    C = np.asarray(C, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    if len(C) != len(P):
        C = np.full((len(P), 3), 0.8)
    good_v = np.isfinite(P).all(axis=1)
    F = F[(F >= 0).all(axis=1) & (F < len(P)).all(axis=1)]
    F = F[good_v[F].all(axis=1)]
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    if len(F):
        F = np.unique(F, axis=0)
    return P, C, F


def _fix_winding(P, F):
    """Make triangles wind counter-clockwise when seen from outside."""
    v0, v1, v2 = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)                 # |n| = 2*area -> area weighted
    outward = (n * ((v0 + v1 + v2) / 3.0)).sum()   # P is centered at origin
    if outward < 0:
        F = F[:, ::-1]
    return np.ascontiguousarray(F)


def _decimate(P, C, F, target):
    """Vertex-clustering decimation (cluster centroids, correct re-indexing)."""
    if len(F) <= target:
        return P, C, F
    mn = P.min(axis=0)
    ext = float((P.max(axis=0) - mn).max()) + 1e-12
    out = (P, C, F)
    for grid in (192, 160, 128, 96, 80, 64, 48, 40, 32, 24, 16, 12, 8):
        q = np.floor((P - mn) / ext * (grid - 1e-3)).astype(np.int64)
        key = (q[:, 0] * grid + q[:, 1]) * grid + q[:, 2]
        uniq, inv = np.unique(key, return_inverse=True)
        inv = inv.reshape(-1)
        cnt = np.bincount(inv, minlength=len(uniq)).astype(np.float64)
        P2 = np.stack([np.bincount(inv, P[:, k], minlength=len(uniq)) / cnt for k in range(3)], 1)
        C2 = np.stack([np.bincount(inv, C[:, k], minlength=len(uniq)) / cnt for k in range(3)], 1)
        F2 = inv[F]
        keep = (F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])
        F2 = np.unique(F2[keep], axis=0) if keep.any() else F2[keep]
        out = (P2, C2, F2)
        if len(F2) <= target:
            break
    return out


def _image_to_array(raw: bytes | str | Path):
    img = QImage.fromData(raw) if isinstance(raw, (bytes, bytearray)) else QImage(str(raw))
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format_RGBA8888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    arr = np.frombuffer(img.constBits(), dtype=np.uint8, count=bpl * h).reshape(h, bpl)
    return arr[:, : w * 4].reshape(h, w, 4).copy()


def _sample(tex, u, v, flip_v):
    hh, ww = tex.shape[:2]
    u = np.mod(u, 1.0)
    v = np.mod(v, 1.0)
    if flip_v:
        v = 1.0 - v
    x = np.clip((u * (ww - 1)).round().astype(int), 0, ww - 1)
    y = np.clip((v * (hh - 1)).round().astype(int), 0, hh - 1)
    return tex[y, x, :3].astype(np.float64) / 255.0


# =====================================================================
# loaders
# =====================================================================
def load_model(path: Path, target_faces: int = 2500):
    ext = path.suffix.lower()
    if ext == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        P = np.asarray(data["positions"], dtype=np.float64)
        C = np.asarray(data["colors"], dtype=np.float64)
        F = np.asarray(data["faces"], dtype=np.int64)
    elif ext in (".glb", ".gltf"):
        P, C, F = _load_gltf(path)
    elif ext == ".obj":
        P, C, F = _load_obj(path)
    else:
        raise ValueError(f"unsupported model format: {ext}")
    P, C, F = _clean(P, C, F)
    return _decimate(P, C, F, target_faces)


# ---------------- glTF / GLB ----------------
_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16,
       5125: np.uint32, 5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class _Gltf:
    def __init__(self, path: Path):
        self.base = path.parent
        data = path.read_bytes()
        self._glb_bin = b""
        if data[:4] == b"glTF":
            off = 12
            while off + 8 <= len(data):
                clen, ctype = struct.unpack_from("<II", data, off)
                chunk = data[off + 8: off + 8 + clen]
                if ctype == 0x4E4F534A:
                    self.j = json.loads(chunk.decode("utf-8"))
                elif ctype == 0x004E4942 and not self._glb_bin:
                    self._glb_bin = chunk
                off += 8 + clen
        else:
            self.j = json.loads(data.decode("utf-8"))
        self._bufs: dict[int, bytes] = {}
        self._tex: dict[int, object] = {}

    def _read_uri(self, uri: str) -> bytes:
        if uri.startswith("data:"):
            return base64.b64decode(uri.split(",", 1)[1])
        return (self.base / unquote(uri)).read_bytes()

    def buffer(self, i: int) -> bytes:
        if i not in self._bufs:
            b = self.j["buffers"][i]
            self._bufs[i] = self._read_uri(b["uri"]) if "uri" in b else self._glb_bin
        return self._bufs[i]

    def accessor(self, idx: int) -> np.ndarray:
        a = self.j["accessors"][idx]
        dt = np.dtype(_CT[a["componentType"]])
        nc, count = _NC[a["type"]], a["count"]
        if "bufferView" in a:
            bv = self.j["bufferViews"][a["bufferView"]]
            buf = self.buffer(bv["buffer"])
            start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
            elsize = dt.itemsize * nc
            stride = bv.get("byteStride") or elsize
            if stride == elsize:
                arr = np.frombuffer(buf, dtype=dt, count=count * nc, offset=start).reshape(count, nc)
            else:
                raw = np.frombuffer(buf, dtype=np.uint8, count=stride * (count - 1) + elsize, offset=start)
                arr = np.lib.stride_tricks.as_strided(
                    raw, shape=(count, elsize), strides=(stride, 1)).copy().view(dt).reshape(count, nc)
        else:
            arr = np.zeros((count, nc), dtype=dt)
        if a.get("normalized") and dt.kind in "iu":
            arr = np.clip(arr.astype(np.float64) / np.iinfo(dt).max, -1.0, 1.0)
        return arr

    def texture(self, tex_index: int):
        if tex_index in self._tex:
            return self._tex[tex_index]
        arr = None
        try:
            src = self.j["textures"][tex_index].get("source")
            im = self.j["images"][src]
            if "bufferView" in im:
                bv = self.j["bufferViews"][im["bufferView"]]
                buf = self.buffer(bv["buffer"])
                o = bv.get("byteOffset", 0)
                arr = _image_to_array(bytes(buf[o: o + bv["byteLength"]]))
            elif "uri" in im:
                arr = _image_to_array(self._read_uri(im["uri"]))
        except Exception as exc:
            print(f"[ModelView3D] texture {tex_index} skipped: {exc!r}")
        self._tex[tex_index] = arr
        return arr


def _node_matrix(node) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    R = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4)
    M[:3, :3] = R @ np.diag(node.get("scale", [1, 1, 1]))
    M[:3, 3] = node.get("translation", [0, 0, 0])
    return M


def _load_gltf(path: Path):
    g = _Gltf(path)
    j = g.j
    nodes = j.get("nodes", [])
    Ps, Cs, Fs = [], [], []
    offset = 0

    def add_mesh(mesh, M):
        nonlocal offset
        for prim in mesh.get("primitives", []):
            attrs = prim.get("attributes", {})
            if prim.get("mode", 4) != 4 or "POSITION" not in attrs:
                continue
            pos = g.accessor(attrs["POSITION"]).astype(np.float64)[:, :3]
            pos = pos @ M[:3, :3].T + M[:3, 3]
            n = len(pos)
            if "indices" in prim:
                idx = g.accessor(prim["indices"]).reshape(-1).astype(np.int64)
            else:
                idx = np.arange(n, dtype=np.int64)
            idx = idx[: len(idx) // 3 * 3].reshape(-1, 3)
            if np.linalg.det(M[:3, :3]) < 0:
                idx = idx[:, ::-1]

            mat = j["materials"][prim["material"]] if "material" in prim and "materials" in j else {}
            pbr = mat.get("pbrMetallicRoughness", {})
            basef = np.array(pbr.get("baseColorFactor", [1, 1, 1, 1]), dtype=np.float64)[:3]
            col = None
            if "COLOR_0" in attrs:
                col = g.accessor(attrs["COLOR_0"]).astype(np.float64)[:, :3] * basef
            elif "baseColorTexture" in pbr and "TEXCOORD_0" in attrs:
                tex = g.texture(pbr["baseColorTexture"]["index"])
                if tex is not None:
                    uv = g.accessor(attrs["TEXCOORD_0"]).astype(np.float64)
                    col = _sample(tex, uv[:, 0], uv[:, 1], flip_v=False) * basef
            if col is None:
                col = np.tile(basef, (n, 1))
            Ps.append(pos)
            Cs.append(col)
            Fs.append(idx + offset)
            offset += n

    def walk(i, parent):
        node = nodes[i]
        M = parent @ _node_matrix(node)
        if "mesh" in node:
            add_mesh(j["meshes"][node["mesh"]], M)
        for ch in node.get("children", []):
            walk(ch, M)

    if "scenes" in j and j["scenes"]:
        roots = j["scenes"][j.get("scene", 0)].get("nodes", [])
    else:
        kids = {c for nd in nodes for c in nd.get("children", [])}
        roots = [i for i in range(len(nodes)) if i not in kids]
    for r in roots:
        walk(r, np.eye(4))

    if not Ps:
        raise ValueError("no triangle meshes found in glTF")
    return np.concatenate(Ps), np.concatenate(Cs), np.concatenate(Fs)


# ---------------- OBJ ----------------
def _load_obj(path: Path):
    V, VC, VT = [], [], []
    fv, ft, fm = [], [], []
    mats: list[tuple[np.ndarray, object]] = []
    mat_ids: dict[str, int] = {}
    mtl_defs: dict[str, tuple[np.ndarray, object]] = {}
    cur = -1

    def read_mtl(mpath: Path):
        if not mpath.exists():
            return
        name, kd, tex = None, np.array([0.8, 0.8, 0.8]), None
        for line in mpath.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip().split()
            if not s:
                continue
            k = s[0].lower()
            if k == "newmtl":
                if name is not None:
                    mtl_defs[name] = (kd, tex)
                name, kd, tex = " ".join(s[1:]), np.array([0.8, 0.8, 0.8]), None
            elif k == "kd" and len(s) >= 4:
                kd = np.array([float(s[1]), float(s[2]), float(s[3])])
            elif k == "map_kd" and len(s) >= 2:
                rel = s[-1].replace("\\", "/")
                cand = mpath.parent / rel
                if not cand.exists():
                    cand = mpath.parent / Path(rel).name
                if cand.exists():
                    tex = _image_to_array(cand)
        if name is not None:
            mtl_defs[name] = (kd, tex)

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                V.append((float(p[1]), float(p[2]), float(p[3])))
                if len(p) >= 7:
                    VC.append((float(p[4]), float(p[5]), float(p[6])))
            elif line.startswith("vt "):
                p = line.split()
                VT.append((float(p[1]), float(p[2])))
            elif line.startswith("f "):
                toks = line.split()[1:]
                if len(toks) < 3:
                    continue
                vi, ti = [], []
                for tk in toks:
                    a = tk.split("/")
                    v = int(a[0])
                    vi.append(v - 1 if v > 0 else len(V) + v)
                    if len(a) > 1 and a[1]:
                        t_ = int(a[1])
                        ti.append(t_ - 1 if t_ > 0 else len(VT) + t_)
                    else:
                        ti.append(-1)
                for k in range(1, len(vi) - 1):          # fan triangulation (quads, n-gons)
                    fv.append((vi[0], vi[k], vi[k + 1]))
                    ft.append((ti[0], ti[k], ti[k + 1]))
                    fm.append(cur)
            elif line.startswith("mtllib"):
                read_mtl(path.parent / line.split(None, 1)[1].strip())
            elif line.startswith("usemtl"):
                name = line.split(None, 1)[1].strip()
                if name not in mat_ids:
                    mat_ids[name] = len(mats)
                    mats.append(mtl_defs.get(name, (np.array([0.8, 0.8, 0.8]), None)))
                cur = mat_ids[name]

    if not V or not fv:
        raise ValueError("OBJ has no geometry")
    P = np.asarray(V, dtype=np.float64)
    F = np.asarray(fv, dtype=np.int64)

    if len(VC) == len(V):
        C = np.asarray(VC, dtype=np.float64)
        return P, C, F

    T = np.asarray(ft, dtype=np.int64)
    M = np.asarray(fm, dtype=np.int64)
    VTa = np.asarray(VT, dtype=np.float64) if VT else np.zeros((0, 2))
    acc = np.zeros((len(P), 3))
    cnt = np.zeros(len(P))
    for m in np.unique(M):
        sel = M == m
        kd, tex = mats[m] if m >= 0 else (np.array([0.8, 0.8, 0.8]), None)
        for k in range(3):
            vi = F[sel, k]
            colors = np.tile(kd, (len(vi), 1))
            if tex is not None and len(VTa):
                ti = T[sel, k]
                ok = (ti >= 0) & (ti < len(VTa))
                if ok.any():
                    uv = VTa[ti[ok]]
                    colors[ok] = _sample(tex, uv[:, 0], uv[:, 1], flip_v=True)
            np.add.at(acc, vi, colors)
            np.add.at(cnt, vi, 1.0)
    C = np.where(cnt[:, None] > 0, acc / np.maximum(cnt, 1.0)[:, None], 0.8)
    return P, C, F


# =====================================================================
# standalone debug:  python -m overlay.model_view3d model.glb
# =====================================================================
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    box = QWidget()
    box.setStyleSheet("background:#1b1f27")
    box.resize(320, 320)
    view = ModelView3D(Path(sys.argv[1]), box)
    view.setGeometry(0, 0, 320, 320)
    view.load_failed.connect(lambda m: print("FAILED:", m))
    box.show()
    sys.exit(app.exec())
