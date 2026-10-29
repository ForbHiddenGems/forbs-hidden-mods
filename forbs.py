#!/usr/bin/env python3
"""Forbs Hidden Mods: everything from this one folder.

    python forbs.py setup <your DW2-PC folder>   once: copy your DW2-PC here, apply the mods
    python forbs.py build [--dev | --both]       build the game (release by default)
    python forbs.py play  [--dev]                start the game
    python forbs.py extract                      game data for the Blender add-on -> game-data
    python forbs.py addon                        the Blender add-on -> dist/dw2_digimon_addon.zip
    python forbs.py update                       after new patches: apply + build both + add-on
    python forbs.py apply                        put the patches in patches/series on DW2-PC again
    python forbs.py status                       what's where
    python forbs.py clean [--yes]                tidy DW2-PC: mod files to mods/, leftovers out
    python forbs.py names [--undo]               label mods/ files: 005C.bin -> 005C Agumon model.bin
    python forbs.py mine                         the Digimon you made (their numbers)
    python forbs.py remove <number>              remove one you made, cleanly (backed up first)
    python forbs.py config --mingw C:\\mingw64 --sdl3 C:\\SDL3    the compiler and SDL3 folders

The folder:
    patches/  tools/  blender-addon/    the mods themselves (these go on GitHub)
    DW2-PC/       the game's source and your builds, made by setup  (never uploaded)
    game-data/    files from your dw2.pak for the add-on              (never uploaded)
    mods/         your Digimon: every build and the add-on use this   (never uploaded)
    dist/         the add-on zip to install in Blender                (never uploaded)

Every build gets a mods-folder.txt pointing at mods/, so the release build, the dev build and
the Blender add-on all share the one mods folder. DW2-PC/ is managed by this script: apply
resets its source to DW2-PC commit 1dbb32a and puts the patches on, so make changes as patches.
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DW2 = os.path.join(ROOT, "DW2-PC")
GAME_DATA = os.path.join(ROOT, "game-data")
MODS = os.path.join(ROOT, "mods")
DIST = os.path.join(ROOT, "dist")
SERIES = os.path.join(ROOT, "patches", "series")
ADDON = os.path.join(ROOT, "blender-addon", "dw2_digimon")
CONFIG = os.path.join(ROOT, "forbs.json")
APPLIED = os.path.join(DW2, ".git", "forbs-applied")

UPSTREAM = "https://github.com/Wyrelade/DW2-PC.git"
BASE = "1dbb32a0332a78d5e9afbe4d26c62d86cc5e3f76"     # v1.0.0-beta: English and Spanish
BRANCH = "forbs-mods"
WINDOWS = os.name == "nt"


def die(msg):
    sys.exit("\nSTOPPED: " + msg)


def say(msg):
    print(msg, flush=True)


def load_config():
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


def git(*args, check=True, quiet=False):
    if shutil.which("git") is None:
        die("Git isn't installed (or not in PATH). Install it from git-scm.com and reopen PowerShell.")
    r = subprocess.run(["git", "-C", DW2] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        die("git %s failed:\n%s" % (" ".join(args), (r.stderr or r.stdout).strip()))
    if not quiet and r.stdout.strip():
        say(r.stdout.rstrip())
    return r


def build_dirs(dev):
    if WINDOWS:
        return ["native64"] if dev else ["native64_rel", "play"]
    return ["linux64"] if dev else ["linux64_rel"]


def exe_name():
    return "dw2.exe" if WINDOWS else "dw2"


def find_pak():
    names = ["native64_rel", "play", "native64", "native", "native_rel", "linux64_rel", "linux64"]
    cands = [os.path.join(DW2, "build", n, "dw2.pak") for n in names]
    if os.environ.get("APPDATA"):
        cands.append(os.path.join(os.environ["APPDATA"], "DW2-Online", "dw2.pak"))
    cands.append(os.path.expanduser("~/.local/share/DW2-Online/dw2.pak"))
    return next((c for c in cands if os.path.isfile(c)), None)


def series_files():
    files = sorted(glob.glob(os.path.join(SERIES, "*.patch")))
    if not files:
        die("no patches in " + SERIES)
    return files


def series_hash():
    h = hashlib.sha256()
    for p in series_files():
        with open(p, "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:16]


def added_files(patch):
    """Files a patch creates (+++ b/x after --- /dev/null)."""
    out = []
    prev = ""
    with open(patch, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("+++ b/") and prev.startswith("--- /dev/null"):
                out.append(line[6:].rstrip("\r\n"))
            prev = line
    return out


# ---------------------------------------------------------------- setup


def cmd_setup(args):
    if not args:
        die("say where your DW2-PC folder is, e.g.\n  python forbs.py setup C:\\Users\\Shaun\\Desktop\\DMW2\\DW2-PC")
    old = os.path.abspath(os.path.expanduser(args[0]))
    if not os.path.isfile(os.path.join(old, "tools", "build_native.py")):
        die(old + " doesn't look like a DW2-PC folder (no tools/build_native.py in it)")
    if os.path.exists(DW2):
        die(DW2 + " already exists. Setup only runs once.\n"
            "If you copied a DW2-PC folder in by hand, tidy it with  python forbs.py clean")

    say("Copying %s\n     -> %s" % (old, DW2))
    say("(your old folder is left exactly as it is)")
    old_build = os.path.join(old, "build")
    count = [0, 0]

    def ignore(d, names):
        d = os.path.abspath(d)
        skip = set()
        if d == old:
            skip |= {n for n in names if n.startswith("venv") or n.startswith(".venv")}
        # builds: keep only the game pack. The rest is rebuilt here (CMake files hold the old path).
        if os.path.dirname(d) == old_build:
            skip |= {n for n in names if not n.lower().endswith(".pak")}
        return skip

    def link_or_copy(src, dst):
        count[0] += 1
        if src.lower().endswith(".pak"):
            try:
                os.link(src, dst)        # same drive: no second copy of the 400 MB pack
                count[1] += 1
                return dst
            except OSError:
                pass
        if count[0] % 2000 == 0:
            say("  %d files..." % count[0])
        return shutil.copy2(src, dst)

    shutil.copytree(old, DW2, ignore=ignore, copy_function=link_or_copy, symlinks=True)
    say("  copied %d files" % count[0])

    # mods from the old builds and the user data folder -> the one mods folder
    os.makedirs(MODS, exist_ok=True)
    found = glob.glob(os.path.join(old_build, "*", "mods", "*.bin"))
    if os.environ.get("APPDATA"):
        found += glob.glob(os.path.join(os.environ["APPDATA"], "DW2-Online", "mods", "*.bin"))
    n = gather_mods([p for p in found])
    if n:
        say("  %d mod files gathered into mods\\ (the newest copy of each)" % n)

    if not os.path.isdir(os.path.join(DW2, ".git")):
        say("Your DW2-PC folder wasn't a Git clone: fetching its history from GitHub...")
        tmp = os.path.join(ROOT, ".dw2-clone-tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        r = subprocess.run(["git", "clone", "--no-checkout", "-q", UPSTREAM, tmp])
        if r.returncode != 0:
            die("couldn't download DW2-PC from GitHub")
        shutil.move(os.path.join(tmp, ".git"), os.path.join(DW2, ".git"))
        shutil.rmtree(tmp, ignore_errors=True)
    if git("cat-file", "-e", BASE + "^{commit}", check=False, quiet=True).returncode != 0:
        say("Fetching DW2-PC commit 1dbb32a from GitHub...")
        git("fetch", "-q", UPSTREAM, check=True)

    cfg = load_config()
    cfg.setdefault("mingw", os.environ.get("DW2_MINGW", "C:\\mingw64" if WINDOWS else ""))
    cfg.setdefault("sdl3", os.environ.get("DW2_SDL3", "C:\\SDL3" if WINDOWS else ""))
    cfg["old_dw2pc"] = old
    save_config(cfg)

    cmd_apply([])
    os.makedirs(GAME_DATA, exist_ok=True)
    say("\nSetup done. Next:\n"
        "  python forbs.py build --both     build the release and dev games\n"
        "  python forbs.py extract          game data for Blender\n"
        "  python forbs.py addon            the add-on to install in Blender\n"
        "Once the new builds work you can delete your old DW2-PC folder (%s)." % old)


# ---------------------------------------------------------------- apply


def cmd_apply(args):
    if not os.path.isdir(os.path.join(DW2, ".git")):
        die("no DW2-PC here yet: run  python forbs.py setup <your DW2-PC folder>  first")
    patches = series_files()
    say("Putting %d patches on DW2-PC (commit 1dbb32a)..." % len(patches))
    if os.path.isdir(os.path.join(DW2, ".git", "rebase-apply")):
        git("am", "--abort", check=False, quiet=True)
    git("checkout", "-q", "-f", "-B", BRANCH, BASE)
    # files the patches create may be lying around untracked (patches applied by hand before)
    for p in patches:
        for rel in added_files(p):
            path = os.path.join(DW2, rel)
            tracked = git("ls-files", "--error-unmatch", rel, check=False, quiet=True).returncode == 0
            if os.path.isfile(path) and not tracked:
                os.remove(path)
    r = subprocess.run(["git", "-C", DW2, "-c", "user.name=Forbs Hidden Mods", "-c",
                        "user.email=forbs@localhost", "-c", "commit.gpgsign=false",
                        "am", "-q", "--whitespace=nowarn"] + patches, capture_output=True, text=True)
    if r.returncode != 0:
        git("am", "--abort", check=False, quiet=True)
        die("a patch didn't apply:\n" + (r.stdout + r.stderr).strip())
    with open(APPLIED, "w") as f:
        f.write(series_hash())
    say("  done: DW2-PC is on branch %s with every patch" % BRANCH)


def ensure_applied():
    try:
        with open(APPLIED) as f:
            if f.read().strip() == series_hash():
                return
    except OSError:
        pass
    say("The patches changed since they were last put on DW2-PC.")
    cmd_apply([])


# ---------------------------------------------------------------- build / play


def write_mods_pointer(d):
    os.makedirs(MODS, exist_ok=True)
    folder = os.path.join(DW2, "build", d)
    if os.path.isdir(folder):
        with open(os.path.join(folder, "mods-folder.txt"), "w") as f:
            f.write(MODS + "\n")


def build(dev):
    cfg = load_config()
    env = dict(os.environ)
    if cfg.get("mingw"):
        env["DW2_MINGW"] = cfg["mingw"]
    if cfg.get("sdl3"):
        env["DW2_SDL3"] = cfg["sdl3"]
    cmd = [sys.executable, os.path.join("tools", "build_native.py")]
    if WINDOWS:
        cmd += ["--arch", "x64"]
    if not dev:
        cmd.append("--release")
    say("\n== Building the %s game ==" % ("dev" if dev else "release"))
    r = subprocess.run(cmd, cwd=DW2, env=env)
    if r.returncode != 0:
        die("the build failed (see above). If it can't find gcc or SDL3:\n"
            "  python forbs.py config --mingw C:\\mingw64 --sdl3 C:\\SDL3")
    for d in build_dirs(dev):
        write_mods_pointer(d)
    if find_pak() is None:
        say("NOTE: no dw2.pak found yet. The game builds it from your disc image the first time it runs.")


def cmd_build(args):
    if not os.path.isdir(DW2):
        die("run  python forbs.py setup <your DW2-PC folder>  first")
    ensure_applied()
    if "--both" in args:
        build(False)
        build(True)
    else:
        build("--dev" in args)
    say("\nBuilt. Start it with  python forbs.py play%s" % (" --dev" if "--dev" in args else ""))


def cmd_play(args):
    dev = "--dev" in args
    d = build_dirs(dev)[0]
    exe = os.path.join(DW2, "build", d, exe_name())
    if not os.path.isfile(exe):
        die("no %s build yet: run  python forbs.py build%s" % ("dev" if dev else "release", " --dev" if dev else ""))
    write_mods_pointer(d)
    say("Starting " + exe)
    subprocess.Popen([exe], cwd=os.path.dirname(exe))


# ---------------------------------------------------------------- Blender


def cmd_extract(args):
    pak = args[0] if args else find_pak()
    if pak is None:
        die("no dw2.pak found. Build and start the game once, or give its path:\n"
            "  python forbs.py extract <path to dw2.pak>")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "dw2_extract_models.py"),
                        "--out", GAME_DATA, pak])
    if r.returncode != 0:
        die("extracting failed")


def cmd_addon(args):
    if not os.path.isdir(ADDON):
        die("no add-on at " + ADDON)
    os.makedirs(DIST, exist_ok=True)
    os.makedirs(MODS, exist_ok=True)
    os.makedirs(GAME_DATA, exist_ok=True)
    out = os.path.join(DIST, "dw2_digimon_addon.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, files in os.walk(ADDON):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for n in files:
                if n.endswith(".pyc") or n == "forbs_paths.json":
                    continue
                p = os.path.join(dirpath, n)
                z.write(p, os.path.join("dw2_digimon", os.path.relpath(p, ADDON)))
        z.writestr("dw2_digimon/forbs_paths.json", json.dumps({"data": GAME_DATA, "mods": MODS}, indent=2))
    say("Wrote %s\nInstall it in Blender (Edit > Preferences > Add-ons > Install from Disk), then\n"
        "restart Blender. It uses game-data and mods in this folder by itself." % out)


# ---------------------------------------------------------------- update / status / config


def gather_mods(folders):
    """Mod files from old places into mods/: the newest copy of each wins."""
    os.makedirs(MODS, exist_ok=True)
    mf = modfiles()
    found = []
    for pat in folders:
        found += glob.glob(pat)
    ids = set()
    for p in sorted(found, key=os.path.getmtime):
        fid = mf.file_id(os.path.basename(p))
        if fid is None:
            continue
        dst = mf.find(MODS, fid) or os.path.join(MODS, os.path.basename(p))
        if not os.path.exists(dst) or os.path.getmtime(p) > os.path.getmtime(dst):
            shutil.copy2(p, dst)  # into the file already there for that number, keeping its name
        ids.add(fid)
    return len(ids)


def modfiles():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import dw2modfiles
    return dw2modfiles


def _need_tables():
    modfiles()
    if not os.path.isfile(os.path.join(GAME_DATA, "0CB9.bin")):
        die("game-data has no Digimon table yet: run  python forbs.py extract  first")


def cmd_mine(args):
    """The Digimon in mods/ that the game itself doesn't have."""
    _need_tables()
    import dw2digi
    import dw2tables
    orig = dw2tables.taken_numbers(dw2tables.Source(GAME_DATA))
    mine = [e for e in dw2digi.load_table(GAME_DATA, MODS) if e["id"] not in orig]
    if not mine:
        say("No Digimon of your own in mods\\ (edits of the game's own Digimon aren't listed).")
    for e in sorted(mine, key=lambda e: e["id"]):
        say("  %3d  %s  (model file %04X)" % (e["id"], e["name"], e["model"]))


