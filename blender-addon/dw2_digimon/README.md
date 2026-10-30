# Digimon World 2 models: Blender add-on

Import any Digimon from your own game files into Blender with its skeleton, texture and every
animation. Edit it or model your own Digimon over its skeleton, then export it into the PC
port's `mods` folder. The game then uses your version in place of that Digimon.

Blender 3.6 or newer (4.x recommended).

## Setup (once)

**With forbs.py** (Forbs Hidden Mods): run `python forbs.py addon` and install
`dist\dw2_digimon_addon.zip`. It already knows your `game-data` and `mods` folders, so leave
both folder boxes empty and skip steps 2 and 3. **Use forbs-hidden-mods folders** empties the
boxes in an older `.blend`.

**Without it:**


1. Install: in Blender, **Edit > Preferences > Add-ons**. In Blender 4.2 or newer, open the
   arrow at the top right and pick **Install from Disk...**; in older versions, click
   **Install...**. Choose `dw2_digimon_addon.zip` and tick **Digimon World 2 models** to turn it on.
2. Unzip `dw2_models.zip`, the file `dw2_extract_models.py` made from your `dw2.pak`, into a
   folder of its own.
3. In the 3D view, press **N** and open the **DW2** tab:
   - **Data folder**: the folder you unzipped `dw2_models.zip` into.
   - **Game mods folder**: a folder called `mods` next to `dw2.exe`. Create it if it isn't
     there yet.

   Both folders, **Import Digimon** and **Export** sit at the top. Below them are three sections
   (**Selected Digimon**; **Name, stats and digivolution**; **Take parts from another Digimon**).
   Click a section's arrow to fold it away, or scroll the sidebar with the mouse wheel.

## Import

Click **Import Digimon** and type part of a name, for example `agu`. You get:

