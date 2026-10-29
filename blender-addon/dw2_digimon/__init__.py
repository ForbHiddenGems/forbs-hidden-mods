"""Digimon World 2 (DW2-PC) model add-on: import a Digimon with its skeleton, texture and every
animation; change it or model your own over its skeleton; export it into the game's mods folder.

Sidebar (N) > DW2 in the 3D view.
"""

bl_info = {
    "name": "Digimon World 2 models (DW2-PC)",
    "author": "DW2-PC mod",
    "version": (0, 6, 0),
    "blender": (3, 6, 0),
    "location": "3D View > Sidebar > DW2",
    "description": "Import and export Digimon World 2 Digimon models and animations",
    "category": "Import-Export",
}

import json
import os
import sys
import uuid

import bpy

# After an update without a Blender restart, Python still holds the old version's helper modules:
# drop them so the ones in this folder load (a stale dw2digi broke v0.4.0's Digimon list).
for _m in [m for m in list(sys.modules) if m.startswith(__name__ + ".")]:
    del sys.modules[_m]
from mathutils import Matrix, Quaternion, Vector

from . import dw2core, dw2digi, dw2model, dw2modfiles, dw2names, dw2parts, dw2tables

FPS = 30


# ---------------------------------------------------------------- helpers

def forbs_paths():
    """forbs_paths.json, put in the add-on by forbs.py: the forbs-hidden-mods folder's game-data
    and mods folders, used whenever the panel's folder boxes are empty."""
    try:
        import json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "forbs_paths.json")) as f:
            j = json.load(f)
        return {"data": j.get("data", ""), "mods": j.get("mods", "")}
    except Exception:
        return {"data": "", "mods": ""}


def data_dir(context):
    p = context.scene.dw2_data_dir
    return bpy.path.abspath(p) if p else forbs_paths()["data"]


def mods_dir(context):
    p = context.scene.dw2_mods_dir
    return bpy.path.abspath(p) if p else forbs_paths()["mods"]


def source(context):
    """Game files as the PC port reads them: the mods folder first, then the data folder."""
    return dw2tables.Source(data_dir(context), mods_dir(context))


_table_cache = {"key": None, "items": [], "table": []}


def load_table(folder, mods=""):
    key = (folder, mods)
    if _table_cache["key"] != key:
        table = dw2digi.load_table(folder, mods or None) if os.path.isdir(folder) else []
        items = []
        src = dw2tables.Source(folder, mods or None)
        for e in table:
            if e["model"] <= 0 or src.path(e["model"]) is None:
                continue
            label = e["name"] or "Digimon #%d" % e["id"]
            items.append((str(e["id"]), label, "number %d, model file %04X" % (e["id"], e["model"])))
        _table_cache.update(key=key, items=items, table=table)
    return _table_cache["table"]


def forget_tables():
    _table_cache["key"] = None
    _choice_cache["key"] = None


def digimon_items(self, context):
    load_table(data_dir(context), mods_dir(context))
    # Blender needs the list kept alive while the menu is open
    return _table_cache["items"] or [("0", "(set the data folder first)", "")]


# ---------------------------------------------------------------- Digimon properties (base data)

_choice_cache = {"key": None}
_old_lists = []     # every list handed to Blender stays alive: it keeps pointers to the strings


def choices(context):
    """Names for the property menus (types, ranks, specialties, techniques, Digimon)."""
    src = source(context)
    key = (data_dir(context), mods_dir(context), src.path(dw2tables.WAZADATA), src.path(dw2tables.SYSTEXT))
    if _choice_cache["key"] != key:
        _old_lists.append(dict(_choice_cache))
        lab = dw2tables.labels(src)
        # the record holds one byte; the end of the table is unused 'abc' fillers
        techs = [(i, n) for i, n in dw2tables.techniques(src) if 0 < i < 256 and n and n != "abc"]
        table = load_table(*key[:2])
        base = src.get(dw2tables.DIGIMNDT)
        with_base = set(i for _, i in dw2tables.base_records(base)[0]) if base else set()
        digis = [(str(e["id"]), "%s (%d)" % (e["name"] or "#", e["id"]), "")
                 for e in sorted(table, key=lambda e: e["name"]) if 0 < e["id"] < 256 and e["id"] in with_base]
        _choice_cache.update(
            key=key,
            type=[(str(i), n, "") for i, n in enumerate(lab["type"])],
            rank=[(str(i), n, "") for i, n in enumerate(lab["rank"])],
            specialty=[(str(i), n, "") for i, n in enumerate(lab["specialty"])],
            have_techs=bool(techs),
            tech=[("0", "(none)", "")] + [(str(i), "%s (%d)" % (n, i), "") for i, n in techs],
            digi=[("0", "(none)", "")] + digis,
            tech_names=dict(techs),
            digi_names=dict((e["id"], e["name"] or "#%d" % e["id"]) for e in table))
    return _choice_cache


_EMPTY = [("0", "-", "")]


def _items(kind):
    def f(self, context):
        try:
            return choices(context or bpy.context).get(kind) or _EMPTY
        except Exception:
            return _EMPTY
    return f