def cmd_remove(args):
    """Remove a Digimon you made: its table entry, stats, digivolutions into it and its own files,
    all backed up into mods/_removed/ first (tools/dw2remove.py)."""
    _need_tables()
    import dw2remove
    nums = [a for a in args if not a.startswith("--")]
    if len(nums) != 1:
        die("say which number, e.g.  python forbs.py remove 170   (python forbs.py mine lists them)")
    try:
        p = dw2remove.plan(GAME_DATA, MODS, int(nums[0], 0))
    except (ValueError, dw2remove.RemoveError) as ex:
        die(str(ex))
    say(dw2remove.describe(p))
    say("\nFirst take it out of your save (party and Digimon Center): the game crashes on a Digimon")
    say("that no longer exists. Everything is copied to mods\\_removed\\ first, so it can be put back.")
    if "--yes" not in args and input("Remove it? [y/N] ").strip().lower() not in ("y", "yes"):
        die("nothing changed")
    back = dw2remove.apply(p, MODS)
    say("Removed. The copy is in %s" % back)
    say("If the Blender add-on had it open, re-import: it is gone from Import Digimon now.")


def cmd_names(args):
    """Give the files in mods/ names that say what they are ("005C Agumon model.bin"), from the
    Digimon table in mods/ and game-data/. The game reads them by their first 4 characters only.
    --undo takes the labels off again."""
    mf = modfiles()
    import dw2digi
    if not os.path.isdir(MODS):
        die("no mods folder yet")
    table = dw2digi.load_table(GAME_DATA, MODS)
    if not table:
        say("(no Digimon table in game-data or mods: run  python forbs.py extract  for better names)")
    changed = 0
    for name in sorted(os.listdir(MODS)):
        fid = mf.file_id(name)
        if fid is None:
            continue
        if "--undo" in args:
            want = "%04X.bin" % fid
        else:
            if name[4:5] in (" ", "_", "-"):
                continue  # already has a label (yours or ours): keep it
            label = mf.clean_label(mf.describe(fid, table))
            if not label:
                continue
            want = "%04X %s.bin" % (fid, label)
        if want == name:
            continue
        if os.path.exists(os.path.join(MODS, want)):
            say("  kept %s (%s is there already)" % (name, want))
            continue
        os.rename(os.path.join(MODS, name), os.path.join(MODS, want))
        say("  %s -> %s" % (name, want))
        changed += 1
    for fid, names in sorted(mf.duplicates(MODS).items()):
        say("  NOTE: file %04X is in mods\\ %d times (%s); the game uses only one, so delete the others"
            % (fid, len(names), ", ".join(names)))
    say("%d file(s) renamed" % changed)


