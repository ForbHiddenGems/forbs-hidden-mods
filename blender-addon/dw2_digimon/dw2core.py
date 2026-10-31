"""Game <-> Blender conversion for DW2 Digimon, without Blender (the add-on's glue turns the
results into Blender data and back). Pure Python, so it can be tested anywhere.

Coordinates: game (x, y, z) with y down and the Digimon facing -z becomes Blender
(x, z, -y) / SCALE: z up, facing -y (Blender's front view), 1 Blender unit = 1000 game units.

Bones: a game bone's frame is its world matrix; vertices are stored in that frame. In Blender
each bone's rest matrix (armature space) is the game frame at the rest pose times a fixed
per-bone turn that points the bone at its child (display only). On export, whatever the Blender
bone frames are become the game frames, so models made or changed in Blender export as they are.
"""
import math
import struct

try:
    from . import dw2model
except ImportError:
    import dw2model

SCALE = 1000.0

# ---------------------------------------------------------------- small matrix maths (4x4 lists)


def ident():
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def mulv(a, v):
    return [a[i][0] * v[0] + a[i][1] * v[1] + a[i][2] * v[2] + a[i][3] for i in range(3)]


def rotv(a, v):
    return [a[i][0] * v[0] + a[i][1] * v[1] + a[i][2] * v[2] for i in range(3)]


def inv(m):
    """Inverse of an affine 4x4 (general 3x3 part)."""
    a = [row[:3] for row in m[:3]]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
           - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    if abs(det) < 1e-12:
        det = 1e-12
    c = [[0.0] * 3 for _ in range(3)]
    c[0][0] = (a[1][1] * a[2][2] - a[1][2] * a[2][1]) / det
    c[0][1] = (a[0][2] * a[2][1] - a[0][1] * a[2][2]) / det
    c[0][2] = (a[0][1] * a[1][2] - a[0][2] * a[1][1]) / det
    c[1][0] = (a[1][2] * a[2][0] - a[1][0] * a[2][2]) / det
    c[1][1] = (a[0][0] * a[2][2] - a[0][2] * a[2][0]) / det
    c[1][2] = (a[0][2] * a[1][0] - a[0][0] * a[1][2]) / det
    c[2][0] = (a[1][0] * a[2][1] - a[1][1] * a[2][0]) / det
    c[2][1] = (a[0][1] * a[2][0] - a[0][0] * a[2][1]) / det
    c[2][2] = (a[0][0] * a[1][1] - a[0][1] * a[1][0]) / det
    t = [m[0][3], m[1][3], m[2][3]]
    it = [-(c[i][0] * t[0] + c[i][1] * t[1] + c[i][2] * t[2]) for i in range(3)]
    return [c[0] + [it[0]], c[1] + [it[1]], c[2] + [it[2]], [0.0, 0.0, 0.0, 1.0]]


# game <-> Blender axes: blender = C @ game, C = [[1,0,0],[0,0,1],[0,-1,0]]
C = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]


def g2b_point(p):
    return [p[0] / SCALE, p[2] / SCALE, -p[1] / SCALE]


def b2g_point(p):
    return [p[0] * SCALE, -p[2] * SCALE, p[1] * SCALE]


def g2b_dir(d):
    return [d[0], d[2], -d[1]]


def b2g_dir(d):
    return [d[0], -d[2], d[1]]