class DW2DigiProps(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name", maxlen=13, description="Up to 13 letters")
    dtype: bpy.props.EnumProperty(name="Type", items=_items("type"))
    rank: bpy.props.EnumProperty(name="Rank", items=_items("rank"))
    specialty: bpy.props.EnumProperty(name="Specialty", items=_items("specialty"))
    growth: bpy.props.IntVectorProperty(name="Growth", size=5, min=0, max=15,
                                        description="Growth class per level: HP, MP, Attack, Defense, Speed")
    technique: bpy.props.EnumProperty(name="Technique", items=_items("tech"),
                                      description="The technique it learns itself")
    dna: bpy.props.IntProperty(name="DNA group", min=0, max=8,
                               description="Its group when DNA-digivolving at the Digi-Lab (0..8)")
    evo0: bpy.props.EnumProperty(name="Digivolves into", items=_items("digi"))
    evo1: bpy.props.EnumProperty(name="or", items=_items("digi"))
    evo2: bpy.props.EnumProperty(name="or", items=_items("digi"))
    evo3: bpy.props.EnumProperty(name="or", items=_items("digi"))
    # picked with a search box (dw2.pick); -1 = as the Digimon has it (its base data)
    technique_id: bpy.props.IntProperty(name="Technique", default=-1)
    evo0_id: bpy.props.IntProperty(default=-1)
    evo1_id: bpy.props.IntProperty(default=-1)
    evo2_id: bpy.props.IntProperty(default=-1)
    evo3_id: bpy.props.IntProperty(default=-1)
    evo0_dp: bpy.props.IntProperty(name="from DP", min=0, max=255)
    evo1_dp: bpy.props.IntProperty(name="from DP", min=0, max=255)
    evo2_dp: bpy.props.IntProperty(name="from DP", min=0, max=255)
    evo3_dp: bpy.props.IntProperty(name="from DP", min=0, max=255)


def _set_enum(p, attr, value):
    try:
        setattr(p, attr, str(value))
    except (TypeError, ValueError):
        pass


def fill_props(arm, src, digi_id, name):
    """The Digimon's name and base data into its properties panel."""
    p = arm.dw2
    p.name = (name or "")[:13]
    d = src.get(dw2tables.DIGIMNDT)
    rec = None
    if d:
        for o, i in dw2tables.base_records(d)[0]:
            if i == digi_id:
                rec = d[o:o + dw2tables.BASE_REC]
    if rec is None:
        arm["dw2_base_raw"] = ""
        return False
    b = dw2tables.parse_base(rec)
    arm["dw2_base_raw"] = rec.hex()
    _set_enum(p, "dtype", b["type"])
    _set_enum(p, "rank", b["rank"])
    _set_enum(p, "specialty", b["specialty"])
    p.growth = b["growth"]
    p.technique_id = b["technique"]
    p.dna = b["dna"]
    for i in range(4):
        t, dp = b["evos"][i] if i < len(b["evos"]) else (0, 0)
        setattr(p, "evo%d_id" % i, t)
        setattr(p, "evo%d_dp" % i, dp)
    return True


def get_technique(arm):
    p = arm.dw2
    if p.technique_id >= 0:
        return p.technique_id
    raw = bytes.fromhex(arm.get("dw2_base_raw", "") or "")
    return raw[2] if len(raw) > 2 else 0


def get_evo(arm, i):
    """Digivolution target i: picked, or (blends from v0.4.3 and older) the old menu's value."""
    p = arm.dw2
    v = getattr(p, "evo%d_id" % i)
    if v >= 0:
        return v
    try:
        return int(getattr(p, "evo%d" % i) or 0)
    except (TypeError, ValueError):
        return 0


def props_base(arm, digi_id, context=None):
    """The properties panel as a base data record for number digi_id."""
    p = arm.dw2
    raw = bytes.fromhex(arm.get("dw2_base_raw", "") or "") or b"\0" * dw2tables.BASE_REC
    b = dw2tables.parse_base(raw)
    b.update(id=digi_id, type=int(p.dtype or 0), rank=int(p.rank or 0), specialty=int(p.specialty or 0),
             growth=list(p.growth), dna=int(p.dna),
             technique=get_technique(arm),
             evos=[(get_evo(arm, i), int(getattr(p, "evo%d_dp" % i))) for i in range(4)])
    return dw2tables.build_base(b)


def write_tables(context, arm, out, digi_id, report, entry_template=None, model=None, anims=None):
    """Write the Digimon's table entry (name, files) and base data into the mods folder when
    they differ from what the game reads now. -> [file numbers written]"""
    src = dw2tables.Source(data_dir(context), out)
    written = []
    p = arm.dw2
    tf = dw2tables.data_file_for(digi_id)
    table = src.get(tf)
    cur = dw2tables.get_entry(src, digi_id)
    name_now = None
    if cur is not None:
        no = int.from_bytes(cur[0:4], "little")
        name_now = dw2digi.glyphs(table, no)
    want_name = p.name.strip() or name_now or "Digimon"
    glyphs = dw2tables.encode_name(want_name)
    if cur is None or want_name != name_now or model is not None:
        template = cur if cur is not None else entry_template
        if template is None:
            raise dw2core.ExportError("no table entry to start number %d from" % digi_id)
        table = dw2tables.upsert_entry(table, digi_id, template,
                                       glyphs if (cur is None or want_name != name_now) else None, model, anims)
        dw2modfiles.write(out, tf, table, dw2modfiles.FIXED.get(tf))
        written.append(tf)
        if cur is not None and want_name != name_now:
            report.append("name: %s -> %s" % (name_now, want_name))
    base = src.get(dw2tables.DIGIMNDT)
    rec = props_base(arm, digi_id, context)
    old = None
    if base:
        for o, i in dw2tables.base_records(base)[0]:
            if i == digi_id:
                old = base[o:o + dw2tables.BASE_REC]
    if base and (old is None or old != rec):
        base = dw2tables.upsert_base(base, rec)
        dw2modfiles.write(out, dw2tables.DIGIMNDT, base, dw2modfiles.FIXED.get(dw2tables.DIGIMNDT))
        written.append(dw2tables.DIGIMNDT)
        if old is not None:
            report.append("base data (type, rank, growth, technique, digivolutions) updated")
    elif not base:
        report.append("no base data file (0C6C.bin) in the data folder: stats not written "
                      "(unzip dw2_data.zip into the data folder too)")
    arm["dw2_base_raw"] = rec.hex()
    forget_tables()
    return written


def find_armature(context):
    ob = context.active_object
    if ob is None:
        return None
    if ob.type == "ARMATURE":
        return ob
    if ob.parent is not None and ob.parent.type == "ARMATURE":
        return ob.parent
    for m in getattr(ob, "modifiers", []):
        if m.type == "ARMATURE" and m.object is not None:
            return m.object
    return None


def fcurve_list(action, obj):
    """Where an action's F-curves live: the action itself before Blender 4.4, a channel bag
    for the object's slot from 4.4 (layered actions)."""
    if bpy.app.version >= (4, 4, 0) and hasattr(action, "slots"):
        slot = action.slots[0] if len(action.slots) else action.slots.new(id_type="OBJECT", name=obj.name)
        try:
            from bpy_extras import anim_utils
            return anim_utils.action_ensure_channelbag_for_slot(action, slot).fcurves, slot
        except (ImportError, AttributeError):
            layer = action.layers[0] if len(action.layers) else action.layers.new("Layer")
            strip = layer.strips[0] if len(layer.strips) else layer.strips.new(type="KEYFRAME")
            return strip.channelbag(slot, ensure=True).fcurves, slot
    return action.fcurves, None


def key_range(action, obj):
    """First and last keyframe of an action (whole frames): the frames the game gets, one per
    1/30 s."""
    lo, hi = None, None
    fcurves, _slot = fcurve_list(action, obj)
    for fc in fcurves:
        for kp in fc.keyframe_points:
            f = int(round(kp.co[0]))
            lo = f if lo is None else min(lo, f)
            hi = f if hi is None else max(hi, f)
    if lo is None:
        return 1, 1
    return lo, hi


def assign_action(obj, action):
    ad = obj.animation_data or obj.animation_data_create()
    ad.action = action
    if action is not None and hasattr(ad, "action_slot") and hasattr(action, "slots") and len(action.slots):
        try:
            ad.action_slot = action.slots[0]
        except (TypeError, RuntimeError):
            pass


def make_material(name, image, clut):
    mat = bpy.data.materials.new(name)
    mat["dw2_clut"] = clut
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.interpolation = "Closest"
    tex.location = (-400, 200)
    if bsdf is not None:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        for key in ("Specular IOR Level", "Specular"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = 0.0
    if hasattr(mat, "blend_method"):
        try:
            mat.blend_method = "CLIP"
        except TypeError:
            pass
    if hasattr(mat, "surface_render_method"):
        try:
            mat.surface_render_method = "DITHERED"
        except TypeError:
            pass
    return mat


def material_image(mat):
    if mat is None or not mat.use_nodes:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image is not None:
            return n.image
    return None


# ---------------------------------------------------------------- import

def build_scene(context, scene, name, entry):
    coll = context.collection
    # armature
    arm = bpy.data.armatures.new(name)
    arm_obj = bpy.data.objects.new(name, arm)
    coll.objects.link(arm_obj)
    arm.display_type = "STICK"
    arm_obj.show_in_front = True
    for o in context.selected_objects:
        o.select_set(False)
    context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    ebs = []
    for b in scene["bones"]:
        eb = arm.edit_bones.new(b["name"])
        eb.head = (0.0, 0.0, 0.0)
        eb.tail = (0.0, 0.1, 0.0)
        eb.matrix = Matrix(b["rest"])
        eb.length = b["length"]
        eb.use_connect = False
        ebs.append(eb)
    for eb, b in zip(ebs, scene["bones"]):
        if b["parent"] >= 0:
            eb.parent = ebs[b["parent"]]
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in arm_obj.pose.bones:
        pb.rotation_mode = "QUATERNION"
    # texture
    w, h, rgba = scene["image"]
    img = bpy.data.images.new(name + "_texture", w, h, alpha=True)
    flat = [0.0] * (w * h * 4)
    for y in range(h):
        src = (h - 1 - y) * w * 4          # Blender stores the bottom row first
        dst = y * w * 4
        for i in range(w * 4):
            flat[dst + i] = rgba[src + i] / 255.0
    img.pixels.foreach_set(flat)
    try:
        img.pack()
    except RuntimeError:
        pass
    img.use_fake_user = True
    # mesh
    me = bpy.data.meshes.new(name + "_mesh")
    me.from_pydata(scene["verts"], [], [p["verts"] for p in scene["polys"]])
    uv = me.uv_layers.new(name="UVMap")
    flat_uv = [c for p in scene["polys"] for xy in p["uvs"] for c in xy]
    uv.data.foreach_set("uv", flat_uv)
    for clut in scene["materials"]:
        me.materials.append(make_material("%s_pal_%04X" % (name, clut), img, clut))
    me.polygons.foreach_set("material_index", [p["material"] for p in scene["polys"]])
    for key in ("semi", "tpage"):
        at = me.attributes.new("dw2_" + key, "INT", "FACE")
        at.data.foreach_set("value", [int(p[key]) for p in scene["polys"]])
    me.update()
    try:
        if hasattr(me, "use_auto_smooth"):
            me.use_auto_smooth = True
        me.normals_split_custom_set([n for p in scene["polys"] for n in p["normals"]])
    except (RuntimeError, AttributeError, TypeError):
        pass
    me_obj = bpy.data.objects.new(name + "_mesh", me)
    coll.objects.link(me_obj)
    me_obj.parent = arm_obj
    mod = me_obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_obj
    groups = [me_obj.vertex_groups.new(name=b["name"]) for b in scene["bones"]]
    per_bone = {}
    for vi, bi in enumerate(scene["vbone"]):
        per_bone.setdefault(bi, []).append(vi)
    for bi, vis in per_bone.items():
        groups[bi].add(vis, 1.0, "REPLACE")
    # actions
    uid = uuid.uuid4().hex
    arm_obj["dw2_uid"] = uid
    first = None
    for a in scene["actions"]:
        act = bpy.data.actions.new(a["name"])
        act.use_fake_user = True
        act["dw2_owner"] = uid
        act["dw2_slot"] = a["slot"]
        act["dw2_index"] = a["index"]
        act["dw2_loop_to"] = a["loop_to"]
        fcurves, _slot = fcurve_list(act, arm_obj)
        n = len(a["frames"])
        for bi, b in enumerate(scene["bones"]):
            locs, rots, scls = [], [], []
            prev = None
            for basis in a["frames"]:
                loc, rot, scl = Matrix(basis[bi]).decompose()
                if prev is not None and prev.dot(rot) < 0:
                    rot = -rot
                prev = rot
                locs.append(loc)
                rots.append(rot)
                scls.append(scl)
            path = 'pose.bones["%s"].' % b["name"]
            for prop, vals, size in (("location", locs, 3), ("rotation_quaternion", rots, 4),
                                     ("scale", scls, 3)):
                for k in range(size):
                    try:
                        fc = fcurves.new(path + prop, index=k, action_group=b["name"])
                    except TypeError:       # channel bags (4.4+) take no group here
                        fc = fcurves.new(path + prop, index=k)
                    fc.keyframe_points.add(n)
                    co = []
                    for f in range(n):
                        co += [float(f + 1), float(vals[f][k])]
                    fc.keyframe_points.foreach_set("co", co)
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"
                    fc.update()
        if first is None:
            first = act
    assign_action(arm_obj, first)
    context.scene.render.fps = FPS
    context.scene.frame_start = 1
    if first is not None:
        context.scene.frame_end = max(2, key_range(first, arm_obj)[1])
    meta = dict(scene["meta"])
    arm_obj["dw2_meta"] = json.dumps(meta)
    arm_obj["dw2_model"] = entry["model"]
    arm_obj["dw2_digimon"] = entry["id"]
    arm_obj["dw2_name"] = name
    context.scene.frame_set(1)
    return arm_obj


def pick_items(self, context):
    try:
        ch = choices(context or bpy.context)
    except Exception:
        return _EMPTY
    return ch.get("tech" if self.which == "technique" else "digi") or _EMPTY


class DW2_OT_pick(bpy.types.Operator):
    """Pick from a list you can type into to search"""
    bl_idname = "dw2.pick"
    bl_label = "Pick"
    bl_property = "choice"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    which: bpy.props.StringProperty(options={"HIDDEN"})
    choice: bpy.props.EnumProperty(name="Choice", items=pick_items)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        arm = find_armature(context)
        if arm is None or "dw2_meta" not in arm:
            self.report({"ERROR"}, "Select the Digimon first")
            return {"CANCELLED"}
        v = int(self.choice or 0)
        if self.which == "technique":
            arm.dw2.technique_id = v
        elif self.which.startswith("evo"):
            i = int(self.which[3:])
            setattr(arm.dw2, "evo%d_id" % i, v)
            if v == 0:      # (none) ends the list here
                for j in range(i + 1, 4):
                    setattr(arm.dw2, "evo%d_id" % j, 0)
        scr = getattr(context, "screen", None)
        for area in scr.areas if scr else ():
            area.tag_redraw()
        return {"FINISHED"}


class DW2_OT_use_forbs_folders(bpy.types.Operator):
    """Empty both folder boxes, so the add-on uses your forbs-hidden-mods folder's game-data and mods"""
    bl_idname = "dw2.use_forbs_folders"
    bl_label = "Use forbs-hidden-mods folders"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context.scene.dw2_data_dir = ""
        context.scene.dw2_mods_dir = ""
        forget_tables()
        return {"FINISHED"}


class DW2_OT_import(bpy.types.Operator):
    """Import a Digimon (model, texture and all its animations) from the data folder"""
    bl_idname = "dw2.import_digimon"
    bl_label = "Import Digimon"
    bl_options = {"REGISTER", "UNDO"}
    bl_property = "digimon"

    digimon: bpy.props.EnumProperty(name="Digimon", items=digimon_items)

    def invoke(self, context, event):
        if not os.path.isdir(data_dir(context)):
            self.report({"ERROR"}, "Set the DW2 data folder first (the unzipped dw2_models.zip)")
            return {"CANCELLED"}
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        folder = data_dir(context)
        table = load_table(folder, mods_dir(context))
        entry = next((e for e in table if str(e["id"]) == self.digimon), None)
        if entry is None:
            self.report({"ERROR"}, "No such Digimon in the data folder")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        name = entry["name"] or "Digimon%d" % entry["id"]
        model, anims = dw2core.load_digimon(folder, entry, mods_dir(context) or None)
        scene = dw2core.import_digimon(model, anims, name)
        try:
            for b, nm in zip(scene["bones"], dw2names.guess(scene)):
                b["name"] = nm                    # best guesses: wing_L_12, thigh_R_17 ...
        except Exception:                         # keep bone_NN
            pass
        already = [o.name for o in bpy.data.objects if is_dw2_armature(o) and o.get("dw2_name") == name]
        arm_new = build_scene(context, scene, name, entry)
        try:
            fill_props(arm_new, source(context), entry["id"], entry["name"])
        except Exception as ex:                   # the panel stays empty; the model still works
            print("[DW2] properties:", ex)
        if already:
            self.report({"WARNING"}, "%s was already in the scene (%s): this is a second copy" % (
                name, ", ".join(already)))
        else:
            self.report({"INFO"}, "%s: %d bones, %d faces, %d animations" % (
                name, len(scene["bones"]), len(scene["polys"]), len(scene["actions"])))
        return {"FINISHED"}


# ---------------------------------------------------------------- export

def gather(context, arm_obj, report):
    """Read the armature, its meshes, texture and actions into the core's scene dict."""
    meta = json.loads(arm_obj["dw2_meta"])
    bones_b = list(arm_obj.data.bones)
    names = [b.name for b in bones_b]
    index = {n: i for i, n in enumerate(names)}
    bones = [{"name": b.name, "parent": index[b.parent.name] if b.parent else -1,
              "rest": [list(r) for r in b.matrix_local]} for b in bones_b]
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and (
        o.parent == arm_obj or any(m.type == "ARMATURE" and m.object == arm_obj for m in o.modifiers))
        and "dw2_preview" not in o and o.visible_get()]
    if not meshes:
        raise dw2core.ExportError("no visible mesh is attached to the armature")
    verts, vbone, polys = [], [], []
    mat_index = {}
    materials = []
    image = None
    to_arm = arm_obj.matrix_world.inverted()
    unweighted = 0
    for ob in meshes:
        me = ob.data
        m = to_arm @ ob.matrix_world
        rot = m.to_3x3()
        base = len(verts)
        gname = {g.index: g.name for g in ob.vertex_groups}
        for v in me.vertices:
            verts.append(list(m @ v.co))
            best = None
            for g in v.groups:
                n = gname.get(g.group)
                if n in index and g.weight > 0 and (best is None or g.weight > best[0]):
                    best = (g.weight, index[n])
            if best is None:
                unweighted += 1
                pb = ob.parent_bone if ob.parent_type == "BONE" else None
                vbone.append(index.get(pb, 0))
            else:
                vbone.append(best[1])
        uvl = me.uv_layers.active
        if uvl is None:
            raise dw2core.ExportError("%s has no UV map" % ob.name)
        if hasattr(me, "corner_normals"):
            cn = [rot @ Vector(c.vector) for c in me.corner_normals]
        else:
            me.calc_normals_split()
            cn = [rot @ Vector(lp.normal) for lp in me.loops]
        semi = me.attributes.get("dw2_semi")
        tpage = me.attributes.get("dw2_tpage")
        for p in me.polygons:
            mat = ob.material_slots[p.material_index].material if ob.material_slots else None
            key = mat.name if mat else None
            if key not in mat_index:
                mat_index[key] = len(materials)
                materials.append(mat.get("dw2_clut") if mat is not None else None)
                img = material_image(mat)
                if img is not None:
                    if image is None:
                        image = img
                    elif img != image:
                        raise dw2core.ExportError("every material must use the same texture image (%s and %s)"
                                                  % (image.name, img.name))
            loops = list(p.loop_indices)
            polys.append({
                "verts": [base + me.loops[li].vertex_index for li in loops],
                "uvs": [tuple(uvl.data[li].uv) for li in loops],
                "normals": [list(cn[li].normalized()) for li in loops],
                "material": mat_index[key],
                "semi": semi.data[p.index].value if semi else 0,
                "tpage": tpage.data[p.index].value if tpage else 0,
            })
    if unweighted:
        report.append("%d vertices had no bone weight and follow their object's bone (or the first bone)"
                      % unweighted)
    if image is None:
        raise dw2core.ExportError("no texture image found in the materials")
    w0, h0 = dw2model.Tim(bytes.fromhex(meta["tim"])).width, dw2model.Tim(bytes.fromhex(meta["tim"])).height
    img = image
    scaled = None
    if tuple(img.size) != (w0, h0):
        scaled = img.copy()
        scaled.scale(w0, h0)
        img = scaled
        report.append("texture %s scaled to %d x %d" % (image.name, w0, h0))
    w, h = img.size
    px = list(img.pixels[:])
    if scaled is not None:
        bpy.data.images.remove(scaled)
    rgba = bytearray(w * h * 4)
    for y in range(h):
        src = (h - 1 - y) * w * 4
        dst = y * w * 4
        for i in range(w * 4):
            rgba[dst + i] = max(0, min(255, int(round(px[src + i] * 255))))
    # actions
    actions = []
    uid = arm_obj.get("dw2_uid")
    scn = context.scene
    keep_action = arm_obj.animation_data.action if arm_obj.animation_data else None
    keep_frame = scn.frame_current
    for act in bpy.data.actions:
        if act.get("dw2_owner") != uid or "dw2_slot" not in act:
            continue
        assign_action(arm_obj, act)
        f0, f1 = key_range(act, arm_obj)
        frames = []
        for f in range(f0, f1 + 1):
            scn.frame_set(f)
            frames.append([[list(r) for r in arm_obj.pose.bones[n].matrix] for n in names])
        actions.append({"slot": int(act["dw2_slot"]), "index": int(act["dw2_index"]),
                        "loop_to": int(act.get("dw2_loop_to", -1)), "pose": frames})
    assign_action(arm_obj, keep_action)
    scn.frame_set(keep_frame)
    return {"bones": bones, "verts": verts, "vbone": vbone, "polys": polys,
            "materials": materials, "image": (w, h, bytes(rgba)), "actions": actions, "meta": meta}


class DW2_OT_export(bpy.types.Operator):
    """Write this Digimon's model and animation files into the mods folder"""
    bl_idname = "dw2.export_digimon"
    bl_label = "Export to mods folder"

    def execute(self, context):
        arm_obj = find_armature(context)
        if arm_obj is None or "dw2_meta" not in arm_obj:
            self.report({"ERROR"}, "Select a Digimon imported with this add-on (its armature or mesh)")
            return {"CANCELLED"}
        out = bpy.path.abspath(context.scene.dw2_mods_dir)
        if not out:
            self.report({"ERROR"}, "Set the mods folder first (the mods folder next to dw2.exe)")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        report = []
        try:
            sc = gather(context, arm_obj, report)
            files, rep = dw2core.export_digimon(sc, int(arm_obj["dw2_model"]), arm_obj.get("dw2_name", ""))
        except dw2core.ExportError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        report += rep
        os.makedirs(out, exist_ok=True)
        for fid, data in sorted(files.items()):
            if len(data) > 0x80000:
                self.report({"ERROR"}, "file %04X is %d KB; the game's limit here is 512 KB" % (fid, len(data) // 1024))
                return {"CANCELLED"}
        labels = file_labels(arm_obj.get("dw2_name", arm_obj.name), int(arm_obj["dw2_model"]),
                             dw2core_anims(arm_obj, files))
        names = {}
        for fid, data in sorted(files.items()):
            names[fid] = dw2modfiles.write(out, fid, data, labels.get(fid))
        try:
            for fid in write_tables(context, arm_obj, out, int(arm_obj["dw2_digimon"]), report):
                files[fid] = b""
        except (dw2core.ExportError, ValueError) as ex:
            self.report({"ERROR"}, "model written, but not its name / stats: %s" % ex)
            return {"CANCELLED"}
        text = bpy.data.texts.get("DW2 export report") or bpy.data.texts.new("DW2 export report")
        text.clear()
        text.write("%s: %d files written to %s\n" % (arm_obj.get("dw2_name", arm_obj.name), len(files), out))
        text.write("".join("  %s\n" % (names.get(fid) or os.path.basename(dw2modfiles.find(out, fid) or "%04X.bin" % fid))
                           for fid in sorted(files)))
        text.write("".join("- %s\n" % r for r in report) or "no warnings\n")
        self.report({"INFO"}, "%d files written (%d notes: see the text 'DW2 export report')" % (len(files), len(report)))
        return {"FINISHED"}


def file_labels(name, model_id, anims):
    """{file id: label} for a Digimon's files: "Agumon model", "Agumon animations 3"."""
    name = name or "Digimon"
    out = {model_id: "%s model" % name}
    for k, a in enumerate(anims or []):
        if a and a > 0 and a not in out:
            out[a] = "%s animations %d" % (name, k)
    return out


def dw2core_anims(arm, files):
    """The animation file numbers of the Digimon an armature is (its table entry)."""
    try:
        e = next((e for e in dw2digi.load_table(*_table_dirs()) if e["id"] == int(arm.get("dw2_digimon", 0))), None)
    except Exception:
        e = None
    return e["anims"] if e else []


def _table_dirs():
    ctx = bpy.context
    return data_dir(ctx), mods_dir(ctx) or None


def _first_free(context):
    free = dw2tables.free_numbers(source(context))
    pref = [n for n in free if 150 <= n <= 179] or free
    return pref[0] if pref else 0


class DW2_OT_save_new(bpy.types.Operator):
    """Export this Digimon as a brand-new one: its own number, name, model and animation files
    and base data; the Digimon it was made from is left as it is"""
    bl_idname = "dw2.save_new_digimon"
    bl_label = "Save as new Digimon"
    bl_options = {"REGISTER"}

    number: bpy.props.IntProperty(name="Number", min=1, max=255,
                                  description="Its slot, 1..255 (a party Digimon's number is one byte)")
    new_name: bpy.props.StringProperty(name="Name", maxlen=13)

    def invoke(self, context, event):
        arm = find_armature(context)
        if arm is None or "dw2_meta" not in arm:
            self.report({"ERROR"}, "Select a Digimon imported with this add-on")
            return {"CANCELLED"}
        if not context.scene.dw2_mods_dir:
            self.report({"ERROR"}, "Set the mods folder first")
            return {"CANCELLED"}
        mine = arm.get("dw2_new")
        self.number = int(arm["dw2_digimon"]) if mine else _first_free(context)
        self.new_name = arm.dw2.name if mine else ""
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "new_name")
        lay.prop(self, "number")
        free = dw2tables.free_numbers(source(context))
        lay.label(text="Free numbers: " + ", ".join(str(n) for n in free[:12]) + (" ..." if len(free) > 12 else ""))
        lay.label(text="A number you used for one of your own Digimon is replaced.")

    def execute(self, context):
        arm = find_armature(context)
        out = bpy.path.abspath(context.scene.dw2_mods_dir)
        n = int(self.number)
        name = self.new_name.strip()
        if not name:
            self.report({"ERROR"}, "Give it a name")
            return {"CANCELLED"}
        try:
            dw2tables.encode_name(name)
        except ValueError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        src = source(context)
        original = dw2tables.taken_numbers(dw2tables.Source(data_dir(context)))
        if n in original:
            self.report({"ERROR"}, "Number %d is one of the game's own Digimon; free ones: %s" % (
                n, ", ".join(str(x) for x in dw2tables.free_numbers(src)[:10])))
            return {"CANCELLED"}
        replacing = n in dw2tables.taken_numbers(src) and not (arm.get("dw2_new") and int(arm["dw2_digimon"]) == n)
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        template = dw2tables.get_entry(src, int(arm["dw2_digimon"]))
        model_id, anim_ids = dw2tables.new_files(n)
        report = []
        try:
            sc = gather(context, arm, report)
            meta = json.loads(arm["dw2_meta"])
            anims = []
            for k, slot in enumerate(meta["slots"]):
                if slot.get("file", 0) > 0:
                    slot["file"] = anim_ids[k]
                    anims.append(anim_ids[k])
                else:
                    anims.append(0)
            sc["meta"] = meta
            files, rep = dw2core.export_digimon(sc, model_id, name)
        except dw2core.ExportError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        report += rep
        os.makedirs(out, exist_ok=True)
        labels = file_labels(name, model_id, anims)
        for fid, data in sorted(files.items()):
            dw2modfiles.write(out, fid, data, labels.get(fid))
        arm.dw2.name = name
        try:
            write_tables(context, arm, out, n, report, entry_template=template, model=model_id, anims=anims)
        except (dw2core.ExportError, ValueError) as ex:
            self.report({"ERROR"}, "files written, but not its table entry: %s" % ex)
            return {"CANCELLED"}
        # from now on this armature is the new Digimon
        try:
            arm.name = name
            arm.data.name = name
        except (AttributeError, TypeError):
            pass
        arm["dw2_digimon"] = n
        arm["dw2_model"] = model_id
        arm["dw2_name"] = name
        arm["dw2_new"] = 1
        arm["dw2_meta"] = json.dumps(meta)
        if replacing:
            report.insert(0, "replaced the Digimon you made earlier as number %d" % n)
        text = bpy.data.texts.get("DW2 export report") or bpy.data.texts.new("DW2 export report")
        text.clear()
        text.write("%s saved as a new Digimon, number %d: %d files in %s\n" % (name, n, len(files) + 2, out))
        text.write("".join("  %s\n" % os.path.basename(dw2modfiles.find(out, fid) or "%04X.bin" % fid)
                           for fid in sorted(files)))
        text.write("".join("- %s\n" % r for r in report) or "no warnings\n")
        self.report({"INFO"}, "%s is number %d (model file %04X). Get it in the dev build: F2 > Save > Edit > "
                              "Add Digimon" % (name, n, model_id))
        return {"FINISHED"}


class DW2_OT_check(bpy.types.Operator):
    """Count what the game limits: corners and normals per bone, bones, tree depth"""
    bl_idname = "dw2.check_digimon"
    bl_label = "Check limits"

    def execute(self, context):
        arm_obj = find_armature(context)
        if arm_obj is None or "dw2_meta" not in arm_obj:
            self.report({"ERROR"}, "Select a Digimon imported with this add-on")
            return {"CANCELLED"}
        report = []
        try:
            sc = gather(context, arm_obj, report)
            sc["actions"] = []                  # geometry only: quick
            files, rep = dw2core.export_digimon(sc, int(arm_obj["dw2_model"]))
        except dw2core.ExportError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        m = dw2model.Model.parse(files[int(arm_obj["dw2_model"])])
        worst = max(m.bones, key=lambda b: len(b.verts))
        self.report({"INFO"}, "OK: %d bones, %d faces, busiest bone %d / 256 corners%s" % (
            len(m.bones), sum(len(b.faces) for b in m.bones), len(worst.verts),
            ("; " + "; ".join(report + rep)) if report or rep else ""))
        return {"FINISHED"}


# ---------------------------------------------------------------- take parts from another Digimon

def is_dw2_armature(ob):
    return ob is not None and ob.type == "ARMATURE" and "dw2_meta" in ob


def attached_meshes(arm_obj, visible_only=True):
    return [o for o in bpy.data.objects if o.type == "MESH" and (
        o.parent == arm_obj or any(m.type == "ARMATURE" and m.object == arm_obj for m in o.modifiers))
        and "dw2_preview" not in o and (not visible_only or o.visible_get())]


def vertex_owner(ob, v, index):
    """Bone name a vertex follows: its heaviest bone group."""
    gname = {g.index: g.name for g in ob.vertex_groups}
    best = None
    for g in v.groups:
        n = gname.get(g.group)
        if n in index and g.weight > 0 and (best is None or g.weight > best[0]):
            best = (g.weight, n)
    return best[1] if best else None


def selected_parts(donor):
    """Bones picked on the donor: selected bones (Pose or Edit Mode), plus the bones of any
    selected faces of its meshes; then every bone below them."""
    names = set(b.name for b in donor.data.bones if getattr(b, "select", False))
    index = {b.name: i for i, b in enumerate(donor.data.bones)}
    for ob in attached_meshes(donor):
        me = ob.data
        sel = [p for p in me.polygons if getattr(p, "select", False)]
        if len(sel) == len(me.polygons):
            continue                      # everything selected: not a choice of parts
        for p in sel:
            if True:
                for vi in p.vertices if hasattr(p, "vertices") else [me.loops[li].vertex_index for li in p.loop_indices]:
                    n = vertex_owner(ob, me.vertices[vi], index)
                    if n:
                        names.add(n)
    out = set(names)
    grew = True
    while grew:
        grew = False
        for b in donor.data.bones:
            if b.name not in out and b.parent is not None and b.parent.name in out:
                out.add(b.name)
                grew = True
    return [b.name for b in donor.data.bones if b.name in out]


def mesh_height(arm_obj):
    to_arm = arm_obj.matrix_world.inverted()
    lo, hi = None, None
    for ob in attached_meshes(arm_obj):
        m = to_arm @ ob.matrix_world
        for v in ob.data.vertices:
            z = (m @ v.co)[2]
            lo = z if lo is None else min(lo, z)
            hi = z if hi is None else max(hi, z)
    return (hi - lo) if lo is not None and hi > lo else 1.0


def body_bone(arm_obj):
    """Where parts go by default: the chest (or body), else the hips, else the bone with the
    most mesh."""
    for prefix in ("chest_", "body_", "hips_"):
        for b in arm_obj.data.bones:
            if b.name.startswith(prefix):
                return b.name
    return busiest_bone(arm_obj)


def busiest_bone(arm_obj):
    counts = {}
    index = {b.name: i for i, b in enumerate(arm_obj.data.bones)}
    for ob in attached_meshes(arm_obj):
        for v in ob.data.vertices:
            n = vertex_owner(ob, v, index)
            if n:
                counts[n] = counts.get(n, 0) + 1
    return max(counts, key=counts.get) if counts else arm_obj.data.bones[0].name


def texel_uvs(uvs, w, h):
    """Blender UVs of one face (loop order) -> texel coordinates in the game's strip order."""
    t = [(u * w, (1.0 - v) * h) for u, v in uvs]
    return [t[0], t[1], t[3], t[2]] if len(t) == 4 else t


def read_pixels(img):
    return list(img.pixels[:])


def action_curves(action, obj):
    fcurves, _slot = fcurve_list(action, obj)
    return {(fc.data_path, fc.array_index): fc for fc in fcurves}


def add_parts(context, donor, target, attach, motion, report):
    names = selected_parts(donor)
    if not names:
        raise dw2core.ExportError(
            "nothing selected on %s: in Pose Mode, click the bones of the parts you want "
            "(Shift-click for more), or select their faces in Edit Mode" % donor.name)
    if attach not in target.data.bones:
        raise dw2core.ExportError("%s has no bone called %s" % (target.name, attach))
    S = set(names)
    dbones = {b.name: b for b in donor.data.bones}
    # where they go: same offset from the attach point, scaled to the target's size
    roots = [n for n in names if dbones[n].parent is None or dbones[n].parent.name not in S]
    p = dbones[roots[0]].parent
    d_anchor = Vector(p.matrix_local.translation if hasattr(p.matrix_local, "translation")
                      else [r[3] for r in list(p.matrix_local)[:3]]) if p is not None else Vector((0.0, 0.0, 0.0))
    t_attach = target.data.bones[attach].matrix_local
    t_anchor = Vector(t_attach.translation if hasattr(t_attach, "translation")
                      else [r[3] for r in list(t_attach)[:3]])
    s = mesh_height(target) / mesh_height(donor)
    s = max(0.2, min(5.0, s))

    def place(co):
        return [t_anchor[k] + s * (co[k] - d_anchor[k]) for k in range(3)]

    prefix = donor.get("dw2_name", donor.name)
    newname = {}
    for n in names:
        nm = "%s_%s" % (prefix, n)
        k = 2
        while nm in target.data.bones or nm in newname.values():
            nm = "%s_%s_%d" % (prefix, n, k)
            k += 1
        newname[n] = nm
    # ---- texture: the target's image and free space
    tmeta = json.loads(target["dw2_meta"])
    tmeshes = attached_meshes(target, visible_only=False)
    timg = None
    tuvs, tcluts = [], []
    for ob in tmeshes:
        me = ob.data
        uvl = me.uv_layers.active
        for slot in ob.material_slots:
            if slot.material is not None:
                tcluts.append(slot.material.get("dw2_clut"))
                if timg is None:
                    timg = material_image(slot.material)
        if uvl is None:
            continue
    if timg is None:
        raise dw2core.ExportError(
            "found no texture on %s (its meshes: %s). Is 'Add to' the right Digimon?" % (
                target.name, ", ".join(o.name for o in tmeshes) or "none"))
    tw, th = timg.size
    for ob in tmeshes:
        me = ob.data
        uvl = me.uv_layers.active
        if uvl is None:
            continue
        for poly in me.polygons:
            tuvs.append(texel_uvs([tuple(uvl.data[li].uv) for li in poly.loop_indices], tw, th))
    occ = dw2parts.occupancy(tw, th, tuvs, tcluts, bytes.fromhex(tmeta.get("texanim", "")))
    # ---- the donor faces to copy
    dmeshes = attached_meshes(donor, visible_only=False)
    seen = {}
    checked = [0, 0, 0]       # meshes, meshes with UVs, faces
    dindex = {b.name: i for i, b in enumerate(donor.data.bones)}
    to_darm = donor.matrix_world.inverted()
    verts, vgroup, faces = [], [], []
    dimg = None
    mats = []
    mat_of = {}
    for ob in dmeshes:
        me = ob.data
        # the donor's mesh as it sits on its own skeleton: a mesh object moved away from it
        # (to see the two Digimon side by side) does not move the parts
        m = Matrix() if ob.parent == donor else to_darm @ ob.matrix_world
        rot = m.to_3x3()
        checked[0] += 1
        uvl = me.uv_layers.active or (me.uv_layers[0] if len(me.uv_layers) else None)
        if uvl is None:
            continue
        checked[1] += 1
        owner = [vertex_owner(ob, v, dindex) for v in me.vertices]
        if hasattr(me, "corner_normals"):
            cn = [list((rot @ Vector(c.vector)).normalized()) for c in me.corner_normals]
        else:
            me.calc_normals_split()
            cn = [list((rot @ Vector(lp.normal)).normalized()) for lp in me.loops]
        semi = me.attributes.get("dw2_semi")
        tpage = me.attributes.get("dw2_tpage")
        vmap = {}
        for poly in me.polygons:
            loops = list(poly.loop_indices)
            vis = [me.loops[li].vertex_index for li in loops]
            checked[2] += 1
            owners = [owner[v] for v in vis]
            # the face goes with the bone most of its corners follow
            main = max(set(owners), key=lambda o: (owners.count(o), o is not None and o in S))
            seen[main] = seen.get(main, 0) + 1
            if main not in S:
                continue
            mat = ob.material_slots[poly.material_index].material if ob.material_slots else None
            img = material_image(mat)
            if img is not None:
                dimg = dimg or img
            key = mat.name if mat else ""
            if key not in mat_of:
                mat_of[key] = len(mats)
                mats.append(mat)
            out_v = []
            for v in vis:
                if (ob.name, v) not in vmap:
                    vmap[(ob.name, v)] = len(verts)
                    verts.append(place(m @ me.vertices[v].co))
                    vgroup.append(newname[owner[v] if owner[v] in S else main])
                out_v.append(vmap[(ob.name, v)])
            faces.append({"verts": out_v, "uvs": [tuple(uvl.data[li].uv) for li in loops],
                          "normals": [cn[li] for li in loops], "mat": mat_of[key],
                          "semi": semi.data[poly.index].value if semi else 0,
                          "tpage": tpage.data[poly.index].value if tpage else 0})
    if not faces:
        top = sorted(seen.items(), key=lambda kv: -kv[1])[:6]
        raise dw2core.ExportError(
            "no faces of %s follow the selected bones (%s). Checked %d mesh(es) (%d with UVs), %d faces; "
            "their faces follow: %s" % (
                donor.name, ", ".join(names[:6]), checked[0], checked[1], checked[2],
                ", ".join("%s x%d" % (k or "no bone", n) for k, n in top) or "nothing"))
    if dimg is None:
        raise dw2core.ExportError("%s has no texture image" % donor.name)
    dw_, dh_ = dimg.size
    cells = dw2parts.reserve_cells(occ, len(mats))
    if cells is None:
        raise dw2core.ExportError("no room left in %s's texture for %d more palettes" % (target.name, len(mats)))
    rects, own = dw2parts.islands([texel_uvs(f["uvs"], dw_, dh_) for f in faces], dw_, dh_)
    spots = dw2parts.pack(occ, rects)
    if spots is None:
        need = sum(r[2] * r[3] for r in rects)
        raise dw2core.ExportError("not enough free space in %s's texture for these parts (they need about "
                                  "%d texels in %d pieces); pick fewer parts" % (target.name, need, len(rects)))
    # copy the texels (Blender keeps the bottom row first)
    dpx = read_pixels(dimg)
    tpx = read_pixels(timg)
    for (rx, ry, rw, rh), (nx, ny) in zip(rects, spots):
        for j in range(rh):
            src = ((dh_ - 1 - (ry + j)) * dw_ + rx) * 4
            dst = ((th - 1 - (ny + j)) * tw + nx) * 4
            tpx[dst:dst + rw * 4] = dpx[src:src + rw * 4]
    timg.pixels.foreach_set(tpx)
    try:
        timg.pack()
    except RuntimeError:
        pass
    for f, k in zip(faces, own):
        (rx, ry, _, _), (nx, ny) = rects[k], spots[k]
        f["uvs"] = [((u * dw_ - rx + nx) / tw, 1.0 - ((1.0 - v) * dh_ - ry + ny) / th) for u, v in f["uvs"]]
    # ---- bones
    keep_active = context.view_layer.objects.active
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in context.selected_objects:
        o.select_set(False)
    context.view_layer.objects.active = target
    target.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    ebs = target.data.edit_bones
    for n in names:
        db = dbones[n]
        ml = db.matrix_local
        eb = ebs.new(newname[n])
        eb.head = (0.0, 0.0, 0.0)
        eb.tail = (0.0, 0.1, 0.0)
        rows = [list(r) for r in ml]
        pos = place([rows[0][3], rows[1][3], rows[2][3]])
        eb.matrix = Matrix([rows[0][:3] + [pos[0]], rows[1][:3] + [pos[1]], rows[2][:3] + [pos[2]],
                            [0.0, 0.0, 0.0, 1.0]])
        eb.length = max(0.01, db.length * s) if hasattr(db, "length") else 0.05
        eb.use_connect = False
    for n in names:
        db = dbones[n]
        par = db.parent.name if db.parent is not None and db.parent.name in S else None
        ebs[newname[n]].parent = ebs[newname[par]] if par else ebs[attach]
    bpy.ops.object.mode_set(mode="OBJECT")
    for n in names:
        target.pose.bones[newname[n]].rotation_mode = "QUATERNION"
    # ---- mesh object
    tname = target.get("dw2_name", target.name)
    me = bpy.data.meshes.new("%s_%s_parts" % (tname, prefix))
    me.from_pydata(verts, [], [f["verts"] for f in faces])
    uvl = me.uv_layers.new(name="UVMap")
    uvl.data.foreach_set("uv", [c for f in faces for xy in f["uvs"] for c in xy])
    for k in range(len(mats)):
        make = make_material("%s_%s_pal_%d" % (tname, prefix, k), timg, 0)
        del make["dw2_clut"]              # a new palette: export finds it a place
        me.materials.append(make)
    me.polygons.foreach_set("material_index", [f["mat"] for f in faces])
    for key in ("semi", "tpage"):
        at = me.attributes.new("dw2_" + key, "INT", "FACE")
        at.data.foreach_set("value", [int(f[key]) for f in faces])
    me.update()
    try:
        if hasattr(me, "use_auto_smooth"):
            me.use_auto_smooth = True
        me.normals_split_custom_set([n for f in faces for n in f["normals"]])
    except (RuntimeError, AttributeError, TypeError):
        pass
    ob = bpy.data.objects.new(me.name, me)
    context.collection.objects.link(ob)
    ob.parent = target
    ob["dw2_parts"] = json.dumps([newname[n] for n in names])
    ob["dw2_parts_scale"] = s
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = target
    groups = {}
    for vi, g in enumerate(vgroup):
        if g not in groups:
            groups[g] = ob.vertex_groups.new(name=g)
        groups[g].add([vi], 1.0, "REPLACE")
    # ---- motion
    dact = donor.animation_data.action if donor.animation_data else None
    if dact is None or "dw2_slot" not in dact:
        dact = next((a for a in bpy.data.actions if a.get("dw2_owner") == donor.get("dw2_uid")), None)
    uid = target.get("dw2_uid")
    tacts = [a for a in bpy.data.actions if a.get("dw2_owner") == uid and "dw2_slot" in a]
    dcurves = action_curves(dact, donor) if (dact is not None and motion == "LOOP") else {}
    d0, d1 = key_range(dact, donor) if dact is not None else (1, 1)
    for act in tacts:
        f0, f1 = key_range(act, target)
        fcurves, _slot = fcurve_list(act, target)
        times = dw2parts.resample(d1 - d0 + 1, f1 - f0 + 1) if dcurves else [0.0]
        frames = list(range(f0, f0 + len(times)))
        for n in names:
            path_d = 'pose.bones["%s"].' % n
            path_t = 'pose.bones["%s"].' % newname[n]
            for prop, size, default in (("location", 3, (0.0, 0.0, 0.0)),
                                        ("rotation_quaternion", 4, (1.0, 0.0, 0.0, 0.0)),
                                        ("scale", 3, (1.0, 1.0, 1.0))):
                for k in range(size):
                    src = dcurves.get((path_d + prop, k))
                    vals = [src.evaluate(d0 + t) if src is not None else default[k] for t in times]
                    if prop == "location":
                        vals = [v * s for v in vals]
                    try:
                        fc = fcurves.new(path_t + prop, index=k, action_group=newname[n])
                    except TypeError:
                        fc = fcurves.new(path_t + prop, index=k)
                    fc.keyframe_points.add(len(frames))
                    co = []
                    for f, v in zip(frames, vals):
                        co += [float(f), float(v)]
                    fc.keyframe_points.foreach_set("co", co)
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"
                    fc.update()
    report.append("%d parts (%d bones, %d faces) from %s added to %s on %s, scaled %.2fx"
                  % (len(roots), len(names), len(faces), prefix, tname, attach, s))
    if dcurves:
        report.append("their motion from %s loops in all %d of %s's animations" % (dact.name, len(tacts), tname))
    for o in context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    return ob


class DW2_OT_add_parts(bpy.types.Operator):
    """Copy the selected bones of this Digimon (with their mesh, texture and motion) onto the
    target Digimon, attached to the chosen bone"""
    bl_idname = "dw2.add_parts"
    bl_label = "Add selected parts"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        sc = context.scene
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")    # brings Edit Mode face selections up to date
        donor = find_armature(context)
        target = sc.dw2_target
        if not is_dw2_armature(donor):
            self.report({"ERROR"}, "Select the Digimon you take the parts FROM (its armature, in Pose Mode)")
            return {"CANCELLED"}
        if not is_dw2_armature(target):
            self.report({"ERROR"}, "Pick the Digimon to add the parts TO in 'Add to'")
            return {"CANCELLED"}
        if target == donor:
            self.report({"ERROR"}, "'Add to' is the same Digimon the parts come from")
            return {"CANCELLED"}
        if target.name not in sc.objects:
            self.report({"ERROR"}, "The %s in 'Add to' is not in the scene any more (deleted, or an old "
                                   "copy): pick 'Add to' again" % target.name)
            return {"CANCELLED"}
        attach = sc.dw2_attach or body_bone(target)
        report = []
        try:
            add_parts(context, donor, target, attach, sc.dw2_parts_motion, report)
        except dw2core.ExportError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        self.report({"INFO"}, "; ".join(report))
        return {"FINISHED"}


def apply_placement(context, ob):
    """Bake the parts object's own move / turn / scale into its mesh and its bones (rest
    position and the size of their motion), so the parts move around their new spot."""
    arm = ob.parent
    names = json.loads(ob["dw2_parts"])
    D = ob.matrix_basis.copy()
    if all(abs(D[i][j] - (1.0 if i == j else 0.0)) < 1e-6 for i in range(4) for j in range(4)):
        return 0.0
    loc, rot, scl = D.decompose()
    sc = (abs(scl[0]) + abs(scl[1]) + abs(scl[2])) / 3.0
    me = ob.data
    R = D.to_3x3()
    if hasattr(me, "corner_normals"):
        normals = [list((R @ Vector(c.vector)).normalized()) for c in me.corner_normals]
    else:
        me.calc_normals_split()
        normals = [list((R @ Vector(lp.normal)).normalized()) for lp in me.loops]
    for v in me.vertices:
        v.co = D @ v.co
    me.update()
    try:
        if hasattr(me, "use_auto_smooth"):
            me.use_auto_smooth = True
        me.normals_split_custom_set(normals)
    except (RuntimeError, AttributeError, TypeError):
        pass
    ob.matrix_basis = Matrix()
    keep = context.view_layer.objects.active
    for o in context.selected_objects:
        o.select_set(False)
    context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    ebs = arm.data.edit_bones
    for n in names:
        if n in ebs:
            eb = ebs[n]
            ln = eb.length
            eb.matrix = D @ eb.matrix
            eb.length = max(0.01, ln * sc)
    bpy.ops.object.mode_set(mode="OBJECT")
    # the parts' own motion: offsets grow or shrink with them
    uid = arm.get("dw2_uid")
    paths = set('pose.bones["%s"].location' % n for n in names)
    for act in bpy.data.actions:
        if act.get("dw2_owner") != uid:
            continue
        fcurves, _slot = fcurve_list(act, arm)
        for fc in fcurves:
            if fc.data_path in paths:
                for kp in fc.keyframe_points:
                    kp.co = (kp.co[0], kp.co[1] * sc)
                fc.update()
    for o in context.selected_objects:
        o.select_set(False)
    context.view_layer.objects.active = ob
    ob.select_set(True)
    return sc


class DW2_OT_apply_parts(bpy.types.Operator):
    """Make the parts object's move / turn / scale permanent: the mesh and its bones move
    together, so the parts animate around their new spot"""
    bl_idname = "dw2.apply_parts"
    bl_label = "Apply placement"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ob = context.active_object
        if ob is None or "dw2_parts" not in ob or ob.parent is None:
            self.report({"ERROR"}, "Select a parts object made with 'Add selected parts'")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        sc = apply_placement(context, ob)
        self.report({"INFO"}, "placement applied" if sc else "nothing to apply: move, turn or scale the object first")
        return {"FINISHED"}


def _target_poll(self, ob):
    # only Digimon in this scene (a deleted one can linger in the file)
    return is_dw2_armature(ob) and ob.name in self.objects


# ---------------------------------------------------------------- preview of the selected parts

_preview_state = {"key": None}


def clear_preview():
    for o in [o for o in bpy.data.objects if "dw2_preview" in o]:
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def preview_material():
    mat = bpy.data.materials.get("DW2 preview")
    if mat is None:
        mat = bpy.data.materials.new("DW2 preview")
        mat.diffuse_color = (1.0, 0.45, 0.0, 1.0)
    return mat


def build_preview(arm, names, scene_coll):
    """An orange copy of the selected bones' faces, drawn in front of everything and moved by
    the same skeleton, so you can see what you have picked."""
    clear_preview()
    if arm is None or not names:
        return
    S = set(names)
    index = {b.name: i for i, b in enumerate(arm.data.bones)}
    for ob in attached_meshes(arm, visible_only=False):
        me = ob.data
        owner = [vertex_owner(ob, v, index) for v in me.vertices]
        keep = []
        for p in me.polygons:
            vis = list(p.vertices)
            ow = [owner[v] for v in vis]
            if max(set(ow), key=ow.count) in S:
                keep.append(vis)
        if not keep:
            continue
        used = sorted(set(v for f in keep for v in f))
        remap = {v: i for i, v in enumerate(used)}
        pm = bpy.data.meshes.new("DW2 preview")
        pm.from_pydata([tuple(me.vertices[v].co) for v in used], [], [[remap[v] for v in f] for f in keep])
        pm.materials.append(preview_material())
        pm.update()
        po = bpy.data.objects.new("DW2 preview", pm)
        po["dw2_preview"] = 1
        coll = ob.users_collection[0] if ob.users_collection else scene_coll
        coll.objects.link(po)
        po.parent = ob.parent
        po.matrix_parent_inverse = ob.matrix_parent_inverse.copy()
        po.matrix_basis = ob.matrix_basis.copy()
        po.show_in_front = True
        po.hide_select = True
        mod = po.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
        groups = {}
        for v in used:
            n = owner[v]
            if n is None:
                continue
            if n not in groups:
                groups[n] = po.vertex_groups.new(name=n)
            groups[n].add([remap[v]], 1.0, "REPLACE")


def _preview_tick():
    """Every quarter second while the preview is on: rebuild it when the selection changes."""
    try:
        context = bpy.context
        sc = context.scene
        if sc is None or not getattr(sc, "dw2_preview", False):
            clear_preview()
            _preview_state["key"] = None
            return None                          # stop the timer
        ob = context.view_layer.objects.active if context.view_layer else None
        arm = ob if is_dw2_armature(ob) else (
            ob.parent if ob is not None and is_dw2_armature(ob.parent) else None)
        names = selected_parts(arm) if arm is not None else []
        key = (arm.name if arm is not None else None, tuple(names))
        if key != _preview_state["key"]:
            _preview_state["key"] = key
            build_preview(arm, names, sc.collection)
    except Exception as ex:                      # never leave a broken timer running
        print("[DW2] preview:", ex)
        return None
    return 0.25


def _preview_toggle(self, context):
    _preview_state["key"] = None
    if self.dw2_preview:
        if not bpy.app.timers.is_registered(_preview_tick):
            bpy.app.timers.register(_preview_tick, first_interval=0.05)
    else:
        clear_preview()


def duplicate_digimon():
    """{name: [armature objects]} for Digimon imported more than once."""
    seen = {}
    for o in bpy.data.objects:
        if is_dw2_armature(o) and o.users_scene:
            seen.setdefault(o.get("dw2_name", o.name), []).append(o.name)
    return {k: v for k, v in seen.items() if len(v) > 1}


def draw_props(box, arm, context):
    p = arm.dw2
    sub = box
    sub.label(text="Digimon number %d%s" % (int(arm.get("dw2_digimon", 0)),
                                             " (new)" if arm.get("dw2_new") else ""), icon="OUTLINER_OB_ARMATURE")
    sub.prop(p, "name")
    if not arm.get("dw2_base_raw"):
        sub.label(text="No base data: unzip dw2_data.zip into the data folder", icon="INFO")
        return
    row = sub.row(align=True)
    row.prop(p, "dtype", text="")
    row.prop(p, "rank", text="")
    row.prop(p, "specialty", text="")
    col = sub.column(align=True)
    col.label(text="Growth per level (0..15):")
    for i, nm in enumerate(("HP", "MP", "Attack", "Defense", "Speed")):
        col.prop(p, "growth", index=i, text=nm)
    ch = choices(context)
    tid = get_technique(arm)
    row = sub.row(align=True)
    row.label(text="Technique: " + (ch["tech_names"].get(tid, "#%d" % tid) if tid else "(none)"))
    if ch.get("have_techs"):
        op = row.operator("dw2.pick", text="Change", icon="VIEWZOOM")
        op.which = "technique"
    else:
        sub.label(text="To change it, the data folder needs 025B.bin", icon="ERROR")
        sub.label(text="from dw2_data.zip (extract_models --data)")
    sub.prop(p, "dna")
    col = sub.column(align=True)
    col.label(text="Digivolves into (by DP):")
    for i in range(4):
        t = get_evo(arm, i)
        row = col.row(align=True)
        op = row.operator("dw2.pick", text=ch["digi_names"].get(t, "#%d" % t) if t else "(none)", icon="VIEWZOOM")
        op.which = "evo%d" % i
        if t:
            row.prop(p, "evo%d_dp" % i, text="from")
        else:
            break
    sub.operator("dw2.save_new_digimon", icon="DUPLICATE")
    sub.label(text="Export saves name and stats too.", icon="INFO")


class _DW2Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DW2"


class DW2_PT_panel(_DW2Panel, bpy.types.Panel):
    """Folders, import and export: always at the top, so they're never off screen."""
    bl_label = "Digimon World 2"

    def draw(self, context):
        lay = self.layout
        sc = context.scene
        fp = forbs_paths()
        col = lay.column(align=True)
        if fp["data"] and not sc.dw2_data_dir and not sc.dw2_mods_dir:
            col.label(text="Using your forbs-hidden-mods folder", icon="CHECKMARK")
            col.label(text=os.path.dirname(fp["mods"].rstrip("/\\")))
            col.label(text="(fill a box below to use another folder)")
        col.label(text="Data folder (game data):")
        col.prop(sc, "dw2_data_dir", text="")
        col.label(text="Game mods folder:")
        col.prop(sc, "dw2_mods_dir", text="")
        if fp["data"] and (sc.dw2_data_dir or sc.dw2_mods_dir):
            col.operator("dw2.use_forbs_folders", icon="FILE_REFRESH")
        row = lay.row(align=True)
        row.operator("dw2.import_digimon", icon="IMPORT")
        row.operator("dw2.export_digimon", icon="EXPORT", text="Export")
        for nm, objs in duplicate_digimon().items():
            warn = lay.box()
            warn.alert = True
            warn.label(text="%s is in the scene %d times:" % (nm, len(objs)), icon="ERROR")
            warn.label(text=", ".join(objs))
            warn.label(text="Delete the copies you are not using")


def _current(context):
    arm = find_armature(context)
    return arm if arm is not None and "dw2_meta" in arm else None


class DW2_PT_digimon(_DW2Panel, bpy.types.Panel):
    bl_label = "Selected Digimon"
    bl_parent_id = "DW2_PT_panel"

    def draw(self, context):
        lay = self.layout
        arm = _current(context)
        if arm is None:
            lay.label(text="Select an imported Digimon")
            return
        lay.label(text="%s (model %04X)" % (arm.get("dw2_name", arm.name), int(arm["dw2_model"])),
                  icon="OUTLINER_OB_ARMATURE")
        ad = arm.animation_data
        if ad is not None:
            lay.prop(ad, "action", text="Animation")
            act = ad.action
            if act is not None and "dw2_slot" in act:
                row = lay.row()
                row.label(text="slot %d, #%d" % (act["dw2_slot"], act["dw2_index"]))
                row.prop(act, '["dw2_loop_to"]', text="Loop to")
        lay.operator("dw2.check_digimon", icon="CHECKMARK")


class DW2_PT_stats(_DW2Panel, bpy.types.Panel):
    bl_label = "Name, stats and digivolution"
    bl_parent_id = "DW2_PT_panel"

    def draw(self, context):
        arm = _current(context)
        if arm is None:
            self.layout.label(text="Select an imported Digimon")
            return
        draw_props(self.layout, arm, context)


class DW2_PT_parts(_DW2Panel, bpy.types.Panel):
    bl_label = "Take parts from another Digimon"
    bl_parent_id = "DW2_PT_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        box = self.layout
        sc = context.scene
        arm = find_armature(context)
        donor = arm if is_dw2_armature(arm) else None
        if donor is not None:
            picked = selected_parts(donor)
            box.label(text="From %s: %d bone%s selected" % (donor.get("dw2_name", donor.name), len(picked),
                                                               "" if len(picked) == 1 else "s"))
        else:
            box.label(text="Select the Digimon to take parts from")
        box.prop(sc, "dw2_preview", text="Preview selected parts (orange)")
        box.prop(sc, "dw2_target", text="Add to")
        if sc.dw2_target is not None and sc.dw2_target.name not in sc.objects:
            row = box.row()
            row.alert = True
            row.label(text="Not in the scene any more: pick it again", icon="ERROR")
        if is_dw2_armature(sc.dw2_target):
            box.prop_search(sc, "dw2_attach", sc.dw2_target.data, "bones", text="Attach to")
        box.prop(sc, "dw2_parts_motion", text="Motion")
        box.operator("dw2.add_parts", icon="ADD")
        act_ob = context.active_object
        if act_ob is not None and "dw2_parts" in act_ob:
            sub = box.box()
            sub.label(text="Place %s:" % act_ob.name)
            sub.label(text="move / turn / scale it (G, R, S), then")
            sub.operator("dw2.apply_parts", icon="CHECKMARK")


classes = (DW2DigiProps, DW2_OT_pick, DW2_OT_use_forbs_folders, DW2_OT_save_new, DW2_OT_import, DW2_OT_export, DW2_OT_check, DW2_OT_add_parts, DW2_OT_apply_parts,
           DW2_PT_panel, DW2_PT_digimon, DW2_PT_stats, DW2_PT_parts)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.dw2_data_dir = bpy.props.StringProperty(name="DW2 data folder", subtype="DIR_PATH")
    bpy.types.Scene.dw2_mods_dir = bpy.props.StringProperty(name="DW2 mods folder", subtype="DIR_PATH")
    bpy.types.Scene.dw2_target = bpy.props.PointerProperty(
        name="Add to", type=bpy.types.Object, poll=_target_poll,
        description="The Digimon that gets the parts")
    bpy.types.Scene.dw2_attach = bpy.props.StringProperty(
        name="Attach to", description="Its bone the parts hang from (empty: its chest or body)")
    bpy.types.Scene.dw2_parts_motion = bpy.props.EnumProperty(
        name="Motion", items=[("LOOP", "Copy their motion", "Loop the parts' movement from the donor's current "
                               "animation through every animation of the target"),
                              ("STILL", "Keep still", "The parts hold still (pose them yourself)")],
        default="LOOP")
    bpy.types.Object.dw2 = bpy.props.PointerProperty(type=DW2DigiProps)
    bpy.types.Scene.dw2_preview = bpy.props.BoolProperty(
        name="Preview selected parts", default=False, update=_preview_toggle,
        description="Show the parts of the selected bones in orange, in front of everything")


def unregister():
    if bpy.app.timers.is_registered(_preview_tick):
        bpy.app.timers.unregister(_preview_tick)
    try:
        clear_preview()
    except Exception:
        pass
    del bpy.types.Scene.dw2_preview
    del bpy.types.Object.dw2
    del bpy.types.Scene.dw2_parts_motion
    del bpy.types.Scene.dw2_attach
    del bpy.types.Scene.dw2_target
    del bpy.types.Scene.dw2_mods_dir
    del bpy.types.Scene.dw2_data_dir
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
