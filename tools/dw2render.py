"""Software preview of DW2 models (numpy + Pillow): poses a model with an animation frame and
draws it textured, as a check that the format reading is right.

    python dw2render.py <dir of extracted files> <model file id hex> <anim file id hex> [anim#] out.gif
"""
import math
import sys

import numpy as np
from PIL import Image

import dw2model


def bone_worlds(model, animfile=None, frame=None):
    """World (3x3 float, translation) per bone for an animation frame (None = rest)."""
    out = []
    for i, b in enumerate(model.bones):
        if animfile is not None and frame is not None:
            p = animfile.pose_matrix(i, frame[i])
            R = np.array(p.m, dtype=float) / 4096.0
            t = np.array(p.t, dtype=float)
        else:
            R = np.eye(3)
            t = np.zeros(3)
        if b.parent >= 0:
            PR, Pt = out[b.parent]
            R, t = PR @ R, PR @ t + Pt
        out.append((R, t))
    return out


def palette_for(tim, clut, clut_row=0):
    """The 16 (4 bit) or 256 (8 bit) colours a face uses. The game uploads only the image: a
    face's clut points inside it (row clut >> 6, halfword x (clut & 0x3F) * 16)."""
    n = 16 if tim.bpp_mode == 0 else 256
    pal = np.zeros((n, 4), dtype=np.uint8)
    y = (clut >> 6) + clut_row
    x = (clut & 0x3F) * 16
    iw, ih = tim.img_rect[2], tim.img_rect[3]
    for i in range(n):
        if y < ih and x + i < iw:
            c = int.from_bytes(tim.pix[(y * iw + x + i) * 2:(y * iw + x + i) * 2 + 2], "little")
            pal[i] = dw2model.Tim.color(c)
    return pal


def index_image(tim):
    img = np.zeros((tim.height, tim.width), dtype=np.int32)
    raw = np.frombuffer(tim.pix, dtype=np.uint8).reshape(tim.height, -1)
    if tim.bpp_mode == 0:
        img[:, 0::2] = raw & 15
        img[:, 1::2] = raw >> 4
    elif tim.bpp_mode == 1:
        img[:, :] = raw[:, :tim.width]
    return img


def render(model, worlds, size=320, yaw=0.0, pitch=0.25, light=True, bg=(40, 44, 52)):
    tim = model.tim
    idx = index_image(tim)
    pals = {}
    tris = []
    for bi, b in enumerate(model.bones):
        R, t = worlds[bi]
        V = np.array(b.verts, dtype=float).reshape(-1, 3) @ R.T + t if b.verts else np.zeros((0, 3))
        N = (np.array(b.normals, dtype=float).reshape(-1, 3) / 4096.0) @ R.T if b.normals else None
        for f in b.faces:
            if f.clut not in pals:
                pals[f.clut] = palette_for(tim, f.clut)
            order = [(0, 1, 2), (1, 3, 2)] if len(f.verts) == 4 else [(0, 1, 2)]
            for a, c, d in order:
                k = (a, c, d)
                vv = [V[f.verts[j]] for j in k]
                nn = [N[f.norms[j]] if N is not None and f.norms[j] < len(N) else np.array([0, -1, 0])
                      for j in k]
                uv = [f.uvs[j] for j in k]
                tris.append((vv, nn, uv, f.clut))
    if not tris:
        return Image.new("RGB", (size, size), bg)
    allv = np.array([v for t in tris for v in t[0]])
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    view = Rx @ Ry
    centre = (allv.max(0) + allv.min(0)) / 2
    pts = (allv - centre) @ view.T
    ext = np.abs(pts[:, :2]).max() * 1.15 + 1
    scale = size / 2 / ext
    zbuf = np.full((size, size), np.inf)
    col = np.zeros((size, size, 3), dtype=float)
    col[:] = bg
    L = np.array([0.3, -0.8, -0.5])
    L = L / np.linalg.norm(L)
    for vv, nn, uv, clut in tris:
        P = (np.array(vv) - centre) @ view.T
        sx = size / 2 + P[:, 0] * scale
        sy_ = size / 2 + P[:, 1] * scale      # PS1 y points down: screen y down too
        z = P[:, 2]
        # back-face cull (game culls by screen winding)
        area = (sx[1] - sx[0]) * (sy_[2] - sy_[0]) - (sx[2] - sx[0]) * (sy_[1] - sy_[0])
        if area <= 0:
            continue
        x0, x1 = int(max(0, math.floor(sx.min()))), int(min(size - 1, math.ceil(sx.max())))
        y0, y1 = int(max(0, math.floor(sy_.min()))), int(min(size - 1, math.ceil(sy_.max())))
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((sx[1] - xs) * (sy_[2] - ys) - (sx[2] - xs) * (sy_[1] - ys)) / area
        w1 = ((sx[2] - xs) * (sy_[0] - ys) - (sx[0] - xs) * (sy_[2] - ys)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        zz = w0 * z[0] + w1 * z[1] + w2 * z[2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        m = inside & (zz < sub)
        if not m.any():
            continue
        u = w0 * uv[0][0] + w1 * uv[1][0] + w2 * uv[2][0]
        v = w0 * uv[0][1] + w1 * uv[1][1] + w2 * uv[2][1]
        ui = np.clip(u.astype(int), 0, tim.width - 1)
        vi = np.clip(v.astype(int), 0, tim.height - 1)
        texel = pals[clut][idx[vi, ui]]
        m &= texel[..., 3] > 0
        if light:
            shades = []
            for n in nn:
                n = np.asarray(n, dtype=float)
                ln = np.linalg.norm(n)
                d = max(0.0, -float((n / ln) @ L)) if ln > 0 else 0.5
                shades.append(0.45 + 0.75 * d)
            sh = w0 * shades[0] + w1 * shades[1] + w2 * shades[2]
        else:
            sh = np.ones_like(w0)
        rgb = texel[..., :3] * np.clip(sh, 0, 1.4)[..., None]
        sub[m] = zz[m]
        col[y0:y1 + 1, x0:x1 + 1][m] = np.clip(rgb[m], 0, 255)
    return Image.fromarray(col.astype(np.uint8), "RGB")


def main():
    import os
    d, mid, aid = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
    an = int(sys.argv[4]) if len(sys.argv) > 5 else 0
    out = sys.argv[-1]
    model = dw2model.Model.parse(open(os.path.join(d, "%04X.bin" % mid), "rb").read())
    af = dw2model.AnimFile.parse(open(os.path.join(d, "%04X.bin" % aid), "rb").read(), len(model.bones))
    anim = af.anims[an]
    frames = []
    for fr in anim.frames:
        frames.append(render(model, bone_worlds(model, af, fr), yaw=0.6))
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=33, loop=0)


if __name__ == "__main__":
    main()
