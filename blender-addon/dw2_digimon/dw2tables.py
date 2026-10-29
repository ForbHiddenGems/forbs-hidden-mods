"""DW2 tables the add-on edits: a Digimon's table entry (name, model, animations), its base data
(type, rank, specialty, stat growth, technique, DNA group, digivolutions), and the names it shows
them by (types / ranks / specialties from the system text, technique names). Pure Python.

Files are read through a Source: the game's mods folder first, then the data folder (the
unzipped dw2_models.zip / dw2_data.zip), as the PC port itself reads them.
"""
import os
import struct

try:
    from . import dw2digi, dw2modfiles
except ImportError:
    import dw2digi
    import dw2modfiles

DIGIMNDT = 0xC6C
WAZADATA = 0x25B
SYSTEXT = 0x1FD
TABLES = (0xCB9, 0xCBA, 0xCBB)
DATA_REC = 0x28
BASE_REC = 0x12
NEW_FILE_BASE = 0x1000          # a new Digimon's files: 0x1000 + number * 16 + k (k 0 model)

PUNCT = "&?!/-,.'\";:%+="
PUNCT_GLYPH = [0x42, 0x44, 0x45, 0x46, 0x49, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x5B, 0x5C]


class Source:
    def __init__(self, data_dir, mods_dir=None):
        self.dirs = [d for d in (mods_dir, data_dir) if d]
        # zips unzipped into a folder of their own inside the data folder (data/dw2_data/...)
        if data_dir and os.path.isdir(data_dir):
            for n in sorted(os.listdir(data_dir)):
                sub = os.path.join(data_dir, n)
                if os.path.isdir(sub):
                    self.dirs.append(sub)

    def path(self, fid):
        for d in self.dirs:
            p = dw2modfiles.find(d, fid)
            if p:
                return p
        return None

    def get(self, fid):
        p = self.path(fid)
        return open(p, "rb").read() if p else None


# ---------------------------------------------------------------- text

def encode_name(text):
    out = bytearray()
    for c in text:
        if c.isdigit():
            out.append(ord(c) - 48)
        elif "A" <= c <= "Z":
            out.append(0x0A + ord(c) - 65)
        elif "a" <= c <= "z":
            out.append(0x24 + ord(c) - 97)
        elif c in " _":
            out.append(0xFD)
        elif c in PUNCT:
            out.append(PUNCT_GLYPH[PUNCT.index(c)])
        else:
            raise ValueError("the game has no letter for %r" % c)
    if not 1 <= len(out) <= 13:
        raise ValueError("a name is 1 to 13 letters")
    return bytes(out) + b"\xff"


def labels(src):
    """{'type': [3 names], 'rank': [4], 'specialty': [6]} from the system text (digistatus.c);
    plain fallbacks when the file is missing."""
    out = {"type": ["Vaccine", "Data", "Virus"], "rank": ["Rookie", "Champion", "Ultimate", "Mega"],
           "specialty": ["Fire", "Battle", "Air", "Earth", "Ice", "Mecha"]}
    d = src.get(SYSTEXT)
    if d and len(d) > 0xD0 * 4:
        def t(k):
            o = struct.unpack_from("<I", d, k * 4)[0]
            return dw2digi.glyphs(d, o) if o < len(d) else ""
        names = [t(0xC3 + i) for i in range(3)]
        if all(names):
            out["type"] = names
        names = [t(0xC6 + i) for i in range(4)]
        if all(names):
            out["rank"] = names
        names = [t(0xCA + i) for i in range(6)]
        if all(names):
            out["specialty"] = names
    return out


def techniques(src):
    """[(id, name)] from WAZADATA (records of 0x44 from word 0; name offset at +0x24)."""
    d = src.get(WAZADATA)
    out = []
    if not d:
        return out
    p = struct.unpack_from("<I", d, 0)[0]
    while p + 0x44 <= len(d):
        tid = struct.unpack_from("<h", d, p)[0]
        if tid == 0:
            break
        no = struct.unpack_from("<I", d, p + 0x24)[0]
        out.append((tid, dw2digi.glyphs(d, no) if no < len(d) else "#%d" % tid))
        p += 0x44
    return out


# ---------------------------------------------------------------- base data (DIGIMNDT)

def base_records(d):
    recs = []
    p = 0
    while p + BASE_REC <= len(d):
        did = struct.unpack_from("<h", d, p)[0]
        if did == 0:
            break
        recs.append((p, did))
        p += BASE_REC
    return recs, p