def cmd_clean(args):
    """DW2-PC/ back to exactly DW2-PC + the patches: every file Git doesn't know is listed and
    removed (your disc dump, assets, venv and dw2.pak are kept: DW2-PC's own .gitignore covers
    them). Mod files found in it go to mods/ first; old builds are cleared except dw2.pak."""
    if not os.path.isdir(os.path.join(DW2, ".git")):
        die("DW2-PC here isn't a Git clone. Delete the DW2-PC folder inside this folder and run\n"
            "  python forbs.py setup <your old DW2-PC folder>")
    n = gather_mods([os.path.join(DW2, "build", "*", "mods", "*.bin"), os.path.join(DW2, "mods", "*.bin")])
    if n:
        say("Kept %d mod file(s) from DW2-PC: they're in mods\\ now (the newest copy of each)." % n)
    if os.path.isdir(os.path.join(DW2, ".git", "rebase-apply")):
        git("am", "--abort", check=False, quiet=True)
    git("checkout", "-q", "-f", "-B", BRANCH, BASE)
    loose = [l[13:] for l in git("clean", "-nd", quiet=True).stdout.splitlines() if l.startswith("Would remove ")]
    from_patches = {f for p in series_files() for f in added_files(p)}
    from_patches |= {os.path.dirname(f) + "/" for f in from_patches}
    loose = [l for l in loose if l not in from_patches]      # the patches put these back
    old_builds = []
    bdir = os.path.join(DW2, "build")
    for d in sorted(os.listdir(bdir)) if os.path.isdir(bdir) else []:
        full = os.path.join(bdir, d)
        if os.path.isdir(full):
            for n2 in os.listdir(full):
                if not n2.lower().endswith(".pak"):
                    old_builds.append(os.path.join("build", d, n2))
    if not loose and not old_builds:
        say("Nothing to clean.")
        git("clean", "-fdq")
    else:
        say("These are not part of DW2-PC or the patches and will be deleted:")
        for l in loose:
            say("  " + l)
        if old_builds:
            say("  build\\...: %d old build files (dw2.pak is kept; the builds are made again)" % len(old_builds))
        if "--yes" not in args and input("Delete them? [y/N] ").strip().lower() not in ("y", "yes"):
            die("nothing deleted")
        git("clean", "-fdq")
        for rel in old_builds:
            p = os.path.join(DW2, rel)
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        say("  cleaned")
    if os.path.exists(APPLIED):
        os.remove(APPLIED)
    cmd_apply([])
    say("\nDone. Build again with  python forbs.py build --both")