def g2b_mat(R, t):
    """Game frame (3x3 rotation as floats, translation in game units) -> Blender 4x4."""
    # M_b = C R C^T ; t_b = C t / SCALE
    Ct = [[C[j][i] for j in range(3)] for i in range(3)]
    CR = [[sum(C[i][k] * R[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    M = [[sum(CR[i][k] * Ct[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    tb = g2b_point(t)
    return [M[0] + [tb[0]], M[1] + [tb[1]], M[2] + [tb[2]], [0.0, 0.0, 0.0, 1.0]]


def b2g_mat(m):
    """Blender 4x4 -> (game 3x3 floats, game translation)."""
    R3 = [row[:3] for row in m[:3]]
    Ct = [[C[j][i] for j in range(3)] for i in range(3)]
    tmp = [[sum(Ct[i][k] * R3[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    R = [[sum(tmp[i][k] * C[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    t = b2g_point([m[0][3], m[1][3], m[2][3]])
    return R, t


def game_local(pose):
    R = [[c / 4096.0 for c in row] for row in pose.m]
    return R, list(pose.t)


def compose(parent, local):
    PR, Pt = parent
    R, t = local
    R2 = [[sum(PR[i][k] * R[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    t2 = [sum(PR[i][k] * t[k] for k in range(3)) + Pt[i] for i in range(3)]
    return R2, t2


def worlds(model, af=None, frame=None):
    out = []
    for i, b in enumerate(model.bones):
        if af is not None and frame is not None:
            loc = game_local(af.pose_matrix(i, frame[i]))
        else:
            loc = ([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]], [0.0, 0.0, 0.0])
        out.append(compose(out[b.parent], loc) if b.parent >= 0 else loc)
    return out


def rot_between(a, b):
    """3x3 rotation turning unit vector a onto unit vector b."""
    ax = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    s = math.sqrt(sum(x * x for x in ax))
    c = sum(a[i] * b[i] for i in range(3))
    if s < 1e-9:
        if c > 0:
            return [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
        # opposite: half turn about any axis normal to a
        p = [1.0, 0, 0] if abs(a[0]) < 0.9 else [0, 1.0, 0]
        ax = [a[1] * p[2] - a[2] * p[1], a[2] * p[0] - a[0] * p[2], a[0] * p[1] - a[1] * p[0]]
        s = math.sqrt(sum(x * x for x in ax))
        ax = [x / s for x in ax]
        return [[2 * ax[i] * ax[j] - (1.0 if i == j else 0.0) for j in range(3)] for i in range(3)]
    k = [x / s for x in ax]
    ang = math.atan2(s, c)
    cs, sn = math.cos(ang), math.sin(ang)
    K = [[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]]
    KK = [[sum(K[i][m] * K[m][j] for m in range(3)) for j in range(3)] for i in range(3)]
    return [[(1.0 if i == j else 0.0) + sn * K[i][j] + (1 - cs) * KK[i][j] for j in range(3)]
            for i in range(3)]


def axis_turn(d):
    """The quarter-turn rotation (one of 24) taking +Y nearest to direction d. Only quarter
    turns: a bone's own axes then stay on the game frame's axes, so the stretch and squash the
    game animates along those axes stays a plain per-axis scale in Blender."""
    best = None
    axes = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, 0, 0], [0, -1, 0], [0, 0, -1]]
    for a in axes:
        for b in axes:
            if abs(sum(a[k] * b[k] for k in range(3))) > 0:
                continue
            c = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
            # columns: X axis -> b, Y axis -> a, Z axis -> c (proper rotation)
            c = [b[1] * a[2] - b[2] * a[1], b[2] * a[0] - b[0] * a[2], b[0] * a[1] - b[1] * a[0]]
            score = sum(a[k] * d[k] for k in range(3))
            if best is None or score > best[0] + 1e-9:
                best = (score, [[b[r], a[r], c[r]] for r in range(3)])
    return [[float(v) for v in row] for row in best[1]]


def polar(R):
    """Nearest rotation to R (drops scale): Gram-Schmidt on the columns."""
    c0 = _norm([R[r][0] for r in range(3)])
    c1 = [R[r][1] for r in range(3)]
    d = sum(c0[k] * c1[k] for k in range(3))
    c1 = _norm([c1[k] - d * c0[k] for k in range(3)])
    c2 = [c0[1] * c1[2] - c0[2] * c1[1], c0[2] * c1[0] - c0[0] * c1[2], c0[0] * c1[1] - c0[1] * c1[0]]
    return [[c0[r], c1[r], c2[r]] for r in range(3)]


def as4(R):
    return [R[0] + [0.0], R[1] + [0.0], R[2] + [0.0], [0.0, 0.0, 0.0, 1.0]]


# ---------------------------------------------------------------- texture

def tim_halfword(tim, x, y):
    iw = tim.img_rect[2]
    o = (y * iw + x) * 2
    return tim.pix[o] | tim.pix[o + 1] << 8


def clut_colours(tim, clut):
    y, x = clut >> 6, (clut & 0x3F) * 16
    return [tim_halfword(tim, x + i, y) for i in range(16)]


def uv_cover(faces_uv, w, h):
    """{(x, y): owner} for texels inside the UV triangles; faces_uv = [(owner, [(u, v)...])]."""
    own = {}
    for owner, uvs in faces_uv:
        tris = [(0, 1, 2)] if len(uvs) == 3 else [(0, 1, 2), (1, 3, 2)]
        for a, b, c in tris:
            pa, pb, pc = uvs[a], uvs[b], uvs[c]
            x0 = max(0, int(min(pa[0], pb[0], pc[0])))
            x1 = min(w - 1, int(max(pa[0], pb[0], pc[0])))
            y0 = max(0, int(min(pa[1], pb[1], pc[1])))
            y1 = min(h - 1, int(max(pa[1], pb[1], pc[1])))
            area = (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pc[0] - pa[0]) * (pb[1] - pa[1])
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    if area == 0:
                        inside = True
                    else:
                        px, py = x + 0.5, y + 0.5
                        w0 = ((pb[0] - px) * (pc[1] - py) - (pc[0] - px) * (pb[1] - py)) / area
                        w1 = ((pc[0] - px) * (pa[1] - py) - (pa[0] - px) * (pc[1] - py)) / area
                        w2 = 1 - w0 - w1
                        e = 0.02
                        inside = w0 >= -e and w1 >= -e and w2 >= -e
                    if inside:
                        own.setdefault((x, y), owner)
    return own


def texanim_rects(blob):
    """Source and destination rectangles (in pixels, 4 bit) the eye blink / texture animation
    copies, so their texels keep the palette of the faces they end up on.
    -> [((sx, sy, w, h), (dx, dy))]"""
    out = []
    p = 0
    i = 0
    n = len(blob)
    while p + 10 <= n and i < 10:
        dstX, dstY, w, h = blob[p], blob[p + 1], blob[p + 2], blob[p + 3]
        if i >= 2 and dstX in (0xFE, 0xFF):
            break
        if dstX != 0xFF:
            for k in range(0, 6, 2):
                out.append(((blob[p + 4 + k] * 4, blob[p + 5 + k], w * 4, h), (dstX * 4, dstY)))
        p += 10
        i += 1
    if p < n and blob[p] == 0xFE:
        q = p + 1
        for c in range(10):
            if q + 42 > n or blob[q] == 0xFF:
                break
            dx, dy, w, h, dx2, dy2, w2, h2 = blob[q:q + 8]
            uv = blob[q + 10:q + 42]
            for m in range(0, 32, 4):
                out.append(((uv[m] * 4, uv[m + 1], w * 4, h), (dx * 4, dy)))
                out.append(((uv[m + 2] * 4, uv[m + 3], w2 * 4, h2), (dx2 * 4, dy2)))
            q += 42
    return out


def decode_texture(model):
    """The model's 4-bit texture as RGBA rows (top row first), each texel coloured with the
    palette of the faces that use it. -> (w, h, bytearray RGBA), {(x, y): clut}"""
    tim = model.tim
    w, h = tim.width, tim.height
    faces = [(f.clut, f.uvs) for b in model.bones for f in b.faces]
    own = uv_cover(faces, w, h)
    # texels the blink copies onto a face take that face's palette
    for (sx, sy, rw, rh), (dx, dy) in texanim_rects(model.texanim):
        for y in range(rh):
            for x in range(rw):
                o = own.get((dx + x, dy + y))
                if o is not None:
                    own.setdefault((sx + x, sy + y), o)
    counts = {}
    for c, _ in faces:
        counts[c] = counts.get(c, 0) + 1
    common = max(counts, key=counts.get) if counts else 0
    pals = {}
    out = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            c = own.get((x, y), common)
            if c not in pals:
                pals[c] = [dw2model.Tim.color(v) for v in clut_colours(tim, c)]
            col = pals[c][tim.index_at(x, y)]
            o = (y * w + x) * 4
            out[o:o + 4] = bytes(col)
    return w, h, out, own


def rgb15(r, g, b, a=255):
    if a < 128:
        return 0
    v = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
    return v if v else 0x8000      # black that is not transparent: the STP bit


def median_cut(cols, n):
    """Up to n colours for a list of (r, g, b) (with repeats)."""
    if not cols:
        return []
    boxes = [cols]
    while len(boxes) < n:
        best = None
        for i, bx in enumerate(boxes):
            if len(set(bx)) < 2:
                continue
            rng = max(max(c[k] for c in bx) - min(c[k] for c in bx) for k in range(3))
            if best is None or rng > best[0]:
                best = (rng, i)
        if best is None:
            break
        bx = boxes.pop(best[1])
        k = max(range(3), key=lambda k: max(c[k] for c in bx) - min(c[k] for c in bx))
        bx.sort(key=lambda c: c[k])
        m = len(bx) // 2
        boxes += [bx[:m], bx[m:]]
    return [tuple(sum(c[k] for c in bx) // len(bx) for k in range(3)) for bx in boxes if bx]


def encode_texture(w, h, rgba, groups, tim_template, keep_palette_slots, texanim=b"", orig_rgba=None):
    """A new 4-bit TIM from RGBA (top row first, w x h = the template's size).
    groups: [(clut or None, [uv lists of its faces])], one per material.
    keep_palette_slots: use each group's clut location as it is (imported models).
    -> (tim bytes, {group index: clut}, report lines)"""
    report = []
    cover = uv_cover([(gi, uvs) for gi, (_, faces) in enumerate(groups) for uvs in faces], w, h)
    for (sx, sy, rw, rh), (dx, dy) in texanim_rects(texanim):
        for y in range(rh):
            for x in range(rw):
                o = cover.get((dx + x, dy + y))
                if o is not None:
                    cover.setdefault((sx + x, sy + y), o)
    iw = w // 4
    # palette slots: 16 halfwords = 64 texels of one row
    used_rows = set(y for (x, y) in cover)
    cluts = {}
    taken = set()
    for gi, (clut, _) in enumerate(groups):
        if keep_palette_slots and clut is not None:
            cluts[gi] = clut
            taken.add(clut)
    free = []
    for y in range(h - 1, -1, -1):
        for xs in range(iw // 16 - 1, -1, -1):
            c = (y << 6) | xs
            if c in taken:
                continue
            if any((x, y) in cover for x in range(xs * 64, xs * 64 + 64)):
                continue
            free.append(c)
    for gi in range(len(groups)):
        if gi not in cluts:
            if not free:
                raise ValueError("no free texture row left for a palette (too many materials)")
            cluts[gi] = free.pop(0)
            taken.add(cluts[gi])
    # texels just outside the faces: the PS1 samples a face's edge texels too, so they get the
    # palette of the nearest face's material (two rounds of growing the covered area), else they
    # would be read through another palette and show as specks along the edges
    slots = set()
    for c in cluts.values():
        y, xs = c >> 6, (c & 0x3F) * 64
        slots.update((x, y) for x in range(xs, xs + 64))
    for _ in range(2):
        grow = {}
        for (x, y), o in cover.items():
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (x + dx, y + dy)
                if 0 <= q[0] < w and 0 <= q[1] < h and q not in cover and q not in slots:
                    grow.setdefault(q, o)
        cover.update(grow)
    # colours per group
    def px(x, y):
        o = (y * w + x) * 4
        return rgba[o], rgba[o + 1], rgba[o + 2], rgba[o + 3]
    # materials whose texels are all as imported keep their palette and indices exactly
    untouched = set()
    if keep_palette_slots and orig_rgba is not None and len(orig_rgba) == len(rgba):
        for gi, (clut, _) in enumerate(groups):
            if clut is None:
                continue
            same = True
            for (x, y), o in cover.items():
                if o == gi:
                    k = (y * w + x) * 4
                    if rgba[k:k + 4] != orig_rgba[k:k + 4]:
                        same = False
                        break
            if same:
                untouched.add(gi)
    palettes = {}
    clear = {}
    for gi in range(len(groups)):
        if gi in untouched:
            continue
        cols = []
        clear[gi] = False
        for (x, y), o in cover.items():
            if o == gi:
                r, g, b, a = px(x, y)
                if a >= 128:
                    cols.append((r & 0xF8, g & 0xF8, b & 0xF8))
                else:
                    clear[gi] = True
        room = 15 if clear[gi] else 16
        uniq = sorted(set(cols))
        if len(uniq) <= room:
            pal = uniq
        else:
            pal = median_cut(cols, room)
            report.append("material %d: %d colours reduced to %d" % (gi, len(uniq), room))
        # with see-through texels, entry 0 is the transparent colour
        palettes[gi] = ([None] if clear[gi] else []) + pal
    # indices (on top of the original pixels when there are untouched materials)
    tim_len = iw * 2 * h
    pix = bytearray(tim_template[len(tim_template) - tim_len:]) if untouched else bytearray(tim_len)
    for y in range(h):
        for x in range(w):
            gi = cover.get((x, y))
            if gi is None or gi in untouched:
                continue
            r, g, b, a = px(x, y)
            pal = palettes[gi]
            if a < 128:
                k = 0
            else:
                k = min((i for i in range(len(pal)) if pal[i] is not None),
                        key=lambda i: (pal[i][0] - r) ** 2 + (pal[i][1] - g) ** 2 + (pal[i][2] - b) ** 2,
                        default=0)
            o = y * iw * 2 + (x >> 1)
            pix[o] = (pix[o] & 0x0F) | (k << 4) if x & 1 else (pix[o] & 0xF0) | k
    # the palettes go into the image rows they name
    for gi, pal in palettes.items():
        c = cluts[gi]
        y, xs = c >> 6, (c & 0x3F) * 16
        for i in range(16):
            v = 0 if i >= len(pal) or pal[i] is None else rgb15(*pal[i])
            o = (y * iw + xs + i) * 2
            pix[o] = v & 255
            pix[o + 1] = v >> 8
    # the TIM: keep the template's header and (unused by the game) CLUT block
    t = tim_template
    raw = bytearray(t)
    blen, ix, iy, iw0, ih0 = struct.unpack_from("<IHHHH", raw, len(raw) - 12 - iw * 2 * h)
    raw[len(raw) - iw * 2 * h:] = pix
    return bytes(raw), cluts, report


# ---------------------------------------------------------------- import

def _norm(v):
    s = math.sqrt(sum(x * x for x in v))
    return [x / s for x in v] if s > 1e-12 else [0.0, 0.0, 1.0]


def load_digimon(folder, entry, mods=None):
    import os

    def rd(fid):
        try:
            from . import dw2modfiles
        except ImportError:
            import dw2modfiles
        for f in (mods, folder):
            p = dw2modfiles.find(f, fid) if fid > 0 else None
            if p:
                return open(p, "rb").read()
        return None

    model = dw2model.Model.parse(rd(entry["model"]))
    anims = []
    for slot, fid in enumerate(entry["anims"]):
        d = rd(fid)
        anims.append((fid, dw2model.AnimFile.parse(d, len(model.bones)) if d else None))
    return model, anims


def _min_scale(R):
    return min(math.sqrt(sum(R[r][c] ** 2 for r in range(3))) for c in range(3))


def rest_worlds(model, anims, rest_frame):
    """Bone frames for the rest pose. Some animations shrink a part to nothing to hide it
    (a second face, a held item): such a bone takes a full-size pose of its own instead, so its
    part keeps its shape in Blender."""
    locs = []
    for i in range(len(model.bones)):
        if rest_frame:
            af, fr = rest_frame
            loc = game_local(af.pose_matrix(i, fr[i]))
        else:
            loc = ([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]], [0.0, 0.0, 0.0])
        if _min_scale(loc[0]) < 0.5:
            best = None
            for fid, af2 in anims:
                if not af2:
                    continue
                for an in af2.anims:
                    if not an:
                        continue
                    for fr2 in an.frames:
                        cand = game_local(af2.pose_matrix(i, fr2[i]))
                        sc = _min_scale(cand[0])
                        if best is None or sc > best[0] + 1e-9:
                            best = (sc, cand)
                        if sc > 0.95:
                            break
                    if best and best[0] > 0.95:
                        break
                if best and best[0] > 0.95:
                    break
            if best and best[0] >= 0.5:
                loc = best[1]
            else:
                loc = ([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]], loc[1])
        # rest frames are pure rotations (Blender bones carry no scale at rest)
        locs.append((polar(loc[0]), loc[1]))
    out = []
    for i, b in enumerate(model.bones):
        out.append(compose(out[b.parent], locs[i]) if b.parent >= 0 else locs[i])
    return out


def import_digimon(model, anims, name="Digimon", rest=None):
    """-> scene dict (Blender coordinates) for the add-on to build.
    rest: (slot, anim, frame) used as the rest pose (default: the first frame of the first
    animation in slot 0)."""
    nb = len(model.bones)
    rest_frame = None
    if rest is None:
        for fid, af in anims:
            if af:
                an = next((a for a in af.anims if a), None)
                if an:
                    rest_frame = (af, an.frames[0])
                    break
    else:
        af = anims[rest[0]][1]
        rest_frame = (af, af.anims[rest[1]].frames[rest[2]])
    W = rest_worlds(model, anims, rest_frame)
    base = [g2b_mat(R, t) for R, t in W]
    heads = [[m[0][3], m[1][3], m[2][3]] for m in base]
    children = [[] for _ in range(nb)]
    for i, b in enumerate(model.bones):
        if b.parent >= 0:
            children[b.parent].append(i)
    # bone directions (display only): towards the children, else on from the parent
    dirs = [None] * nb
    lengths = [0.05] * nb
    for i in range(nb):
        if children[i]:
            avg = [sum(heads[c][k] for c in children[i]) / len(children[i]) for k in range(3)]
            d = [avg[k] - heads[i][k] for k in range(3)]
            ln = math.sqrt(sum(x * x for x in d))
            if ln > 1e-4:
                dirs[i] = [x / ln for x in d]
                lengths[i] = max(ln, 0.02)
    for i in range(nb):
        if dirs[i] is None:
            p = model.bones[i].parent
            dirs[i] = dirs[p] if p >= 0 and dirs[p] is not None else [0.0, 0.0, 1.0]
            # length: the size of the part's own geometry
            vs = model.bones[i].verts
            if vs:
                ext = max(max(abs(c) for c in v) for v in vs) / SCALE
                lengths[i] = max(0.02, min(ext, 0.5))
    rest_m = []
    turns = []
    for i in range(nb):
        R3 = [row[:3] for row in base[i][:3]]
        # local direction = R^-1 dir (R is a rotation: transpose)
        dl = _norm([sum(R3[k][j] * dirs[i][k] for k in range(3)) for j in range(3)])
        X = axis_turn(dl)
        turns.append(X)
        rest_m.append(mul(base[i], as4(X)))
    bones = [{"name": "%s_%02d" % ("bone", i), "parent": model.bones[i].parent, "rest": rest_m[i],
              "length": lengths[i]} for i in range(nb)]
    # mesh
    verts, vbone, polys = [], [], []
    clut_list = []
    tim = model.tim
    W_, H_ = tim.width, tim.height
    for i, b in enumerate(model.bones):
        R, t = W[i]
        first = len(verts)
        for v in b.verts:
            gp = [sum(R[r][k] * v[k] for k in range(3)) + t[r] for r in range(3)]
            verts.append(g2b_point(gp))
            vbone.append(i)
        nrm = [_norm(g2b_dir([sum(R[r][k] * n[k] for k in range(3)) for r in range(3)]))
               for n in b.normals]
        for f in b.faces:
            order = [0, 2, 1] if len(f.verts) == 3 else [0, 2, 3, 1]
            if f.clut not in clut_list:
                clut_list.append(f.clut)
            polys.append({
                "verts": [first + f.verts[k] for k in order],
                "uvs": [(f.uvs[k][0] / W_, 1.0 - f.uvs[k][1] / H_) for k in order],
                "normals": [nrm[f.norms[k]] if f.norms[k] < len(nrm) else [0, 0, 1] for k in order],
                "material": clut_list.index(f.clut),
                "semi": 1 if f.semi else 0,
                "tpage": f.tpage,
            })
    w, h, rgba, _ = decode_texture(model)
    # actions
    actions = []
    for slot, (fid, af) in enumerate(anims):
        if not af:
            continue
        for k, an in enumerate(af.anims):
            if not an:
                continue
            frames = []
            for fr in an.frames:
                Wf = worlds(model, af, fr)
                pose = [mul(g2b_mat(R, t), as4(turns[i])) for i, (R, t) in enumerate(Wf)]
                basis = []
                for i in range(nb):
                    p = model.bones[i].parent
                    rest_rel = mul(inv(rest_m[p]), rest_m[i]) if p >= 0 else rest_m[i]
                    pose_rel = mul(inv(pose[p]), pose[i]) if p >= 0 else pose[i]
                    basis.append(mul(inv(rest_rel), pose_rel))
                frames.append(basis)
            actions.append({"name": "%s_anim%03d" % (name, slot * 10 + k), "slot": slot, "index": k,
                            "loop_to": an.loop_to if an.loop_to is not None else -1,
                            "frames": frames})
    meta = {
        "slots": [{"file": fid, "count": (af.table_len if af else 0),
                   "present": [k for k, a in enumerate(af.anims) if a] if af else []}
                  for fid, af in anims],
        "tim": model.tim_bytes.hex(),
        "texanim": model.texanim.hex(),
        "rgba_hash": _hash(rgba),
        "rgba_z": pack_rgba(rgba),
        "bone_count": nb,
    }
    return {"bones": bones, "verts": verts, "vbone": vbone, "polys": polys,
            "materials": clut_list, "image": (w, h, rgba), "actions": actions, "meta": meta}


def pack_rgba(rgba):
    import base64
    import zlib
    return base64.b64encode(zlib.compress(bytes(rgba), 9)).decode("ascii")


def unpack_rgba(text):
    import base64
    import zlib
    return zlib.decompress(base64.b64decode(text))


def blink_intact(meta, rgba, w, h, texanim):
    """The eye blink copies fixed patches of the texture: it can stay when every texel it
    reads or writes is as imported (new parts were put elsewhere)."""
    if not meta.get("rgba_z"):
        return False
    try:
        orig = unpack_rgba(meta["rgba_z"])
    except Exception:
        return False
    if len(orig) != len(rgba):
        return False
    for (sx, sy, rw, rh), (dx, dy) in texanim_rects(texanim):
        for x0, y0 in ((sx, sy), (dx, dy)):
            for y in range(y0, min(h, y0 + rh)):
                a = (y * w + x0) * 4
                b = (y * w + min(w, x0 + rw)) * 4
                if orig[a:b] != rgba[a:b]:
                    return False
    return True


def _hash(b):
    import hashlib
    return hashlib.sha1(bytes(b)).hexdigest()


# ---------------------------------------------------------------- export

class ExportError(Exception):
    pass


def _q(x, lo=-32768, hi=32767):
    v = int(round(x))
    return max(lo, min(hi, v)), (v < lo or v > hi)


def export_digimon(sc, model_id, digimon_name="Digimon"):
    """sc: what the add-on reads from Blender (same keys as import_digimon gives, the actions
    as armature-space pose matrices: action["pose"] = [[4x4 per bone] per frame]).
    -> ({file id: bytes}, [report lines])"""
    report = []
    meta = sc["meta"]
    bones = sc["bones"]
    nb = len(bones)
    # depth-first order (the game stores the tree as depths in walk order)
    kids = {i: [] for i in range(nb)}
    roots = []
    for i, b in enumerate(bones):
        (kids[b["parent"]] if b["parent"] >= 0 else roots).append(i)
    order = []
    depth = {}

    def walk(i, d):
        order.append(i)
        depth[i] = d
        for c in kids[i]:
            walk(c, d + 1)
    for r in roots:
        walk(r, 0)
    if max(depth.values()) > 7:
        raise ExportError("the bone tree is %d deep; the game allows 8 levels" % (max(depth.values()) + 1))
    if nb > 64:
        raise ExportError("%d bones; keep it to 64 or fewer" % nb)
    new_index = {old: k for k, old in enumerate(order)}
    G = [b2g_mat(b["rest"]) for b in bones]      # game frames at rest
    Ginv = [inv(g2b_like(R, t)) for R, t in G]
    model = dw2model.Model()
    for old in order:
        b = dw2model.Bone()
        b.depth = depth[old]
        p = bones[old]["parent"]
        b.parent = new_index[p] if p >= 0 else -1
        model.bones.append(b)
    # vertices of each bone
    vmap = {}           # (bone, blender vertex) -> index in that bone

    def vert_in(bone_old, vi):
        key = (bone_old, vi)
        if key in vmap:
            return vmap[key]
        gp = b2g_point(sc["verts"][vi])
        lp = mulv(Ginv[bone_old], gp)
        q = []
        clip = False
        for c in lp:
            v, o = _q(c)
            q.append(v)
            clip |= o
        if clip:
            report.append("a vertex of %s is too far from its bone and was clamped" % bones[bone_old]["name"])
        b = model.bones[new_index[bone_old]]
        b.verts.append(tuple(q))
        vmap[key] = len(b.verts) - 1
        return vmap[key]

    nmap = {}

    def normal_in(bone_old, n):
        R, _ = G[bone_old]
        gn = b2g_dir(n)
        # into the bone frame: R^-1 (rotation: transpose; normalise against any scale)
        ln = [sum(R[k][j] * gn[k] for k in range(3)) for j in range(3)]
        ln = _norm(ln)
        q = tuple(int(round(c * 4096)) for c in ln)
        key = (bone_old, q)
        if key in nmap:
            return nmap[key]
        b = model.bones[new_index[bone_old]]
        b.normals.append(q)
        nmap[key] = len(b.normals) - 1
        return nmap[key]

    # texture groups first (face clut comes from them)
    w, h, rgba = sc["image"]
    tim0 = bytes.fromhex(meta["tim"]) if meta.get("tim") else None
    texanim = bytes.fromhex(meta["texanim"]) if meta.get("texanim") else b"\xff" * 30
    if tim0 is None:
        raise ExportError("no texture template (import a Digimon first, then change it)")
    tmpl = dw2model.Tim(tim0)
    if (w, h) != (tmpl.width, tmpl.height):
        raise ExportError("the texture must be %d x %d (it is %d x %d)" % (tmpl.width, tmpl.height, w, h))
    mats = sc["materials"]          # per material: original clut or None
    groups = [(mats[m], []) for m in range(len(mats))]
    split = 0
    faces_out = []
    for poly in sc["polys"]:
        vs = poly["verts"]
        owners = [sc["vbone"][v] for v in vs]
        bone_old = max(set(owners), key=owners.count)
        if len(set(owners)) > 1:
            split += 1
        loops = list(range(len(vs)))
        if len(vs) > 4:
            tris = [[0, k, k + 1] for k in range(1, len(vs) - 1)]
            report.append("a %d-sided face was split into triangles" % len(vs))
        else:
            tris = [loops]
        for lp in tris:
            faces_out.append((bone_old, poly, lp))
            # in the game's strip order (0 1 / 3 2 of the loop) for the texel coverage
            strip = [lp[0], lp[1], lp[3], lp[2]] if len(lp) == 4 else lp
            groups[poly["material"]][1].append([(poly["uvs"][k][0] * w, (1.0 - poly["uvs"][k][1]) * h)
                                                for k in strip])
    if split:
        report.append("%d faces span two bones; each moves with the bone most of its corners are on"
                      % split)
    # texture: unchanged image -> the original TIM bytes and cluts
    vscale = 1.0
    unchanged = meta.get("rgba_hash") == _hash(rgba) and all(m is not None for m in mats)
    if unchanged:
        tim_bytes = tim0
        cluts = {gi: mats[gi] for gi in range(len(mats))}
    else:
        if any(m is None for m in mats) and not blink_intact(meta, rgba, w, h, texanim):
            # a new texture layout: the eye blink would copy parts of the old one
            if texanim[:1] != b"\xff" or len(texanim) < 30:
                report.append("eye blink / texture animation turned off (new texture layout)")
            texanim = b"\xff" * 30
        orig = None
        if meta.get("rgba_z"):
            try:
                orig = unpack_rgba(meta["rgba_z"])
            except Exception:
                orig = None
        try:
            tim_bytes, cluts, rep = encode_texture(w, h, rgba, groups, tim0, True, texanim, orig)
        except ValueError:
            # no free rows for the palettes: squeeze the picture up to make room at the bottom
            need = (len(groups) + (w // 64) - 1) // (w // 64) + 1     # + a row of margin
            vscale = (h - need) / float(h)
            sq = bytearray(w * h * 4)
            for y in range(h - need):
                sy = min(h - 1, int(y / vscale))
                sq[y * w * 4:(y + 1) * w * 4] = rgba[sy * w * 4:(sy + 1) * w * 4]
            rgba = bytes(sq)
            groups = [(None, [[(u, v * vscale) for u, v in f] for f in fl]) for _, fl in groups]
            texanim = b"\xff" * 30
            tim_bytes, cluts, rep = encode_texture(w, h, rgba, groups, tim0, False, texanim)
            report.append("texture squeezed into the top %d rows to make room for %d palettes"
                          % (h - need, len(groups)))
        report += rep
        report.append("texture re-encoded (%d palettes)" % len(cluts))
    for bone_old, poly, lp in faces_out:
        vi = [vert_in(bone_old, poly["verts"][k]) for k in lp]
        ni = [normal_in(bone_old, poly["normals"][k]) for k in lp]
        uv = []
        for k in lp:
            u = int(round(poly["uvs"][k][0] * w))
            v = int(round((1.0 - poly["uvs"][k][1]) * h * vscale))
            uv.append((max(0, min(w - 1, u)), max(0, min(h - 1, v))))
        if len(lp) == 3:
            gv = [vi[0], vi[2], vi[1]]
            gn = [ni[0], ni[2], ni[1]]
            gu = [uv[0], uv[2], uv[1]]
        else:
            gv = [vi[0], vi[3], vi[1], vi[2]]
            gn = [ni[0], ni[3], ni[1], ni[2]]
            gu = [uv[0], uv[3], uv[1], uv[2]]
        model.bones[new_index[bone_old]].faces.append(
            dw2model.Face(gv, gn, gu, cluts[poly["material"]], poly.get("tpage", 0), bool(poly.get("semi", 0))))
    for b, old in zip(model.bones, order):
        if len(b.verts) > 256 or len(b.normals) > 256:
            raise ExportError("bone %s has %d corners / %d normals; the game allows 256 each per bone"
                              % (bones[old]["name"], len(b.verts), len(b.normals)))
        if not b.verts:
            b.verts = [(0, 0, 0)]
        if not b.normals:
            b.normals = [(0, -4096, 0)]
    model.texanim = texanim
    model.tim_bytes = tim_bytes
    model.tim = dw2model.Tim(tim_bytes)
    files = {model_id: model.build(keep_layout=False)}
    # animations, slot by slot
    by_slot = {}
    for a in sc["actions"]:
        by_slot.setdefault(a["slot"], []).append(a)
    for slot, info in enumerate(meta["slots"]):
        fid = info["file"]
        if fid <= 0:
            continue
        acts = by_slot.get(slot, [])
        af = dw2model.AnimFile()
        af.nbones = nb
        af.poses = [[] for _ in range(nb)]
        count = max([info.get("count", 0)] + [a["index"] + 1 for a in acts])
        af.anims = [None] * count
        libs = [dict() for _ in range(nb)]
        have = {a["index"]: a for a in acts}
        for k in range(count):
            a = have.get(k)
            if a is None:
                if k in info.get("present", []):
                    # keep the game's animation id valid: hold the rest pose
                    a = {"pose": [[b["rest"] for b in bones]], "loop_to": -1}
                    report.append("slot %d animation %d: not in Blender, written as the rest pose"
                                  % (slot, k))
                else:
                    continue
            an = dw2model.Anim()
            for pose in a["pose"]:
                Gf = [b2g_mat(m) for m in pose]
                fr = []
                for newi, old in enumerate(order):
                    p = bones[old]["parent"]
                    if p >= 0 and _min_scale(Gf[p][0]) < 0.02:
                        # the parent is shrunk to nothing: the child is hidden with it whatever its
                        # own pose; use its rest pose (keeps the pose library small)
                        loc = mul(inv(g2b_like(*G[p])), g2b_like(*G[old]))
                    elif p >= 0:
                        loc = mul(inv(g2b_like(*Gf[p])), g2b_like(*Gf[old]))
                    else:
                        loc = g2b_like(*Gf[old])
                    mq = tuple(_q(loc[r][c] * 4096)[0] for r in range(3) for c in range(3))
                    tq = tuple(_q(loc[r][3])[0] for r in range(3))
                    key = mq + tq
                    lib = libs[newi]
                    if key not in lib:
                        lib[key] = len(lib)
                    fr.append(lib[key])
                an.frames.append(fr)
            an.loop_to = a["loop_to"] if a.get("loop_to", -1) >= 0 else None
            if an.loop_to is not None and an.loop_to >= len(an.frames):
                an.loop_to = 0
            af.anims[k] = an
        for newi in range(nb):
            limit = 128 if newi == 0 else 256
            lib = libs[newi]
            if len(lib) > limit:
                remap = _reduce(lib, limit)
                for an in af.anims:
                    if an:
                        for fr in an.frames:
                            fr[newi] = remap[fr[newi]]
                report.append("slot %d: bone %s has %d different poses, merged to %d"
                              % (slot, bones[order[newi]]["name"], len(lib), limit))
                keys = sorted(set(remap.values()))
                inv_lib = {i: k for k, i in lib.items()}
                af.poses[newi] = [_pose(inv_lib[i]) for i in keys]
                pos = {i: n for n, i in enumerate(keys)}
                for an in af.anims:
                    if an:
                        for fr in an.frames:
                            fr[newi] = pos[fr[newi]]
            else:
                af.poses[newi] = [_pose(k) for k, i in sorted(lib.items(), key=lambda kv: kv[1])]
        files[fid] = af.build(keep_layout=False)
    return files, report


def g2b_like(R, t):
    """(3x3, t) game frame -> 4x4 in game units (no axis change)."""
    return [R[0] + [t[0]], R[1] + [t[1]], R[2] + [t[2]], [0.0, 0.0, 0.0, 1.0]]


def _pose(key):
    m = list(key[:9])
    return dw2model.Pose([m[0:3], m[3:6], m[6:9]], list(key[9:12]))


def _reduce(lib, limit):
    """Merge poses until at most limit remain: each dropped pose maps to its nearest kept one."""
    keys = sorted(lib, key=lambda k: lib[k])
    keep = keys[:]

    def dist(a, b):
        return sum(abs(a[i] - b[i]) for i in range(9)) / 4096.0 + sum(abs(a[i] - b[i]) for i in range(9, 12)) / 64.0
    remap = {lib[k]: lib[k] for k in keys}
    while len(keep) > limit:
        best = None
        for i in range(len(keep)):
            for j in range(i + 1, min(len(keep), i + 24)):
                d = dist(keep[i], keep[j])
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        gone = keep.pop(j)
        for k, v in remap.items():
            if v == lib[gone]:
                remap[k] = lib[keep[i]]
    return remap