def parse_base(rec):
    """0x12-byte record -> dict (the layout host/devdata.c reads)."""
    did, skill, dna, a, g = struct.unpack_from("<hBBHH", rec, 0)
    bounds = list(rec[8:13])
    targets = list(rec[13:17])
    evos = []                                   # [(target, from DP)]
    if targets[0]:
        for i in range(4):
            evos.append((targets[i], bounds[i]))
            if bounds[i + 1] == 0:
                break
    return {"id": did, "technique": skill, "dna": dna, "type": a & 15, "rank": a >> 4 & 15,
            "specialty": a >> 8 & 15, "growth": [a >> 12, g & 15, g >> 4 & 15, g >> 8 & 15, g >> 12],
            "evos": evos, "raw": bytes(rec)}


def build_base(b):
    """dict -> 0x12-byte record. The digivolutions: Digi_GetEvolutionTarget takes the first range
    [bound i, bound i+1) holding the DP, the last one open-ended; no entries = none."""
    rec = bytearray(b.get("raw", b"\0" * BASE_REC))
    gr = [max(0, min(15, int(x))) for x in b["growth"]]
    a = (b["type"] & 15) | (b["rank"] & 15) << 4 | (b["specialty"] & 15) << 8 | gr[0] << 12
    g = gr[1] | gr[2] << 4 | gr[3] << 8 | gr[4] << 12
    struct.pack_into("<hBBHH", rec, 0, b["id"], b["technique"] & 255, b["dna"] & 255, a, g)
    evos = [(t, dp) for t, dp in b["evos"] if t][:4]
    bounds = [0] * 5
    targets = [0] * 4
    for i, (t, dp) in enumerate(evos):
        targets[i] = t & 255
        bounds[i] = max(0, min(255, int(dp)))
    if len(evos) > 1:
        # bound i+1 ends range i: the next entry's start; after the last one, 0 ends the list
        for i in range(len(evos) - 1):
            if bounds[i + 1] <= bounds[i]:
                bounds[i + 1] = min(255, bounds[i] + 1)
    if len(evos) < 4:
        bounds[len(evos)] = 0
    else:
        bounds[4] = rec[12]          # four entries: keep the record's own last bound
    rec[8:13] = bytes(bounds)
    rec[13:17] = bytes(targets)
    return bytes(rec)


def upsert_base(d, rec):
    """Replace the record with the same number, or insert it in number order."""
    d = bytearray(d)
    did = struct.unpack_from("<h", rec, 0)[0]
    recs, term = base_records(d)
    for p, i in recs:
        if i == did:
            d[p:p + BASE_REC] = rec
            return bytes(d)
    at = next((p for p, i in recs if i > did), term)
    body = bytes(d[:at]) + bytes(rec) + bytes(d[at:term]) + b"\0" * BASE_REC
    if any(d[term + BASE_REC:]):
        raise ValueError("base data: unexpected layout after the records")
    if len(d) < len(body):
        d += b"\0" * (((len(body) + 0x7FF) & ~0x7FF) - len(d))
    d[:len(body)] = body
    return bytes(d)


# ---------------------------------------------------------------- Digimon table (MODELDT)

def data_file_for(digi_id):
    if digi_id < 0x12C:
        return 0xCB9
    if 0x190 <= digi_id < 0x1F5:
        return 0xCBB
    return 0xCBA


def table_records(d):
    start = struct.unpack_from("<I", d, 0)[0]
    recs = []
    p = start
    while p + DATA_REC <= len(d):
        did = (struct.unpack_from("<H", d, p + 4)[0] >> 1) & 0x7FFF
        if did == 0:
            break
        recs.append((p, did))
        p += DATA_REC
    return start, recs, p


def get_entry(src, digi_id):
    d = src.get(data_file_for(digi_id))
    if not d:
        return None
    _, recs, _ = table_records(d)
    for p, i in recs:
        if i == digi_id:
            return bytes(d[p:p + DATA_REC])
    return None


def _names_end(d, term):
    """First free byte for a new name: past the end marker and any names already put there."""
    p = term + DATA_REC
    while p < len(d) and any(d[p:]):
        # skip names written after the records by earlier edits (0xFF ended)
        q = p
        while q < len(d) and d[q] == 0:
            q += 1
        if q >= len(d):
            break
        e = d.index(b"\xff", q) if b"\xff" in d[q:] else len(d)
        p = e + 1
    return (p + 3) & ~3


