"""Add a new Digimon to DW2's tables, as replacement files for the PC port's mods folder.

    python dw2newdigi.py <data folder> <clone of> <new number> <name> <out folder>
    e.g.  python dw2newdigi.py dw2_data Agumon 170 Forbmon mods

The new Digimon starts as a copy of an existing one (model, animations, base data, digivolutions)
under its own number and name. Writes the changed tables: 0CB9 / 0CBA / 0CBB.bin (Digimon
table: name, model, animations) and 0C6C.bin (base data: type, rank, growth, digivolutions).

Numbers: 1..255 (a party Digimon stores its number in one byte); the table file is chosen by
number as the game does (Digi_GetDataFileId: below 300 0CB9, 400..500 0CBB, else 0CBA).
"""
import os
import struct
import sys

PUNCT = "&?!/-,.'\";:%+="
PUNCT_GLYPH = [0x42, 0x44, 0x45, 0x46, 0x49, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x5B, 0x5C]

DIGIMNDT = 0xC6C
BASE_REC = 0x12
DATA_REC = 0x28


def encode_name(text):
    """Plain text -> the game's glyph codes (host/devedit.c DevEdit_EncodeText), 0xFF ended."""
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


def data_file_for(digi_id):
    if digi_id < 0x12C:
        return 0xCB9
    if 0x190 <= digi_id < 0x1F5:
        return 0xCBB
    return 0xCBA


def _grow(buf, need):
    """Room up to `need` bytes, in whole 2 KB sectors as on the disc."""
    if len(buf) < need:
        buf += b"\0" * (((need + 0x7FF) & ~0x7FF) - len(buf))
    return buf


def table_records(d):
    """DigiData records: (start, [(offset, id)], terminator offset)."""
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


def find_record(files, digi_id):
    d = files[data_file_for(digi_id)]
    _, recs, _ = table_records(d)
    for p, did in recs:
        if did == digi_id:
            return bytes(d[p:p + DATA_REC])
    return None


def add_digidata(d, src_rec, new_id, name_glyphs):
    """A copy of the record src_rec under new_id and a new name, inserted in number order. The
    records are the last part of the file, followed by zero padding: the name goes into that
    padding after the (moved) end marker, so no other offset in the file changes."""
    d = bytearray(d)
    start, recs, term = table_records(d)
    if any(did == new_id for _, did in recs):
        raise ValueError("number %d is taken" % new_id)
    if any(d[term:term + DATA_REC]):
        raise ValueError("unexpected table layout (no end marker)")
    after = d[term + DATA_REC:]
    if any(after):
        raise ValueError("unexpected table layout (data after the records)")
    at = next((p for p, did in recs if did > new_id), term)
    rec = bytearray(src_rec)
    lo = struct.unpack_from("<H", rec, 4)[0]
    struct.pack_into("<H", rec, 4, (lo & 1) | (new_id << 1))
    new_term = term + DATA_REC
    name_at = (new_term + DATA_REC + 3) & ~3
    struct.pack_into("<I", rec, 0, name_at)
    body = bytes(d[start:at]) + bytes(rec) + bytes(d[at:term]) + b"\0" * DATA_REC
    d = _grow(d, name_at + len(name_glyphs))
    d[start:start + len(body)] = body
    d[name_at:name_at + len(name_glyphs)] = name_glyphs
    return bytes(d)


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


def add_base(d, src_id, new_id):
    """DIGIMNDT: records of 0x12 from offset 0 (s16 id first), ended by id 0; a copy of the
    source's record under the new number, in number order."""
    d = bytearray(d)
    recs, term = base_records(d)
    src = next((d[p:p + BASE_REC] for p, did in recs if did == src_id), None)
    if src is None:
        raise ValueError("no base data for number %d" % src_id)
    if any(did == new_id for _, did in recs):
        raise ValueError("number %d already has base data" % new_id)
    tail_end = term + BASE_REC
    if any(d[tail_end:]):
        # something follows the end marker: keep it in place by not moving anything past it;
        # only safe when there is room, which we check
        raise ValueError("unexpected base data layout (data after the records)")
    at = next((p for p, did in recs if did > new_id), term)
    rec = bytearray(src)
    struct.pack_into("<h", rec, 0, new_id)
    body = bytes(d[:at]) + bytes(rec) + bytes(d[at:term]) + b"\0" * BASE_REC
    d = _grow(d, len(body))
    d[:len(body)] = body
    return bytes(d)


def make(folder, clone_name, new_id, new_name, out):
    import dw2digi
    table = dw2digi.load_table(folder)
    src = next((e for e in table if e["name"].lower() == clone_name.lower()), None)
    if src is None:
        raise ValueError("no Digimon called %s" % clone_name)
    if not 1 <= new_id <= 255:
        raise ValueError("the number must be 1..255")
    files = {}
    import dw2modfiles
    for fid in (0xCB9, 0xCBA, 0xCBB, DIGIMNDT):
        p = dw2modfiles.find(folder, fid)
        if p:
            files[fid] = open(p, "rb").read()
    rec = find_record(files, src["id"])
    tf = data_file_for(new_id)
    written = {}
    written[tf] = add_digidata(files[tf], rec, new_id, encode_name(new_name))
    if DIGIMNDT in files:
        written[DIGIMNDT] = add_base(files[DIGIMNDT], src["id"], new_id)
    for fid, data in written.items():
        dw2modfiles.write(out, fid, data, dw2modfiles.FIXED.get(fid))
    return src, written


if __name__ == "__main__":
    folder, clone, num, name, out = sys.argv[1:6]
    src, written = make(folder, clone, int(num, 0), name, out)
    print("%s (number %d) is a copy of %s (number %d): wrote %s" % (
        name, int(num, 0), src["name"], src["id"], ", ".join("%04X.bin" % f for f in sorted(written))))
