#!/usr/bin/env python3
"""Remove a Digimon you made (a number the game itself doesn't have) from the mods folder, cleanly:

    python dw2remove.py <data folder> <mods folder> <number> [--yes]

  - its entry in the Digimon table (0CB9 / 0CBA / 0CBB) and its base data (0C6C) go; any Digimon
    that digivolved into it no longer does (its other digivolutions stay)
  - its own model and animation files (1000 + number x 16 + k) go
  - nothing is deleted: everything changed or removed is first moved to mods/_removed/<number> <name>
    <date>/ (the game doesn't read folders inside mods), so it can be put back
  - your save is not touched: take it out of your party and the Digimon Center FIRST, or the game
    will crash when it meets a Digimon that no longer exists
"""
import datetime
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dw2digi      # noqa: E402
import dw2modfiles  # noqa: E402
import dw2tables    # noqa: E402


class RemoveError(Exception):
    pass


def plan(data_dir, mods_dir, number):
    """What removing `number` would do: dict, or RemoveError."""
    orig = dw2tables.Source(data_dir)
    if number in dw2tables.taken_numbers(orig):
        raise RemoveError("number %d is one of the game's own Digimon; only ones you made can be removed" % number)
    src = dw2tables.Source(data_dir, mods_dir)
    tf = dw2tables.data_file_for(number)
    tp = dw2modfiles.find(mods_dir, tf)
    entry = None
    if tp:
        table = open(tp, "rb").read()
        new_table, entry = dw2tables.remove_entry(table, number)
    if entry is None:
        raise RemoveError("there's no Digimon number %d in your mods folder" % number)
    name = dw2digi.glyphs(table, int.from_bytes(entry[0:4], "little")) or "Digimon %d" % number
    model = int.from_bytes(entry[6:8], "little", signed=True)
    anims = [int.from_bytes(entry[8 + 2 * k:10 + 2 * k], "little", signed=True) for k in range(11)]
    base_p = dw2modfiles.find(mods_dir, dw2tables.DIGIMNDT)
    new_base = changed = None
    if base_p:
        new_base, _, changed = dw2tables.remove_base(open(base_p, "rb").read(), number)
    # its own files: only new file numbers (0xE5B and up) that nothing else in the table uses
    others = set()
    for e in dw2digi.load_table(data_dir, mods_dir):
        if e["id"] != number:
            others.add(e["model"])
            others.update(e["anims"])
    files = []
    for fid in [model] + anims:
        if fid >= 0xE5B and fid not in others:
            p = dw2modfiles.find(mods_dir, fid)
            if p and p not in files:
                files.append(p)
    return {"number": number, "name": name, "table_path": tp, "table": new_table, "base_path": base_p,
            "base": new_base, "evo_changed": changed or [], "files": files,
            "names": {i: e["name"] for e in dw2digi.load_table(data_dir, mods_dir) for i in [e["id"]]}}


def describe(p):
    out = ["Remove %s (number %d):" % (p["name"], p["number"]),
           "  - its entry from %s" % os.path.basename(p["table_path"])]
    if p["base_path"]:
        out.append("  - its stats from %s" % os.path.basename(p["base_path"]))
    for i in p["evo_changed"]:
        out.append("  - %s no longer digivolves into it (its other digivolutions stay)" % p["names"].get(i, "#%d" % i))
    for f in p["files"]:
        out.append("  - %s" % os.path.basename(f))
    return "\n".join(out)


def apply(p, mods_dir):
    """Back everything up into mods/_removed/..., then write the new tables and delete the files.
    -> the backup folder."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H%M%S")
    back = os.path.join(mods_dir, "_removed", dw2modfiles.clean_label("%d %s %s" % (p["number"], p["name"], stamp)))
    os.makedirs(back, exist_ok=True)
    for path in [p["table_path"], p["base_path"]] + p["files"]:
        if path:
            shutil.copy2(path, os.path.join(back, os.path.basename(path)))
    with open(os.path.join(back, "README.txt"), "w") as f:
        f.write("Removed %s (number %d) on %s.\nTo put it back, copy these files back into the mods folder "
                "(over the ones there).\n" % (p["name"], p["number"], stamp))
    with open(p["table_path"], "wb") as f:
        f.write(p["table"])
    if p["base_path"] and p["base"] is not None:
        with open(p["base_path"], "wb") as f:
            f.write(p["base"])
    for path in p["files"]:
        os.remove(path)
    return back


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 3:
        print(__doc__)
        return 1
    data_dir, mods_dir, number = args[0], args[1], int(args[2], 0)
    try:
        p = plan(data_dir, mods_dir, number)
    except RemoveError as ex:
        print("Can't:", ex)
        return 1
    print(describe(p))
    print("\nFirst take it out of your save (party and Digimon Center): the game crashes on a Digimon that "
          "no longer exists.")
    if "--yes" not in argv and input("Remove it? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing changed.")
        return 1
    back = apply(p, mods_dir)
    print("Removed. A copy of everything is in %s" % back)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
