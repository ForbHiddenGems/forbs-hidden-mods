"""Digimon World 2 model / animation / texture format (pure Python, no dependencies).

Worked out from the decomp (src/main/model.c Gfx_AttachModel / Gfx_DrawTexModel,
src/main/anim.c Anim_StepModelAnim, src/main/texslot.c, src/main/digidata.c).

Model file (all little endian, offsets from the start of the file):
    u32 timOffset          the texture (a PS1 TIM), Cd_GetFileEntry(id << 16) entry 0
    u32 relocated          0 on disc (the game sets 1 after fixing up the offsets)
    u32 boneCount
    u32 vertsOfs[boneCount]
    u32 normalsOfs[boneCount]
    u32 polysOfs[boneCount]
    s32 depth[boneCount]   hierarchy as depths in walk order: a bone's parent is the
                           last earlier bone one level up (depth 0 = child of the actor)
    texAnim                eye-blink and texture-animation records (kept as raw bytes)
  per bone, at its offsets:
    verts:   s16 n, s16, s16, then n x (s16 x, y, z)      local to the bone
    normals: s16 n, s16, s16, then n x (s16 x, y, z)      4096 = 1.0
    polys:   4 sections, each s32 n then n records:
               quads, semi-transparent (GT4, 20 bytes)
               quads, opaque           (GT4, 20 bytes)
               tris,  semi-transparent (GT3, 16 bytes)
               tris,  opaque           (GT3, 16 bytes)
    GT4: u8 v[4], u8 n[4] (normal index, gives the vertex colour), u8 uv[8],
         u16 clut (offset added to the slot's CLUT), u16 tpage (bits or'd into the slot's)
    GT3: u8 v[3], u8 n[3], u8 uv[6], u16 clut, u16 tpage
  The game draws the quads as 0, 1, 2, 3 = a PS1 GT4 (strip order: 0 1 / 2 3).

Animation file (Digi_GetAnimFile; one file holds up to 10 animations):
    s32 relocated
    s32 poseTableOfs[boneCount]   per bone: a library of 0x18-byte poses
                                  (s16 m[3][3], 4096 = 1.0; s16 t[3])
    s32 animOfs[...]              0 = no such animation, the list ends at a word of 1
  an animation: frames of boneCount u8 pose indices; after each frame a byte with the
  top bit set ends it: 0xFF stop (hold the last frame), 0xFE lo hi loop to byte offset
  (lo | hi << 8) inside the animation. Each frame shows for 1/30 s.

Texture: a TIM, 4 or 8 bit with a CLUT. Face UVs are in pixels of that image. In 4-bit
mode the face clut selects one 16-colour row of the CLUT (clut & 0x3F = x / 16,
clut >> 6 = row).
"""
import struct


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def s32(b, o):
    return struct.unpack_from("<i", b, o)[0]


# ---------------------------------------------------------------- TIM

class Tim:
    def __init__(self, data, ofs=0):
        self.ofs = ofs
        magic, flags = struct.unpack_from("<II", data, ofs)
        if magic != 0x10:
            raise ValueError("not a TIM at 0x%X" % ofs)
        self.flags = flags
        self.bpp_mode = flags & 7          # 0 = 4 bit, 1 = 8 bit, 2 = 16 bit
        p = ofs + 8
        self.clut = None
        self.clut_rect = None
        if flags & 8:
            blen, cx, cy, cw, ch = struct.unpack_from("<IHHHH", data, p)
            self.clut_rect = (cx, cy, cw, ch)
            self.clut = list(struct.unpack_from("<%dH" % (cw * ch), data, p + 12))
            p += blen
        blen, ix, iy, iw, ih = struct.unpack_from("<IHHHH", data, p)
        self.img_rect = (ix, iy, iw, ih)
        self.pix = data[p + 12:p + 12 + iw * ih * 2]
        self.size = p + blen - ofs
        mult = {0: 4, 1: 2, 2: 1}.get(self.bpp_mode, 1)
        self.width = iw * mult
        self.height = ih

    def index_at(self, x, y):
        row = y * self.img_rect[2] * 2
        if self.bpp_mode == 0:
            b = self.pix[row + (x >> 1)]
            return (b >> 4) if x & 1 else (b & 15)
        if self.bpp_mode == 1:
            return self.pix[row + x]
        return struct.unpack_from("<H", self.pix, row + x * 2)[0]

    def clut_row_count(self):
        if not self.clut:
            return 0
        return len(self.clut) // (16 if self.bpp_mode == 0 else 256)

    @staticmethod
    def color(c):
        """PS1 15-bit colour -> (r, g, b, a). 0x0000 is transparent."""
        r = (c & 31) << 3
        g = ((c >> 5) & 31) << 3
        b = ((c >> 10) & 31) << 3
        a = 0 if c == 0 else 255
        return (r | r >> 5, g | g >> 5, b | b >> 5, a)

    def rgba(self, clut_index=0):
        """The image as a flat RGBA byte string, coloured with one CLUT row
        (4 bit: row of 16; 8 bit: row of 256)."""
        out = bytearray(self.width * self.height * 4)
        n = 16 if self.bpp_mode == 0 else 256
        pal = None
        if self.clut:
            base = clut_index * n
            pal = [self.color(self.clut[base + i]) if base + i < len(self.clut) else (0, 0, 0, 0)
                   for i in range(n)]
        o = 0
        for y in range(self.height):
            for x in range(self.width):
                i = self.index_at(x, y)
                out[o:o + 4] = bytes(pal[i] if pal else self.color(i))
                o += 4
        return bytes(out)


