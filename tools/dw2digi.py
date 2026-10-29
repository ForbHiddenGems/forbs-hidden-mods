"""Digimon table (DigiData, files 0xCB9..0xCBB): id, name, model file, anim files."""
import os, struct

try:
    from . import dw2modfiles
except ImportError:
    import dw2modfiles

PUNCT = {0x42: "&", 0x44: "?", 0x45: "!", 0x46: "/", 0x49: "-", 0x54: ",", 0x55: ".", 0x56: "'",
         0x57: '"', 0x58: ";", 0x59: ":", 0x5A: "%", 0x5B: "+", 0x5C: "=", 0x5D: "#", 0xFD: " "}


def glyphs(b, o):
    s = ""
    while o < len(b):
        c = b[o]
        if c == 0xFF:
            break
        if c < 10:
            s += chr(48 + c)
        elif c < 0x24:
            s += chr(65 + c - 10)
        elif c < 0x3E:
            s += chr(97 + c - 0x24)
        else:
            s += PUNCT.get(c, "")
        o += 1
    return s


def _find(folders, fid):
    """The file in the first folder that has it ("005C.bin" or labelled, "005C Agumon model.bin")."""
    for f in folders:
        p = dw2modfiles.find(f, fid)
        if p:
            return p
    return None


def load_table(folder, mods=None):
    """The Digimon table; files in the mods folder (when given) win, as in the game."""
    out = []
    for fid in (0xCB9, 0xCBA, 0xCBB):
        p = _find((mods, folder), fid)
        if p is None:
            continue
        d = open(p, "rb").read()
        base = struct.unpack_from("<I", d, 0)[0]
        o = base
        while o + 0x28 <= len(d):
            name_ofs, packed = struct.unpack_from("<iI", d, o)
            did = (packed >> 1) & 0x7FFF
            if did == 0:
                break
            model = struct.unpack_from("<h", d, o + 6)[0]
            anims = list(struct.unpack_from("<11h", d, o + 8))
            out.append({"id": did, "name": glyphs(d, name_ofs), "model": model, "anims": anims,
                        "table": fid})
            o += 0x28
    return out