def cmd_update(args):
    cmd_apply([])
    build(False)
    build(True)
    if not glob.glob(os.path.join(GAME_DATA, "*.bin")):
        cmd_extract([])
    cmd_addon([])
    say("\nAll up to date. If the add-on changed, install dist\\dw2_digimon_addon.zip again in Blender.")


def cmd_status(args):
    cfg = load_config()

    def n(folder, pat="*.bin"):
        return len(glob.glob(os.path.join(folder, pat)))
    say("Forbs Hidden Mods: " + ROOT)
    say("  DW2-PC     " + ("set up" if os.path.isdir(os.path.join(DW2, ".git")) else "not set up (python forbs.py setup <folder>)"))
    if os.path.isdir(DW2):
        try:
            with open(APPLIED) as f:
                ok = f.read().strip() == series_hash()
        except OSError:
            ok = False
        say("  patches    %d, %s" % (len(series_files()), "applied" if ok else "NOT applied yet (python forbs.py apply)"))
        for dev in (False, True):
            d = build_dirs(dev)[0]
            exe = os.path.join(DW2, "build", d, exe_name())
            say("  %-10s %s" % ("dev build" if dev else "release", exe if os.path.isfile(exe) else "not built"))
        say("  dw2.pak    " + (find_pak() or "not found"))
    say("  mods       %d files in %s" % (n(MODS), MODS))
    say("  game-data  %d files in %s" % (n(GAME_DATA), GAME_DATA))
    say("  add-on     " + (os.path.join(DIST, "dw2_digimon_addon.zip") if os.path.isfile(
        os.path.join(DIST, "dw2_digimon_addon.zip")) else "not made (python forbs.py addon)"))
    say("  compiler   %s\n  SDL3       %s" % (cfg.get("mingw") or "(default)", cfg.get("sdl3") or "(default)"))


def cmd_config(args):
    cfg = load_config()
    for key in ("mingw", "sdl3"):
        flag = "--" + key
        if flag in args:
            i = args.index(flag)
            if i + 1 >= len(args):
                die(flag + " needs a folder")
            cfg[key] = args[i + 1]
    save_config(cfg)
    say(json.dumps(cfg, indent=2))


COMMANDS = {"setup": cmd_setup, "apply": cmd_apply, "build": cmd_build, "play": cmd_play,
            "extract": cmd_extract, "addon": cmd_addon, "update": cmd_update, "status": cmd_status,
            "config": cmd_config, "clean": cmd_clean, "names": cmd_names, "mine": cmd_mine,
            "remove": cmd_remove}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(0 if len(sys.argv) < 2 else 1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