# ---------------------------------------------------------------- model

class Face:
    __slots__ = ("verts", "norms", "uvs", "clut", "tpage", "semi")

    def __init__(self, verts, norms, uvs, clut, tpage, semi):
        self.verts = verts      # vertex indices into the bone's list (3 or 4)
        self.norms = norms      # normal indices (vertex colours from the lights)
        self.uvs = uvs          # [(u, v)] in texture pixels
        self.clut = clut
        self.tpage = tpage
        self.semi = semi        # semi-transparent section


class Bone:
    def __init__(self):
        self.depth = 0
        self.parent = -1
        self.verts = []         # [(x, y, z)]
        self.normals = []
        self.faces = []
        self.vhdr = (0, 0)      # the two s16 after the vertex count (kept)
        self.nhdr = (0, 0)


class Model:
    """A parsed model file. Model.parse(bytes) -> Model; model.build() -> bytes."""

    def __init__(self):
        self.bones = []
        self.texanim = b""
        self.tim = None
        self.tim_bytes = b""
        self.layout = None      # how the parts were laid out (for a faithful rebuild)
        self.tail = b""         # bytes after the TIM (sector padding)

    @classmethod
    def parse(cls, data):
        m = cls()
        tim_ofs, reloc, n = struct.unpack_from("<III", data, 0)
        if n == 0 or n > 64:
            raise ValueError("bad bone count %d" % n)
        tab = 12
        vo = struct.unpack_from("<%dI" % n, data, tab)
        no = struct.unpack_from("<%dI" % n, data, tab + 4 * n)
        po = struct.unpack_from("<%dI" % n, data, tab + 8 * n)
        dp = struct.unpack_from("<%di" % n, data, tab + 12 * n)
        hdr_end = tab + 16 * n
        first = min(min(vo), min(no), min(po), tim_ofs)
        m.texanim = bytes(data[hdr_end:first])
        stack = []
        ends = {}
        for i in range(n):
            b = Bone()
            b.depth = dp[i]
            del stack[b.depth:]
            b.parent = stack[-1] if stack else -1
            stack.append(i)
            # vertices
            cnt, h1, h2 = struct.unpack_from("<hhh", data, vo[i])
            b.vhdr = (h1, h2)
            b.verts = [struct.unpack_from("<hhh", data, vo[i] + 6 + 6 * k) for k in range(cnt)]
            ends[("v", i)] = (vo[i], vo[i] + 6 + 6 * cnt)
            cnt, h1, h2 = struct.unpack_from("<hhh", data, no[i])
            b.nhdr = (h1, h2)
            b.normals = [struct.unpack_from("<hhh", data, no[i] + 6 + 6 * k) for k in range(cnt)]
            ends[("n", i)] = (no[i], no[i] + 6 + 6 * cnt)
            p = po[i]
            for sec in range(4):
                cnt = s32(data, p)
                p += 4
                quad = sec < 2
                semi = sec in (0, 2)
                for k in range(cnt):
                    if quad:
                        r = struct.unpack_from("<4B4B8BHH", data, p)
                        b.faces.append(Face(list(r[0:4]), list(r[4:8]),
                                            [(r[8], r[9]), (r[10], r[11]), (r[12], r[13]), (r[14], r[15])],
                                            r[16], r[17], semi))
                        p += 20
                    else:
                        r = struct.unpack_from("<3B3B6BHH", data, p)
                        b.faces.append(Face(list(r[0:3]), list(r[3:6]),
                                            [(r[6], r[7]), (r[8], r[9]), (r[10], r[11])],
                                            r[12], r[13], semi))
                        p += 16
            ends[("p", i)] = (po[i], p)
            m.bones.append(b)
        m.tim = Tim(data, tim_ofs)
        m.tim_bytes = bytes(data[tim_ofs:tim_ofs + m.tim.size])
        ends[("t", 0)] = (tim_ofs, tim_ofs + m.tim.size)
        # the order the parts sit in, and any gaps (kept so a rebuild is byte-identical)
        order = sorted(ends.items(), key=lambda kv: kv[1][0])
        layout = []
        pos = first
        for key, (a, e) in order:
            layout.append((key, bytes(data[pos:a]) if a > pos else b""))
            pos = max(pos, e)
        m.layout = layout
        m.reloc = reloc
        m.tail = bytes(data[pos:])
        return m

    # ---- writing

    def _part(self, key):
        kind, i = key
        if kind == "t":
            return self.tim_bytes
        b = self.bones[i]
        if kind == "v":
            out = struct.pack("<hhh", len(b.verts), *b.vhdr)
            return out + b"".join(struct.pack("<hhh", *v) for v in b.verts)
        if kind == "n":
            out = struct.pack("<hhh", len(b.normals), *b.nhdr)
            return out + b"".join(struct.pack("<hhh", *v) for v in b.normals)
        secs = [[], [], [], []]
        for f in b.faces:
            quad = len(f.verts) == 4
            secs[(0 if quad else 2) + (0 if f.semi else 1)].append(f)
        out = bytearray()
        for sec in secs:
            out += struct.pack("<i", len(sec))
            for f in sec:
                uv = [c for p in f.uvs for c in p]
                if len(f.verts) == 4:
                    out += struct.pack("<4B4B8BHH", *f.verts, *f.norms, *uv, f.clut, f.tpage)
                else:
                    out += struct.pack("<3B3B6BHH", *f.verts, *f.norms, *uv, f.clut, f.tpage)
        return bytes(out)

    def default_layout(self):
        """Part order for a new model: per bone verts, normals, polys; then the TIM."""
        lay = []
        for i in range(len(self.bones)):
            lay += [(("v", i), b""), (("n", i), b""), (("p", i), b"")]
        lay.append((("t", 0), b""))
        return lay

    def build(self, keep_layout=True):
        n = len(self.bones)
        if not (keep_layout and self.layout and len(self.layout) == 3 * n + 1):
            layout = self.default_layout()
            keep_layout = False
        else:
            layout = self.layout
        hdr_len = 12 + 16 * n
        body = bytearray()
        ofs = {}
        base = hdr_len + len(self.texanim)
        for key, gap in layout:
            body += gap
            # every part starts on a word (the game reads the section counts as words)
            while (base + len(body)) & 3:
                body += b"\0"
            ofs[key] = base + len(body)
            body += self._part(key)
        out = bytearray(struct.pack("<III", ofs[("t", 0)], getattr(self, "reloc", 0), n))
        for kind in ("v", "n", "p"):
            out += struct.pack("<%dI" % n, *[ofs[(kind, i)] for i in range(n)])
        out += struct.pack("<%di" % n, *[b.depth for b in self.bones])
        out += self.texanim + body
        if keep_layout:
            out += self.tail
        return bytes(out)

    def stats(self):
        return {
            "bones": len(self.bones),
            "verts": sum(len(b.verts) for b in self.bones),
            "faces": sum(len(b.faces) for b in self.bones),
            "tex": "%dx%d %s" % (self.tim.width, self.tim.height,
                                 {0: "4-bit", 1: "8-bit"}.get(self.tim.bpp_mode, "16-bit")),
        }