def upsert_entry(d, digi_id, rec_template, name_glyphs=None, model=None, anims=None):
    """The table entry for digi_id, from rec_template (an existing entry: battle effect
    positions etc.), with its number, and optionally a new name / model / animation files.
    Inserted in number order when new. Names added go into the zero padding after the
    records (the file's offsets elsewhere stay as they are)."""
    d = bytearray(d)
    start, recs, term = table_records(d)
    existing = next((p for p, i in recs if i == digi_id), None)
    rec = bytearray(d[existing:existing + DATA_REC] if existing is not None else rec_template)
    lo = struct.unpack_from("<H", rec, 4)[0]
    struct.pack_into("<H", rec, 4, (lo & 1) | (digi_id << 1))
    if model is not None:
        struct.pack_into("<h", rec, 6, model)
    if anims is not None:
        struct.pack_into("<11h", rec, 8, *anims)
    if existing is not None:
        d[existing:existing + DATA_REC] = rec
        term_after = term
    else:
        at = next((p for p, i in recs if i > digi_id), term)
        tail = bytes(d[term + DATA_REC:]).rstrip(b"\0")      # names added earlier, if any
        body = bytes(d[start:at]) + bytes(rec) + bytes(d[at:term]) + b"\0" * DATA_REC
        new_len = start + len(body) + len(tail)
        if len(d) < new_len:
            d += b"\0" * (((new_len + 0x7FF) & ~0x7FF) - len(d))
        # names placed after the records by earlier edits move with the tail: fix their offsets
        moved = {}
        d2 = bytearray(d)
        d2[start:start + len(body)] = body
        d2[start + len(body):] = b"\0" * (len(d2) - start - len(body))
        d2[start + len(body):start + len(body) + len(tail)] = tail
        old_tail_start = term + DATA_REC
        _, recs2, term2 = table_records(d2)
        for p, _i in recs2:
            no = struct.unpack_from("<I", d2, p)[0]
            if no >= old_tail_start:
                struct.pack_into("<I", d2, p, no + DATA_REC)
        d = d2
        term_after = term2
        existing = next(p for p, i in recs2 if i == digi_id)
    if name_glyphs is not None:
        at = _names_end(d, term_after)
        if len(d) < at + len(name_glyphs):
            d += b"\0" * (((at + len(name_glyphs) + 0x7FF) & ~0x7FF) - len(d))
        d[at:at + len(name_glyphs)] = name_glyphs
        struct.pack_into("<I", d, existing, at)
    return bytes(d)


def taken_numbers(src):
    """Digimon numbers in use (table or base data)."""
    used = set()
    for fid in TABLES:
        d = src.get(fid)
        if d:
            used.update(i for _, i in table_records(d)[1])
    d = src.get(DIGIMNDT)
    if d:
        used.update(i for _, i in base_records(d)[0])
    return used


def free_numbers(src):
    used = taken_numbers(src)
    return [i for i in range(1, 256) if i not in used]


def new_files(number):
    """File numbers for a new Digimon: model, then one per animation slot."""
    base = NEW_FILE_BASE + number * 16
    return base, [base + 1 + k for k in range(11)]


# ---------------------------------------------------------------- removing a Digimon

def remove_entry(d, digi_id):
    """The table without digi_id's entry (the records after it move up; its name stays behind
    unused). -> (bytes, removed record or None)."""
    d = bytearray(d)
    start, recs, term = table_records(d)
    at = next((p for p, i in recs if i == digi_id), None)
    if at is None:
        return bytes(d), None
    rec = bytes(d[at:at + DATA_REC])
    d[at:term] = d[at + DATA_REC:term + DATA_REC]   # the end marker moves up too
    d[term:term + DATA_REC] = b"\0" * DATA_REC
    return bytes(d), rec


def remove_base(d, digi_id):
    """Base data without digi_id's record, and without it as anyone's digivolution.
    -> (bytes, removed record or None, [ids whose digivolutions changed])."""
    d = bytearray(d)
    recs, term = base_records(d)
    at = next((p for p, i in recs if i == digi_id), None)
    rec = None
    if at is not None:
        rec = bytes(d[at:at + BASE_REC])
        d[at:term] = d[at + BASE_REC:term + BASE_REC]
        d[term:term + BASE_REC] = b"\0" * BASE_REC
    changed = []
    recs, term = base_records(d)
    for p, i in recs:
        b = parse_base(d[p:p + BASE_REC])
        if any(t == digi_id for t, _ in b["evos"]):
            b["evos"] = [(t, dp) for t, dp in b["evos"] if t != digi_id]
            d[p:p + BASE_REC] = build_base(b)
            changed.append(i)
    return bytes(d), rec, changed
