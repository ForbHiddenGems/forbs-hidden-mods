"""Best-guess names for a Digimon's bones from the shape of its parts (the game's files have
none). Every name keeps the game's bone number (wing_L_12); a part it cannot place is part_N.

How it reads a Digimon (Blender coordinates: z up, facing -y, its left on +x):
  trunk   the root bones (most Digimon have two: an upper body and the hips)
  limbs   everything hanging off the trunk:
            flat sheet, high up, not touching the ground  -> wing
            off to one side, reaching the ground          -> leg  (thigh, shin, foot, toe)
            off to one side, not reaching the ground      -> arm  (upperarm, forearm, hand, finger)
            in the middle, above the trunk                -> neck ... head, then jaw / horn on it
            in the middle, behind                         -> tail1, tail2 ...
"""
import math

try:
    import numpy as _np
except ImportError:          # Blender always has numpy; plain Python may not
    _np = None


def guess(scene):
    bones = scene["bones"]
    n = len(bones)
    verts = scene["verts"]
    vb = scene["vbone"]
    parent = [b["parent"] for b in bones]
    kids = [[] for _ in range(n)]
    for i, p in enumerate(parent):
        if p >= 0:
            kids[p].append(i)
    pts = [[] for _ in range(n)]
    for v, b in zip(verts, vb):
        pts[b].append(v)
    if not verts:
        return ["part_%02d" % i for i in range(n)]
    lo = [min(v[k] for v in verts) for k in range(3)]
    hi = [max(v[k] for v in verts) for k in range(3)]
    H = max(hi[2] - lo[2], 1e-6)
    W = max(hi[0] - lo[0], 1e-6)
    ground = lo[2]
    heads = [[b["rest"][0][3], b["rest"][1][3], b["rest"][2][3]] for b in bones]

    def subtree(i):
        out = [i]
        for c in kids[i]:
            out += subtree(c)
        return out

    def mean(ps, fallback):
        return [sum(v[k] for v in ps) / len(ps) for k in range(3)] if ps else fallback

    cen = [mean(pts[i], heads[i]) for i in range(n)]
    size = [len(pts[i]) for i in range(n)]

    def tree_pts(i):
        return [v for b in subtree(i) for v in pts[b]]

    def flat(i):
        """A sheet (a wing panel, a fin): thin one way, wide the other two (principal axes);
        a spike or claw is thin two ways and does not count."""
        p = pts[i]
        if len(p) < 4:
            return False
        if _np is not None:
            a = _np.array(p)
            a = a - a.mean(0)
            ev = sorted(_np.linalg.eigvalsh(a.T @ a / len(a)))
            ext = [math.sqrt(max(e, 0.0)) for e in ev]
        else:
            ext = sorted(max(v[k] for v in p) - min(v[k] for v in p) for k in range(3))
        return ext[2] > 0.03 * H and ext[0] < 0.35 * ext[2] and ext[1] > 0.3 * ext[2]

    def side_of(c):
        return ("L" if c[0] > 0 else "R") if abs(c[0]) > 0.07 * W else ""

    def sfx(c):
        s = side_of(c)
        return "_" + s if s else ""

    names = [None] * n
    # ---- trunk: central roots (most Digimon have two: an upper body and the hips)
    roots = [i for i in range(n) if parent[i] < 0]
    central_roots = [r for r in roots if not side_of(mean(tree_pts(r), cen[r]))] or roots[:1]
    trunk = sorted(central_roots, key=lambda r: -size[r])[:2]
    if len(trunk) == 1:
        names[trunk[0]] = "body"
        hips = chest = trunk[0]
    else:
        low = lambda r: mean(pts[r], cen[r])[2]
        hips, chest = sorted(trunk, key=low)
        names[hips], names[chest] = "hips", "chest"
    trunk_c = mean([v for r in trunk for v in pts[r]], [0.0, 0.0, 0.0])
    chest_c = mean(pts[chest], cen[chest])

    def tree_shape(r):
        """(thinnest, middle) spread of a whole limb next to its widest: a flat sheet is about
        (0, >0.3); a stick (an arm, a staff) has a small middle spread too."""
        p = tree_pts(r)
        if len(p) < 4:
            return 1.0, 1.0
        if _np is not None:
            a = _np.array(p)
            a = a - a.mean(0)
            ev = [math.sqrt(max(e, 0.0)) for e in sorted(_np.linalg.eigvalsh(a.T @ a / len(a)))]
        else:
            ev = sorted(max(v[k] for v in p) - min(v[k] for v in p) for k in range(3))
        top = max(ev[2], 1e-9)
        return ev[0] / top, ev[1] / top

    def chain_of(r):
        """Main chain from r: always into the child whose tree is biggest."""
        out = [r]
        while kids[out[-1]]:
            out.append(max(kids[out[-1]], key=lambda c: len(tree_pts(c))))
        return out

    seqs = {"leg": ["thigh", "shin", "foot", "toe"], "arm": ["upperarm", "forearm", "hand", "finger"],
            "frontleg": ["frontthigh", "frontshin", "frontfoot", "fronttoe"]}

    def label_chain(chain, kind, c):
        for k, b in enumerate(chain):
            if names[b]:
                continue
            if kind in seqs:
                seq = seqs[kind]
                base = seq[min(k, len(seq) - 1)] if len(chain) > 1 else kind
            else:
                base = kind + ("" if len(chain) == 1 else str(k + 1))
            names[b] = base + sfx(c)

    def head_tree(r):
        tree = subtree(r)
        head = max(tree, key=lambda b: size[b])
        path = [head]
        while path[-1] != r and parent[path[-1]] >= 0:
            path.append(parent[path[-1]])
        for b in path[1:]:
            names[b] = names[b] or "neck"
        names[head] = names[head] or "head"
        hc = cen[head]
        for b in tree:
            if names[b]:
                continue
            c = mean(tree_pts(b), cen[b])
            if flat(b) and side_of(c):
                names[b] = "ear" + sfx(c)
            elif c[2] < hc[2] and c[1] < hc[1] and not side_of(c):
                names[b] = "jaw"
            elif c[2] > hc[2] + 0.02 * H:
                names[b] = ("horn" if size[b] < 0.6 * max(1, size[head]) else "head") + sfx(c)
            elif side_of(c):
                names[b] = "ear" + sfx(c)
            else:
                names[b] = "headpart"

    def attached_to(r):
        """The trunk bone a limb hangs from."""
        p = r
        while p >= 0 and p not in trunk:
            p = parent[p]
        return p

    # four-legged: every limb on the sides of the chest (that is not a wing) reaches the ground
    def _reach(r):
        tp = tree_pts(r)
        return bool(tp) and min(v[2] for v in tp) < ground + 0.1 * H
    chest_limbs = [c for c in kids[chest] if c not in trunk and side_of(mean(tree_pts(c), cen[c]))
                   and not all(flat(b) for b in subtree(c) if pts[b])]
    # a horizontal body: chest and hips about level, the chest well in front
    _cc, _hc = mean(pts[chest], cen[chest]), mean(pts[hips], cen[hips])
    level = hips != chest and abs(_cc[2] - _hc[2]) < 0.2 * H and _hc[1] - _cc[1] > 0.12 * H
    four_legged = level and len(chest_limbs) >= 2 and all(_reach(c) for c in chest_limbs)
    work = [c for t in trunk for c in kids[t] if c not in trunk]
    work += [r for r in roots if r not in trunk]
    kinds = {}                # limb root -> (kind, centroid)
    while work:
        r = work.pop(0)
        if names[r]:
            continue
        tp = tree_pts(r)
        c = mean(tp, cen[r])
        reaches_ground = bool(tp) and min(v[2] for v in tp) < ground + 0.1 * H
        high = c[2] > ground + 0.4 * H
        side = side_of(c)
        behind = c[1] > trunk_c[1] + 0.05 * H
        front = c[1] < trunk_c[1] - 0.12 * H
        above = c[2] > trunk_c[2] + 0.08 * H
        on_hips = attached_to(r) == hips and hips != chest
        kid_sides = set(side_of(mean(tree_pts(k), cen[k])) for k in kids[r]) - {""}
        if not side and len(kid_sides) == 2 and not above:
            # a central piece carrying both a left and a right part (a collar, a shoulder bar)
            names[r] = "part"
            work = kids[r] + work
            continue
        attach_back = (heads[r][1] - chest_c[1]) / H
        thin, mid = tree_shape(r)
        tv = [b for b in subtree(r) if pts[b]]
        flat_frac = sum(size[b] for b in tv if flat(b)) / float(max(1, sum(size[b] for b in tv)))
        wingish = high and mid > 0.33 and (
            (flat_frac >= 0.5 and (thin < 0.12 or (attach_back > 0.04 and thin < 0.4)))
            or (attach_back > 0.1 and thin < 0.6 and flat_frac >= 0.25))
        if wingish and (side or behind) and not (on_hips and not side):
            kind = "wing"
        elif side:
            if on_hips or (reaches_ground and attached_to(r) < 0):
                kind = "leg"
            elif reaches_ground and c[2] < trunk_c[2] and (hips == chest or four_legged):
                kind = "frontleg" if hips != chest else "leg"
            else:
                kind = "arm"
        elif on_hips and behind and not reaches_ground:
            kind = "tail"
        elif above or (front and not reaches_ground):
            kind = "head"
        elif behind and not reaches_ground:
            kind = "tail"
        elif reaches_ground:
            kind = "leg"
        else:
            names[r] = "part"
            work = kids[r] + work
            continue
        kinds[r] = (kind, c)
    # left / right twins get the same kind (an arm holding a sword is still an arm)
    rank = {"arm": 0, "leg": 1, "frontleg": 1, "wing": 2}

    def mirror_gap(a, b):
        ha, hb = heads[a], heads[b]
        return abs(ha[0] + hb[0]) + abs(ha[1] - hb[1]) + abs(ha[2] - hb[2])

    def twin_of(a):
        ca = kinds[a][1]
        cands = [b for b in kinds if b != a and attached_to(b) == attached_to(a)
                 and side_of(kinds[b][1]) and side_of(ca) and side_of(kinds[b][1]) != side_of(ca)
                 and len(subtree(b)) == len(subtree(a))]
        if not cands:
            return None
        b = min(cands, key=lambda b: mirror_gap(a, b))
        return b if mirror_gap(a, b) < 0.3 * H else None
    for a in list(kinds):
        b = twin_of(a)
        if b is None or twin_of(b) != a or a > b:
            continue
        (ka, ca), (kb, cb) = kinds[a], kinds[b]
        if ka != kb and ka in rank and kb in rank:
            k = min(ka, kb, key=lambda x: rank[x])
            kinds[a], kinds[b] = (k, ca), (k, cb)
    for r, (kind, c) in kinds.items():
        if kind == "head":
            head_tree(r)
        else:
            label_chain(chain_of(r), kind, c)
    # side branches of a limb (fingers, spikes, a held weapon): after the limb they hang from
    for b in range(n):
        if names[b] is None:
            chain = []
            p = parent[b]
            while p >= 0 and names[p] is None:
                p = parent[p]
            kind = (names[p] if p >= 0 else "part").split("_")[0].rstrip("0123456789")
            while kind.endswith("part") and kind != "part":
                kind = kind[:-4]
            kind = {"thigh": "leg", "shin": "leg", "foot": "leg", "toe": "leg", "upperarm": "arm",
                    "forearm": "arm", "hand": "arm", "finger": "arm", "frontthigh": "frontleg",
                    "frontshin": "frontleg", "frontfoot": "frontleg", "fronttoe": "frontleg"}.get(kind, kind)
            names[b] = (kind + "part" if kind != "part" else "part") + sfx(mean(tree_pts(b), cen[b]))
    return ["%s_%02d" % (names[i] or "part", i) for i in range(n)]