# ---------------------------------------------------------------- animation

class Pose:
    __slots__ = ("m", "t")

    def __init__(self, m, t):
        self.m = m      # 3x3 rows, 4096 = 1.0
        self.t = t      # (x, y, z)


class Anim:
    def __init__(self):
        self.frames = []        # [ [pose index per bone] ]
        self.loop_to = None     # frame number the animation loops back to, None = stops
        self.raw = b""


class AnimFile:
    """Anim file: AnimFile.parse(bytes, boneCount); .build() -> bytes."""

    def __init__(self):
        self.poses = []         # per bone: [Pose]
        self.anims = []         # index -> Anim or None
        self.layout = None
        self.tail = b""

    @classmethod
    def parse(cls, data, nbones):
        a = cls()
        a.nbones = nbones
        a.reloc = s32(data, 0)
        pt = list(struct.unpack_from("<%di" % nbones, data, 4))
        p = 4 + 4 * nbones
        offs = []
        while True:
            v = s32(data, p)
            p += 4
            if v == 1:
                break
            offs.append(v)
            if len(offs) > 64:
                raise ValueError("anim table has no end")
        a.table_len = len(offs)
        for o in offs:
            if o == 0:
                a.anims.append(None)
                continue
            an = Anim()
            q = o
            while True:
                an.frames.append(list(data[q:q + nbones]))
                q += nbones
                c = data[q]
                if c & 0x80:
                    if c == 0xFE:
                        tgt = data[q + 1] | data[q + 2] << 8
                        if tgt % nbones:
                            raise ValueError("loop target inside a frame")
                        an.loop_to = tgt // nbones
                        q += 3
                    else:
                        an.end_byte = c
                        q += 1
                    break
            an.raw = bytes(data[o:q])
            a.anims.append(an)
        # each bone's pose library: as many poses as the animations use
        used = [0] * nbones
        for an in a.anims:
            if an:
                for fr in an.frames:
                    for b, i in enumerate(fr):
                        used[b] = max(used[b], i + 1)
        parts = {}
        for b in range(nbones):
            lib = []
            for k in range(used[b]):
                r = struct.unpack_from("<9h3h", data, pt[b] + 0x18 * k)
                lib.append(Pose([list(r[0:3]), list(r[3:6]), list(r[6:9])], list(r[9:12])))
            a.poses.append(lib)
            parts[("p", b)] = (pt[b], pt[b] + 0x18 * used[b])
        for k, o in enumerate(offs):
            if o:
                parts[("a", k)] = (o, o + len(a.anims[k].raw))
        order = sorted(parts.items(), key=lambda kv: (kv[1][0], kv[0]))
        pos = 4 + 4 * nbones + 4 * (len(offs) + 1)
        layout = []
        for key, (s_, e) in order:
            if s_ < pos:
                # shares bytes with the part before (e.g. two bones point at one library)
                layout.append((key, None, s_))
                continue
            layout.append((key, bytes(data[pos:s_]), None))
            pos = e
        a.layout = layout
        a.tail = bytes(data[pos:])
        return a

    # ---- writing

    def _anim_bytes(self, an):
        out = bytearray()
        for fr in an.frames:
            out += bytes(fr)
        if an.loop_to is not None:
            t = an.loop_to * self.nbones
            out += bytes((0xFE, t & 0xFF, t >> 8))
        else:
            out += bytes((getattr(an, "end_byte", 0xFF),))
        return bytes(out)

    def _pose_bytes(self, b):
        return b"".join(struct.pack("<9h3h", *p.m[0], *p.m[1], *p.m[2], *p.t) for p in self.poses[b])

    def default_layout(self):
        lay = [(("a", k), b"", None) for k, an in enumerate(self.anims) if an]
        lay += [(("p", b), b"", None) for b in range(self.nbones)]
        return lay

    def build(self, keep_layout=True):
        nb = self.nbones
        layout = self.layout if keep_layout and self.layout else self.default_layout()
        if keep_layout and self.layout:
            # the kept layout only fits the same parts
            keys = set(k for k, g, sh in layout)
            want = set([("p", b) for b in range(nb)] + [("a", k) for k, an in enumerate(self.anims) if an])
            if keys != want:
                layout = self.default_layout()
                keep_layout = False
        head = 4 + 4 * nb + 4 * (len(self.anims) + 1)
        body = bytearray()
        ofs = {}
        for key, gap, shared in layout:
            if gap is None:
                ofs[key] = shared        # kept as the original pointed it
                continue
            body += gap
            ofs[key] = head + len(body)
            body += self._anim_bytes(self.anims[key[1]]) if key[0] == "a" else self._pose_bytes(key[1])
        out = bytearray(struct.pack("<i", getattr(self, "reloc", 0)))
        out += struct.pack("<%di" % nb, *[ofs[("p", b)] for b in range(nb)])
        out += struct.pack("<%di" % len(self.anims), *[ofs[("a", k)] if an else 0
                                                       for k, an in enumerate(self.anims)])
        out += struct.pack("<i", 1)
        out += body
        if keep_layout:
            out += self.tail
        else:
            while len(out) & 3:
                out += b"\0"
        return bytes(out)

    def pose_matrix(self, bone, index):
        lib = self.poses[bone]
        if index >= len(lib):
            index = len(lib) - 1
        return lib[index]
