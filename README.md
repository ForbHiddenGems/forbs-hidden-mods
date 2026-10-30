# Forbs Hidden Mods

Mods for **Digimon World 2** on the [DW2-PC](https://github.com/Wyrelade/DW2-PC) native PC port,
plus a Blender add-on and tools for making and editing Digimon.

This repository contains **no game files**. To use any of it you need your own copy of the game and
a DW2-PC build made from it.

## What you need

These mods are changes to another project's source code, so you need three things. None of them are in
this repository:

| | Where to get it |
| --- | --- |
| **The DW2-PC source code**, at version `1dbb32a` (v1.0.0-beta) | **<https://github.com/Wyrelade/DW2-PC>**: the Digimon World 2 PC port, built from the [Digimon World 2 decompilation](https://github.com/Wyrelade/Digimon-World-2-Decomp). Public domain (CC0). `git clone https://github.com/Wyrelade/DW2-PC.git`, then `git checkout 1dbb32a`. |
| **Your own Digimon World 2 disc** | USA, **SLUS-01193**, dumped as a raw `.bin` + `.cue`. The build takes the game's data from it; no game data is shared anywhere. |
| **Build tools** | Git, Python 3, MinGW-w64 GCC, SDL3 and mkpsxiso: links in [INSTALL.md](INSTALL.md). |

**[INSTALL.md](INSTALL.md) walks through all of it, step by step**, from a fresh Windows PC to the
game with the mods.

## Everything from this folder: `forbs.py`

One script runs the lot, and everything lives in this one folder:

```
forbs-hidden-mods\
  forbs.py                        the one script
  patches\  tools\  blender-addon\  the mods (what's on GitHub)
  DW2-PC\       game source and your builds   (made by setup; never uploaded)
  game-data\    every file from your dw2.pak (for Blender and tools; never uploaded)
  mods\         your Digimon: every build AND the Blender add-on use this one folder
  dist\         the Blender add-on zip to install
```

**Once:** point setup at the DW2-PC folder you already build from. It copies it in (your old
folder isn't touched) and puts all the patches on. It also gathers any mods from your old builds
into `mods\`.

```
python forbs.py setup C:\path\to\your\DW2-PC
python forbs.py config --mingw C:\mingw64 --sdl3 C:\SDL3     (only if yours are elsewhere)
python forbs.py build --both
python forbs.py extract
python forbs.py addon
```

Then install `dist\dw2_digimon_addon.zip` in Blender. It finds `game-data` and `mods` by itself.

**Every day:**

| Command | Does |
| --- | --- |
| `python forbs.py play` / `play --dev` | starts the release or dev game |
| `python forbs.py update` | after new or changed patches: applies them, builds both games, remakes the add-on |
| `python forbs.py status` | shows what's set up, built and where |
| `python forbs.py names` | gives the files in `mods\` names that say what they are: `005C.bin` becomes `005C Agumon model.bin` (`--undo` takes the labels off) |
| `python forbs.py mine` | lists the Digimon you made (their numbers) |
| `python forbs.py remove <number>` | removes one you made, cleanly: its table entry, stats, any digivolution into it and its own files, all copied to `mods\_removed\` first. Take it out of your save first. |
| `python forbs.py clean` | tidies `DW2-PC\`: moves any mod files into `mods\`, lists and deletes everything that isn't DW2-PC or the patches, then reapplies the patches |
| `python forbs.py build [--dev \| --both]` | builds only |

Every build gets a `mods-folder.txt` next to `dw2.exe` that points at `mods\`. The game reads that
folder first, so you never copy mod files between builds again.

`DW2-PC\` is managed by the script. `apply` and `update` reset its source to DW2-PC commit `1dbb32a`
and put `patches\series` on top. Any change you make directly in `DW2-PC\` is undone, so changes
belong in patches.

## What's in the repository

| Folder | What it is |
| --- | --- |
| `patches/dw2-forbs-hidden-mods.patch` | Every game change in one patch |
| `patches/series/` | The same changes as separate patches, one per feature step, in order (what `forbs.py` applies) |
| `blender-addon/dw2_digimon/` | Blender add-on: import, edit and export Digimon; take parts from other Digimon; create new Digimon |
| `tools/` | Command-line Python tools |

### Game changes (all on the F1 menu's **Forbs Hidden Mods** tab)

- **Domain camera views (F4):** classic, high chase, low chase and first person from inside the
  Digi-Beetle. Includes smooth turning, ceilings drawn with the floor texture (toggled with F10), and a
  facing arrow on the minimap.
- **Mystery encounters:** wandering Digimon appear as a floating **?** until the battle starts. Can be
  set so a ? holds one of the floor's rarer enemy groups.
- **LvlLimitBoostr:** a rare find that raises a party Digimon's level limit by 1. Has 1% chances from
  chests and from ? encounters, each with its own toggle.
- **Battle digivolution:** each of your Digimon gets a DP row under its HP and MP, which fills by dealing
  and taking damage. When it's full, it gets a **Digivolve** command and fights one level up: the
  Digi-Lab's digivolution plays on the battlefield and it becomes the form its digivolution table
  names at its DP, with that form's technique and +30% HP, MP, attack, defense and speed, for 3
  turns before changing back. Your tamer rank unlocks each step: Rookie to Champion at any rank,
  Champion to Ultimate from rank 5 (Pro), Ultimate to Mega from rank 8 (Commander). Your save is
  never changed.
- **Digidex:** a new entry in the game's menu. Every Digimon, with its model turning, its level,
  type and technique, what it digivolves from and what it becomes at which DP. Ones you haven't
  met are black silhouettes named "?????". Fighting against one shows it; having it in your party
  or bank (or digivolving into it in battle) makes it owned and shows its technique too. It's
  kept inside your save.
- **Model mods:** the game reads replacement files from a `mods` folder next to `dw2.exe` (or in
  `%APPDATA%\DW2-Online\mods`, or the folder named in `mods-folder.txt` next to the exe), named by
  game file number (`005C.bin`). A label may follow the number after a space, `_` or `-`
  (`005C Agumon model.bin`); only the first 4 characters count. Files numbered 0xE5B and
  above are new files, which is how new Digimon get their own model and animations.
- The dev build's F2 overlay reads tables from `mods` too, so new Digimon and items show up there.
- **Testing tools (dev build, F2 > Save, Edit on):** pick the tamer rank by title, and **Fill DP**
  fills the DP gauge of every party Digimon that can digivolve, in battle; **Digidex: show all** shows every
  Digimon in the Digidex without changing your save.

All changes sit under `#ifdef DW2_NATIVE`. The PS1 build is unchanged.

## Applying the patch by hand (without forbs.py)

The patch is made against DW2-PC commit `1dbb32a` ("v1.0.0-beta: English and Spanish").

```
git clone https://github.com/Wyrelade/DW2-PC.git
cd DW2-PC
git checkout 1dbb32a
git apply path\to\patches\dw2-forbs-hidden-mods.patch
```

To keep the history step by step instead, use `git am path\to\patches\series\*.patch`.

Then build as usual. For a release build: `python tools/build_native.py --arch x64 --release`. Leave
off `--release` for the dev build with the F2 overlay.

## Blender add-on

Needs Blender 3.6 or newer (4.x recommended). Zip the `blender-addon/dw2_digimon` folder, or use
the zip from Releases, then install it in Blender through **Edit > Preferences > Add-ons**. Full
instructions are in [`blender-addon/dw2_digimon/README.md`](blender-addon/dw2_digimon/README.md).

## Tools

Python 3. `dw2render.py` also needs `numpy` and `Pillow`.

| Script | Use |
| --- | --- |
| `dw2_extract_models.py` | Copies the Digimon models and animations out of your own `dw2.pak` into `dw2_models.zip`. With `--data`, copies the Digimon, technique, item and encounter tables into `dw2_data.zip`. With `--all`, every data file in the pak (what `forbs.py extract` uses). Only reads the pak. |
| `dw2newdigi.py` | Adds a new Digimon as a copy of an existing one under its own number and name, written as replacement table files for `mods`. |
| `dw2render.py` | Software preview: draws a model posed by an animation into a GIF. |
| `dw2model.py`, `dw2digi.py` | Readers and writers for the model, animation and Digimon table formats, used by the scripts above. |

## Licence

The code in this repository (the patches' changes, `forbs.py`, `tools/` and `blender-addon/`) is
licensed under the **[PolyForm Noncommercial License 1.0.0](LICENSE.md)**.

In plain words (the licence text is what counts):

- **You can** download it, build it, play with it, change it for yourself, and share it, for any
  noncommercial purpose: personal use, hobby projects, study, research.
- **You can't** sell it or use it for commercial purposes without permission from the author.
- **If you pass it on** (changed or not), include the licence (or its link) and the
  `Required Notice` line at the top of [LICENSE.md](LICENSE.md).

The patches change the [DW2-PC](https://github.com/Wyrelade/DW2-PC) source code, which is public
domain (CC0); the DW2-PC code itself stays under CC0, this licence covers only the work added here.

Digimon and Digimon World 2 belong to their owners. This project includes none of their data.
