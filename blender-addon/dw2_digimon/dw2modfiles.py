"""Game files by number, with labels: "005C.bin" or "005C Agumon model.bin" (a space, "_" or "-"
after the 4 hex digits, then anything). The PC port reads both (host/mods.c: only the first 4
characters count); these find, write and name them the same way. Pure Python.
"""
import os
import re

_NAME = re.compile(r"^([0-9A-Fa-f]{4})(?:[ _-].*)?\.bin$", re.IGNORECASE)
_index = {}  # folder -> (mtime, {id: name})


def file_id(name):
    """"005C Agumon model.bin" -> 0x5C, else None."""
    m = _NAME.match(name)
    return int(m.group(1), 16) if m else None


def index(folder):
    """{file id: file name} of a folder (the first name in sorted order when one is there twice)."""
    try:
        mt = os.stat(folder).st_mtime_ns
    except OSError:
        return {}
    hit = _index.get(folder)
    if hit and hit[0] == mt:
        return hit[1]
    out = {}
    for n in sorted(os.listdir(folder)):
        i = file_id(n)
        if i is not None and i not in out:
            out[i] = n
    _index[folder] = (mt, out)
    return out


def duplicates(folder):
    """{file id: [names]} for numbers that are in the folder more than once (the game uses one)."""
    seen = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return {}
    for n in names:
        i = file_id(n)
        if i is not None:
            seen.setdefault(i, []).append(n)
    return {i: ns for i, ns in seen.items() if len(ns) > 1}


def find(folder, fid):
    """Path of file `fid` in folder, labelled or not, or None."""
    if not folder or fid is None or fid <= 0:
        return None
    p = os.path.join(folder, "%04X.bin" % fid)
    if os.path.isfile(p):
        return p
    n = index(folder).get(fid)
    return os.path.join(folder, n) if n else None


def clean_label(label):
    label = re.sub(r'[\\/:*?"<>|]+', "", label or "").strip()
    return label[:60]


def write(folder, fid, data, label=None):
    """Write file `fid` into folder: over the file that is there already (keeping its name, labelled
    or not), else as "XXXX label.bin". -> the file name."""
    os.makedirs(folder, exist_ok=True)
    p = find(folder, fid)
    if p is None:
        label = clean_label(label)
        p = os.path.join(folder, "%04X %s.bin" % (fid, label) if label else "%04X.bin" % fid)
    with open(p, "wb") as f:
        f.write(data)
    _index.pop(folder, None)
    return os.path.basename(p)


# ---------------------------------------------------------------- what a file is

FIXED = {
    0xCB9: "Digimon table", 0xCBA: "Digimon table 2", 0xCBB: "Digimon table 3",
    0xC6C: "Digimon stats", 0xC6F: "encounters", 0x25B: "techniques", 0x45E: "items",
    0x1FD: "system text", 0x1A1: "battle HUD layout", 0x13B: "battle HUD sprites",
}
NEW_FILE_BASE = 0x1000


def describe(fid, table):
    """A label for file `fid`: what the Digimon table (dw2digi.load_table) says it is."""
    if fid in FIXED:
        return FIXED[fid]
    for e in table:
        if e["model"] == fid:
            return "%s model" % (e["name"] or "Digimon %d" % e["id"])
    for e in table:
        for k, a in enumerate(e["anims"]):
            if a == fid:
                return "%s animations %d" % (e["name"] or "Digimon %d" % e["id"], k)
    if fid >= NEW_FILE_BASE:
        n, k = divmod(fid - NEW_FILE_BASE, 16)
        if n < 256:
            return "new Digimon %d %s" % (n, "model" if k == 0 else "animations %d" % (k - 1))
    return ""
