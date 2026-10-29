# Installing Forbs Hidden Mods from scratch

This guide starts from nothing: no game build, no tools. At the end you have the Digimon World 2 PC
port built from its source code, with every Forbs Hidden Mods feature, plus the Blender add-on if
you want to make Digimon. It's written for Windows 10 or 11 (64-bit).

Allow about an hour the first time, most of it downloads and the first build.

> **You need your own copy of the game:** a raw dump of the **USA** disc, **SLUS-01193**, as
> `.bin` + `.cue` (or a CloneCD `.img`). A 2048-byte `.iso` won't work: it's missing the audio and
> movie sectors. Nothing in these projects contains any game data. The build reads everything it
> needs from your disc, and checks it against a list of hashes.

---

## 1. Install the tools (once)

| Tool | Where | Notes |
| --- | --- | --- |
| **Git** | <https://git-scm.com> | Default options. |
| **Python 3** (3.11 or newer) | <https://www.python.org/downloads/> | Tick **"Add python.exe to PATH"** in the installer. |
| **MinGW-w64 GCC** (x86_64) | <https://winlibs.com> | Get the **UCRT, x86_64** zip. Unzip it so that `C:\mingw64\bin\gcc.exe` exists. |
| **SDL3** (MinGW development release) | <https://github.com/libsdl-org/SDL/releases> | Get `SDL3-devel-3.x.x-mingw.zip`. Unzip it so that `C:\SDL3\x86_64-w64-mingw32` exists. |
| **mkpsxiso** (for `dumpsxiso`) | <https://github.com/Lameguy64/mkpsxiso/releases> | Get the `win64` zip and unzip it anywhere, for example `C:\mkpsxiso`. |

Other folders work for any of these; you'll just tell the build where they are in step 5.

Open a **new** PowerShell window after installing, so it picks up Git and Python. Check them with:

```
git --version
python --version
```

---

## 2. Get the DW2-PC source code

The mods are made for one version of DW2-PC (commit `1dbb32a`, "v1.0.0-beta"). Get that one:

```
cd C:\
git clone https://github.com/Wyrelade/DW2-PC.git
cd C:\DW2-PC
git checkout 1dbb32a
python -m pip install -r requirements.txt cmake
```

The last line installs the build helpers the project uses (Ninja, splat and the others) and CMake.

---

## 3. Extract your disc into the source folder

The build takes a few data tables from the game's own program, so it needs your disc's files
extracted into `dumps\disc`. Put your disc image somewhere easy, for example
`C:\Games\Digimon World 2 (USA).bin`, then:

```
cd C:\DW2-PC
C:\mkpsxiso\bin\dumpsxiso.exe -x dumps\disc -pt "C:\Games\Digimon World 2 (USA).bin"
```

Check that it worked: `C:\DW2-PC\dumps\disc\SLUS_011.93` should now exist.

