#!/usr/bin/env python3
"""Pull game files out of your dw2.pak into a zip (only reads the pack; changes nothing).

    python dw2_extract_models.py            every Digimon model and animation -> dw2_models.zip
    python dw2_extract_models.py --data     the Digimon / item / technique / encounter tables
                                            -> dw2_data.zip (small)
    add a path to dw2.pak at the end if it is not found by itself
    --out FOLDER                            write the files loose into FOLDER instead of a zip
                                            (forbs.py extract does this into game-data)
"""
import os
import struct
import sys
import zipfile

DATA_FILES = (0xCB9, 0xCBA, 0xCBB)
# Digimon base data (DIGIMNDT), encounter / join sets, techniques (WAZADATA), items (ITEMDATA),
# the model list, system text, the battle HUD's layout (0x1A1) and its sprites (0x13B)
TABLE_FILES = (0xC6C, 0xC6F, 0x25B, 0x45E, 0x1F8, 0x1FD, 0x1A1, 0x13B)


_argv = sys.argv[1:]
OUT_DIR = None
if "--out" in _argv:
    _i = _argv.index("--out")
    OUT_DIR = _argv[_i + 1] if _i + 1 < len(_argv) else sys.exit("--out needs a folder")
    del _argv[_i:_i + 2]
ARGS = [a for a in _argv if not a.startswith("--")]
DATA_ONLY = "--data" in _argv


def find_pak():
    if ARGS:
        return ARGS[0]
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.path.join(here, "dw2.pak")]
    for root in (here, os.getcwd()):
        for sub in ("build/native64_rel", "build/native64", "build/native", "build/linux64_rel", "."):
            cands.append(os.path.join(root, sub, "dw2.pak"))
    appdata = os.environ.get("APPDATA")
    if appdata:
        cands.append(os.path.join(appdata, "DW2-Online", "dw2.pak"))
    cands.append(os.path.expanduser("~/.local/share/DW2-Online/dw2.pak"))
    for c in cands:
        if os.path.isfile(c):
            return c
    sys.exit("dw2.pak not found. Run it as:  python dw2_extract_models.py <path to dw2.pak>")


class Pak:
    def __init__(self, path):
        self.f = open(path, "rb")
        h = self.f.read(0x50)
        if h[:6] != b"DW2PAK":
            sys.exit(path + " is not a dw2.pak")
        self.count, self.index_off, self.entry_size = struct.unpack_from("<III", h, 0x10)

    def get(self, fid):
        if fid <= 0 or fid >= self.count:
            return None
        self.f.seek(self.index_off + fid * self.entry_size)
        e = self.f.read(self.entry_size)
        fmt = struct.unpack_from("<I", e, 0x0C)[0]
        off, size = struct.unpack_from("<QQ", e, 0x10)
        if fmt != 0 or size == 0:
            return None
        self.f.seek(off)
        return self.f.read(size)


def main():
    path = find_pak()
    print("reading", path)
    pak = Pak(path)
    want = set(DATA_FILES) | set(TABLE_FILES)
    for fid in ([] if DATA_ONLY else DATA_FILES):
        d = pak.get(fid)
        base = struct.unpack_from("<I", d, 0)[0]
        p = base
        while p + 0x28 <= len(d):
            packed = struct.unpack_from("<I", d, p + 4)[0]
            if (packed >> 1) & 0x7FFF == 0:
                break
            model = struct.unpack_from("<h", d, p + 6)[0]
            anims = struct.unpack_from("<11h", d, p + 8)
            for v in (model,) + anims:
                if v > 0:
                    want.add(v)
            p += 0x28
    if OUT_DIR:
        os.makedirs(OUT_DIR, exist_ok=True)
        n = 0
        for fid in sorted(want):
            d = pak.get(fid)
            if d:
                with open(os.path.join(OUT_DIR, "%04X.bin" % fid), "wb") as f:
                    f.write(d)
                n += 1
        print("wrote %d files to %s" % (n, OUT_DIR))
        return
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dw2_data.zip" if DATA_ONLY else "dw2_models.zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for fid in sorted(want):
            d = pak.get(fid)
            if d:
                z.writestr("%04X.bin" % fid, d)
                n += 1
    print("wrote %d files to %s (%.1f MB)" % (n, out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