- **An armature (skeleton)** with one bone per body part. The game moves each part rigidly
  with its bone; nothing bends. Bones are named with a best guess at the part: `head_01`,
  `wing_L_12`, `thigh_R_17` and so on (L and R are the Digimon's own left and right). The game's
  files have no names, so these come from each part's shape and position. They're right for most
  Digimon, but unusual shapes can get odd names. The number is always the game's bone number,
  and `part_NN` means it couldn't tell.
- **A mesh** whose vertices each belong to exactly one bone, through vertex groups named
  after the bones.
- **The texture**, a 128 x 256 image.
- **One material per 16-colour palette.** All of them use the same texture image.
- **Every animation** as an action named `<Name>_animNNN`. `NNN` is the game's animation
  number: 0-9 sit in slot 0, 10-19 in slot 1, and so on. Pick an action in the DW2 tab, or in
  the Action Editor, and press play. The scene is set to 30 fps, which is the game's speed:
  one game frame is one Blender frame.

Switch the viewport to **Material Preview** to see the texture.

## Digimon properties and new Digimon

The DW2 tab shows the selected Digimon's **number**, **name** and base data: **type**, **rank**,
**specialty**, **growth per level** for HP, MP, Attack, Defense and Speed (0 to 15), its own
**technique**, its **DNA group**, and **digivolves into**. For the technique and the digivolutions,
click the button with the magnifying glass and type part of a name to search the list. Digivolution is by DP: up to four
Digimon, each from a DP value. With one, it always becomes that one; with more, the last one
whose "from" its DP has reached. These need the game's tables in the data folder, so unzip
`dw2_data.zip` (made by `dw2_extract_models.py --data`) into the same folder as `dw2_models.zip`
(or a folder inside it). The technique list comes from `025B.bin` in it; without that file the
panel keeps each Digimon's technique as it is and says so.

- **Export to mods folder** saves the name and these values too, when you changed them.
- **Save as new Digimon** turns what you have into a brand-new Digimon: pick a name and a free
  number (1 to 255; the box lists free ones). It gets its own model and animation files (numbered
  1000 + number x 16 in hex, e.g. `1AA0.bin` for number 170), its own table entry and base data;
  the Digimon you started from is left as it is. After that, this skeleton *is* the new Digimon:
  Export updates it. Using a number you gave one of your own Digimon before replaces that one;
  the game's own numbers are protected.
- New Digimon need the game patch that allows new file numbers (`dw2-new-digimon-files.patch`).
  Get one in the dev build: **F2 > Save > Edit > Party > Add Digimon**, then collect it at the
  Digimon Center.
- The add-on reads the mods folder too, so your new Digimon appear in **Import Digimon** and in
  the digivolution lists.

## What you can change

**Texture**: paint it in Texture Paint mode. Each material is one palette of 16 colours, so the
faces of one material can use 16 colours between them. More colours get reduced on export.
More materials give you more palettes.

**Mesh**: move, add or delete faces, or hide the original mesh and model your own:

- Parent the new mesh to the armature and give it an **Armature** modifier.
- Give every vertex to **one** bone (a vertex group named after the bone, weight 1). The
  game has no blending between bones; the bone with the highest weight wins.
- UV-map it onto **one** texture image (any size; it is scaled to 128 x 256).
- Keep each bone's part to **256 vertices** or fewer. **Check limits** in the DW2 tab
  counts them.
- Triangles and quads only. Bigger faces are split into triangles on export.

**Animations**: edit the keys of any action. Keys can be anywhere: export samples every
frame from the first key to the last. **Loop to** sets the frame the animation loops back to
(0 = the start). -1 means it plays once and holds the last frame. Keep the action names'
numbers and their custom properties; they tell the game which animation is which.

### What each animation is for

The number is the `NNN` in the action's name. Numbers come in groups of ten, one animation file
per group (0-9, 10-19, ... 100), which is why Export writes several animation files.

**Battle** (the ones that matter most):

| Number | When it plays |
| --- | --- |
| **0** | Standing idle. Also the Status screen, the Digidex and other menus |
| **10** | Taking a hit without being knocked back (a flinch) |
| **20** | Knocked back: first hop (optional: skipped when the Digimon has none) |
| **21** | Knocked back: second hop (optional, as 20) |
| **22** | Knocked back: landing (always played) |
| **50** | Using a technique, first style |
| **60** | Using a technique, second style |
| **70** | Using a technique, third style |
| **80** | Victory pose after a won battle |
| **90** | Getting back up after a knock-back, before idle |
| **100** | Fainted, lying down (also a fainted Digimon at the start of a battle) |

Each technique is set to use one of the three technique styles, and a Digimon can learn many
techniques, so give all three a proper animation. A knock-back plays 20, 21 and 22, then 90 and
back to 0, or 100 if the hit knocked it out.

**Domains:**

| Number | When it plays |
| --- | --- |
| **40** | Standing on the domain map (a wandering enemy) |
| **41** | Walking on the domain map |
| **42-45** | Used by some other domain objects; not confirmed for Digimon |

**30-37** are used by the city's walking characters, most likely the people rather than
Digimon.

Most important: 0, 10, 22, 50, 60, 70 and 100 (nearly every battle uses them). Then 80 and 90,
then 40 and 41 if the Digimon wanders in a domain. Don't delete any: a deleted one is exported as a
still pose, so the Digimon just freezes at that moment.

**Checking them in the game:** export, add the Digimon in the dev build (**F2 > Save > Edit >
Party > Add Digimon**), and battle with it. Let an enemy hit it hard to see the knock-back and
faint animations; **Fill DP** (F2 > Save) lets you check the battle digivolution too.

**Skeleton**: you can move bones (in Edit Mode), and add or remove them. The game allows 8
levels of parent and child, and 64 bones.

## Take parts from another Digimon

For example, Angemon's wings on Agumon:

1. **Import both** Digimon.
2. **Pick the parts on the donor.** Select Angemon's armature, switch to **Pose Mode**
   (Ctrl+Tab) and click the bones of the parts, Shift-clicking for more. Any bones below the
   ones you pick come too. Alternatively, in Edit Mode on Angemon's mesh, hover over a part and
   press **L** to select its faces. The DW2 tab shows how many bones are selected. Tick
   **Preview selected parts (orange)** to see them: the faces of the selected bones light up
   in orange, in front of everything, and update as you click.
3. In the DW2 tab under **Take parts from another Digimon**:
   - **Add to**: the Digimon that gets the parts (Agumon).
   - **Attach to**: its bone the parts hang from. Leave it empty for its chest (or body).
   - **Motion**: **Copy their motion** loops the parts' movement from the donor's current
     animation through every animation of the target, so the wings flap. **Keep still**
     lets you pose them yourself.
4. Click **Add selected parts**.

The parts arrive as their own mesh object (for example `Agumon_Angemon_parts`) with their own
bones under the attach bone. They sit where they were on the donor, relative to its body,
scaled to the target's size. Their pixels are copied into free space in the target's texture,
with their own palettes.

**To place them**, select the parts object in Object Mode and move, turn or scale it (G, R, S)
until it looks right. Then click **Apply placement** in the DW2 tab. This moves their bones to
match, so they still flap around the right spot. Repeat as often as you like, then export as usual.

If the target's texture has no room left, it tells you; pick fewer parts.

## Export

Select the Digimon (its armature or mesh) and click **Export to mods folder**. This writes its
model file and all of its animation files, named by game file number with a label saying what
they are (for example `005C Agumon model.bin` and `0001 Agumon animations 0.bin`). Only the
number counts to the game, so you can rename the label part freely; Export writes into the
file that's there already for a number, keeping your name. Start the game and that Digimon is yours everywhere it appears. The text
**DW2 export report** in Blender's Text Editor lists the files and any notes.

To undo, delete those files from `mods`, or rename the folder. Your `dw2.pak` is never touched.

## Good to know

- **Imported twice?** If the same Digimon is in the scene more than once (`Angemon` and
  `Angemon.001`), the DW2 tab shows a red warning. Delete the copies you aren't using:
  buttons act on the one that's selected, which may not be the one you think.

- **Eye blink**: it copies little patches of the original texture. It stays as long as you
  don't paint over those patches (added parts are always put elsewhere). It is turned off
  when you give the Digimon a whole new texture layout.
- **Animations you delete**: they are written as a still rest pose, so the game's animation
  numbers stay valid.
- **Shared files**: a few Digimon share a model file. Changing one changes all of them.
- **Save the .blend**: the texture is packed into it. If Blender says it can't pack an image,
  use **Image > Pack** in the Image Editor.
