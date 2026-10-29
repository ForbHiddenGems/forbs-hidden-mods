"""Copying parts (bones with their mesh, texture and motion) from one Digimon onto another:
the Blender-free half. Texture work is in texel coordinates, y down from the top row.

  occupancy()      which texels of the target texture are taken (faces, eye blink, palettes)
  islands()        the donor texels the copied faces use, as rectangles
  pack()           a free spot in the target texture for each rectangle
  reserve_cells()  room for the new palettes (64 texels of one row each)
  resample()       donor motion fitted to a target animation's length
"""
try:
    from . import dw2core
except ImportError:
    import dw2core


class Occupancy:
    """One int per texture row, a bit per texel."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.rows = [0] * h

    def mark(self, x, y, w=1, h=1):
        x0, x1 = max(0, x), min(self.w, x + w)
        if x1 <= x0:
            return
        bits = ((1 << (x1 - x0)) - 1) << x0
        for yy in range(max(0, y), min(self.h, y + h)):
            self.rows[yy] |= bits

    def free(self, x, y, w, h):
        if x < 0 or y < 0 or x + w > self.w or y + h > self.h:
            return False
        bits = ((1 << w) - 1) << x
        return all(not (self.rows[yy] & bits) for yy in range(y, y + h))

    def count(self):
        return sum(bin(r).count("1") for r in self.rows)


def occupancy(w, h, face_uvs, cluts, texanim):
    """face_uvs: texel UV lists (strip order for quads) of every face already on the target;
    cluts: the palettes in use; texanim: the eye-blink records."""
    occ = Occupancy(w, h)
    for (x, y) in dw2core.uv_cover([(0, uvs) for uvs in face_uvs], w, h):
        occ.mark(x, y)
    for (sx, sy, rw, rh), (dx, dy) in dw2core.texanim_rects(texanim):
        occ.mark(sx, sy, rw, rh)
        occ.mark(dx, dy, rw, rh)
    for c in cluts:
        if c is not None:
            occ.mark((c & 0x3F) * 64, c >> 6, 64, 1)
    return occ


def islands(face_uvs, w, h, margin=1):
    """Rectangles (x, y, w, h) covering the texels of the given faces, merged where they
    touch or overlap (with a margin so bilinear-free PS1 sampling never reads a neighbour),
    and for each face the index of its rectangle."""
    rects = []
    owner = []
    for uvs in face_uvs:
        cov = dw2core.uv_cover([(0, uvs)], w, h)
        if cov:
            xs = [x for x, y in cov]
            ys = [y for x, y in cov]
            r = [min(xs), min(ys), max(xs) + 1, max(ys) + 1]
        else:
            u = [p[0] for p in uvs]
            v = [p[1] for p in uvs]
            r = [int(min(u)), int(min(v)), int(max(u)) + 1, int(max(v)) + 1]
        # the UV corners themselves (PS1 UVs point at texels on the edge)
        for p in uvs:
            r[0] = min(r[0], int(p[0]))
            r[1] = min(r[1], int(p[1]))
            r[2] = max(r[2], min(w, int(p[0]) + 1))
            r[3] = max(r[3], min(h, int(p[1]) + 1))
        rects.append(r)
        owner.append(len(rects) - 1)
    # merge overlapping / touching rectangles until none touch
    changed = True
    parent = list(range(len(rects)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    while changed:
        changed = False
        roots = sorted(set(find(i) for i in range(len(rects))))
        for a_i in range(len(roots)):
            for b_i in range(a_i + 1, len(roots)):
                a, b = find(roots[a_i]), find(roots[b_i])
                if a == b:
                    continue
                ra, rb = rects[a], rects[b]
                if (ra[0] - margin < rb[2] and rb[0] - margin < ra[2] and
                        ra[1] - margin < rb[3] and rb[1] - margin < ra[3]):
                    rects[a] = [min(ra[0], rb[0]), min(ra[1], rb[1]), max(ra[2], rb[2]), max(ra[3], rb[3])]
                    parent[b] = a
                    changed = True
    roots = sorted(set(find(i) for i in range(len(rects))))
    index = {r: k for k, r in enumerate(roots)}
    out = [(rects[r][0], rects[r][1], rects[r][2] - rects[r][0], rects[r][3] - rects[r][1]) for r in roots]
    return out, [index[find(o)] for o in owner]


def reserve_cells(occ, n):
    """n free palette cells (64 texels of one row), from the bottom up; marks them taken.
    -> [clut value] or None when there is no room."""
    out = []
    for y in range(occ.h - 1, -1, -1):
        for cx in range(occ.w // 64 - 1, -1, -1):
            if len(out) == n:
                return out
            if occ.free(cx * 64, y, 64, 1):
                occ.mark(cx * 64, y, 64, 1)
                out.append((y << 6) | cx)
    return out if len(out) == n else None


def pack(occ, rects, margin=1):
    """A free spot for each rectangle (largest first, scanning from the top left), marked taken
    with a margin. -> [(x, y)] in the rectangles' order, or None when they do not all fit."""
    order = sorted(range(len(rects)), key=lambda i: -(rects[i][2] * rects[i][3]))
    spots = [None] * len(rects)
    for i in order:
        _, _, rw, rh = rects[i]
        found = None
        for y in range(0, occ.h - rh + 1):
            for x in range(0, occ.w - rw + 1):
                # keep a free margin around it as well
                if occ.free(max(0, x - margin), max(0, y - margin),
                            min(occ.w, x + rw + margin) - max(0, x - margin),
                            min(occ.h, y + rh + margin) - max(0, y - margin)):
                    found = (x, y)
                    break
            if found:
                break
        if found is None:
            return None
        occ.mark(found[0], found[1], rw, rh)
        spots[i] = found
    return spots


def resample(donor_frames, target_frames):
    """Donor frame (float) to show at each target frame 0..target_frames-1: the donor's loop
    played a whole number of times across the target animation, so it joins up when the target
    loops."""
    n_d = max(1, donor_frames)
    if n_d == 1 or target_frames <= 1:
        return [0.0] * max(1, target_frames)
    cycles = max(1, int(round(target_frames / float(n_d))))
    span = float(n_d) * cycles
    return [((f * span / target_frames) % n_d) for f in range(target_frames)]