(Your `dumpsxiso.exe` may be directly in the mkpsxiso folder rather than in `bin`. Use whichever path
it's at.)

---

## 4. Cut the game's program into its pieces

Still in `C:\DW2-PC`:

```
python -m splat split configs\USA\SLUS_011.93.yaml
```

This makes the `assets` folder from your disc's program. Check that
`C:\DW2-PC\assets\Ovl_LoadArea.bin` now exists.

---

## 5. Get Forbs Hidden Mods and set it up

Download the mods next to it (or download the repository as a zip from GitHub and unzip it):

```
cd C:\
git clone https://github.com/ForbHiddenGems/forbs-hidden-mods.git
cd C:\forbs-hidden-mods
```

If your MinGW and SDL3 folders aren't `C:\mingw64` and `C:\SDL3`, tell the script where they are:

```
python forbs.py config --mingw C:\path\to\mingw64 --sdl3 C:\path\to\SDL3
```

Now let it set everything up:

```
python forbs.py setup C:\DW2-PC
```

This copies your prepared `C:\DW2-PC` into `C:\forbs-hidden-mods\DW2-PC`, including your
`dumps` and `assets`, and puts every mod patch on it. Your `C:\DW2-PC` isn't changed, and once
everything works you can delete it.

---

## 6. Build the game

```
python forbs.py build --both
```

This builds two versions. The first build takes a while; later ones are much quicker.

- the **release** game (`DW2-PC\build\native64_rel\dw2.exe`), for playing
- the **dev** game (`DW2-PC\build\native64\dw2.exe`), the same plus developer tools on **F2**:
  the save and party editor you need to get new Digimon

It finishes with `Built.`. If it stops with an error, see [Problems](#problems) below.

---

## 7. First start

```
python forbs.py play
```

On the first start the game asks for your disc image. Pick the same `.bin` as in step 3. It checks
the disc file by file, writes its data pack `dw2.pak` next to `dw2.exe` (a few seconds), and starts.
After that the image isn't needed any more.

The dev game (`python forbs.py play --dev`) is a separate folder, so it asks once too. Or copy
`DW2-PC\build\native64_rel\dw2.pak` into `DW2-PC\build\native64\` yourself.

Your saves and settings are shared by both. They live in `%APPDATA%\DW2-Online\`.

---

## 8. Turn the mods on and off

Press **F1** in the game and open the **Forbs Hidden Mods** tab. Everything is there:

- **Domain camera (F4):** classic, high chase, low chase or first person; smooth turning; ceilings (F10)
- **Mystery encounters:** how often wandering Digimon show as a ?, and whether a ? can hold a rarer one
- **LvlLimitBoostr:** where the level-limit boosters can turn up
- **Battle digivolution:** the DP gauge and the Digivolve command
- **Model mods:** how many of your own model files are in use

---

## 9. Optional: the Blender add-on (making and editing Digimon)

You need [Blender](https://www.blender.org/download/) 3.6 or newer (4.x recommended). Then:

```
python forbs.py extract
python forbs.py addon
```

`extract` copies the Digimon models and the game's tables out of your `dw2.pak` into `game-data`.
`addon` makes `dist\dw2_digimon_addon.zip`.

In Blender: **Edit > Preferences > Add-ons**. Open the arrow at the top right, choose **Install from
Disk...**, pick `dist\dw2_digimon_addon.zip`, and tick it. Restart Blender. The **DW2** tab
(press **N** in the 3D view) finds your `game-data` and `mods` folders by itself.

What you export from Blender goes into `mods\`, which both game versions read. The full guide is in
[`blender-addon/dw2_digimon/README.md`](blender-addon/dw2_digimon/README.md).

---

## Everyday commands

| Command | Does |
| --- | --- |
| `python forbs.py play` / `play --dev` | starts the game |
| `python forbs.py update` | after getting a newer version of the mods: puts the patches on, rebuilds both games, remakes the add-on |
| `python forbs.py status` | shows what's set up and built |
| `python forbs.py names` | gives the files in `mods\` names that say what they are |
| `python forbs.py mine` / `remove <number>` | lists / removes Digimon you made |

To get a newer version of the mods later:

```
cd C:\forbs-hidden-mods
git pull
python forbs.py update
```

---

## Problems

| Message | Fix |
| --- | --- |
| `no gcc at ...` | Point it at your MinGW: `python forbs.py config --mingw C:\path\to\mingw64`, then build again. The folder must contain `bin\gcc.exe`. |
| `no SDL3 MinGW release at ...` | `python forbs.py config --sdl3 C:\path\to\SDL3`. The folder must contain `x86_64-w64-mingw32`. |
| `no ninja` / `cmake` not found | `python -m pip install ninja cmake`, then open a new PowerShell window. |
| `assets/Ovl_LoadArea.bin missing` | Step 4 wasn't done in the folder you gave `setup`. Run it in `forbs-hidden-mods\DW2-PC` now. |
| A missing file under `dumps/disc` | Step 3 wasn't done (or used another folder). Run `dumpsxiso` in `forbs-hidden-mods\DW2-PC` now. |
| The game rejects the disc | It must be the USA disc (SLUS-01193) as a raw `.bin`/`.cue` dump, not a 2048-byte `.iso`. |
| `a patch didn't apply` | The DW2-PC copy wasn't at `1dbb32a` or has your own changes. `python forbs.py apply` resets it and tries again. |

Settings window, controls and everything else about the port itself: see the
[DW2-PC README](https://github.com/Wyrelade/DW2-PC).
