#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
layout.py — 通用场景骨架渲染器（Blender headless，领域无关）
用法：blender -b -P layout.py -- layouts/scene.vN.json [--quick] [--samples N] [--camera NAME]

通用场景 JSON（单一事实源，领域无关）：
{
  "time": "day|dusk|night",
  "ground": {"size": [24, 24], "material": "lawn|floor_light|..."},
  "backdrop": {"sea": true},                      # 可选：远处海面
  "objects": [                                    # 通用图元（与 snapshot.py 导出格式一致）
    {"name": "...", "type": "box|sphere|cylinder",
     "size": [x,y,z], "location": [x,y,z], "rotation": [deg,...], "material": "..."}
  ],
  "cameras": ["front", "side45", "top", "wide"]   # 预设名（按场地边界自适应摆放）
}

骨架只做空间关系与材质色块语义；细节由照片级化阶段完成。
具体场地的定制构建器放本地 domain pack（不随通用工具分发），可通过
rebuild_runner 的 builder_module 引用。
"""
import bpy
import json
import math
import os
import sys
from mathutils import Vector

# ---------------- 材质色板（通用材质语义；工作区 palette.json 可扩展） ----------------
PALETTE = {
    "white_fabric": (0.96, 0.96, 0.96, 1.0),
    "greenery":     (0.30, 0.58, 0.38, 1.0),
    "warm_light":   (1.00, 0.82, 0.45, 1.0),
    "wood":         (0.55, 0.40, 0.25, 1.0),
    "wood_dark":    (0.18, 0.11, 0.07, 1.0),
    "wood_deck":    (0.35, 0.24, 0.15, 1.0),
    "floor_light":  (0.85, 0.80, 0.70, 1.0),
    "stone":        (0.70, 0.68, 0.63, 1.0),
    "glass":        (0.80, 0.90, 1.00, 1.0),
    "metal_black":  (0.07, 0.07, 0.08, 1.0),
    "metal":        (0.55, 0.55, 0.58, 1.0),
    "fabric_red":   (0.60, 0.15, 0.12, 1.0),
    "paint_white":  (0.92, 0.90, 0.86, 1.0),
    "paint_cream":  (0.88, 0.85, 0.78, 1.0),
    "lawn":         (0.42, 0.62, 0.30, 1.0),
    "sea":          (0.35, 0.55, 0.70, 1.0),
    "stained_green": (0.20, 0.50, 0.30, 1.0),
    "stained_red":   (0.60, 0.20, 0.15, 1.0),
    "stained_blue":  (0.20, 0.35, 0.60, 1.0),
    "stained_amber": (0.70, 0.50, 0.15, 1.0),
}

MATERIALS = {}

def mat(name):
    if name not in MATERIALS:
        m = bpy.data.materials.new("SEM_" + name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        color = PALETTE.get(name, (0.8, 0.8, 0.8, 1.0))
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color
            if name == "warm_light":
                bsdf.inputs["Emission Strength"].default_value = 5.0
                bsdf.inputs["Emission Color"].default_value = color
            if name == "glass":
                bsdf.inputs["Alpha"].default_value = 0.35
            if name.startswith("stained_"):
                bsdf.inputs["Alpha"].default_value = 0.8
        MATERIALS[name] = m
    return MATERIALS[name]

# ---------------- 基础几何工具 ----------------

def clear_scene():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for item in list(coll):
            if item.users == 0:
                coll.remove(item)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

def box(name, size, location, material, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    o.scale = [s / 2 for s in size]
    o.data.materials.append(mat(material))
    return o

def cylinder(name, radius, depth, location, material, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat(material))
    return o

def sphere(name, radius, location, material):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat(material))
    return o

def plane(name, size, location, material):
    bpy.ops.mesh.primitive_plane_add(size=1, location=location)
    o = bpy.context.active_object
    o.name = name
    o.scale = [size[0] / 2, size[1] / 2, 1]
    o.data.materials.append(mat(material))
    return o

def seg_between(name, p1, p2, radius, material):
    p1, p2 = Vector(p1), Vector(p2)
    mid = (p1 + p2) / 2
    d = p2 - p1
    o = cylinder(name, radius, d.length, mid, material)
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = d.to_track_quat('Z', 'Y')
    return o

def tri_prism(name, width, height, depth, location, material):
    import bmesh
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    v = [bm.verts.new(p) for p in (
        (-width / 2, 0, 0), (width / 2, 0, 0), (0, 0, height),
        (-width / 2, depth, 0), (width / 2, depth, 0), (0, depth, height))]
    bm.faces.new([v[0], v[1], v[2]])
    bm.faces.new([v[4], v[3], v[5]])
    bm.faces.new([v[0], v[1], v[4], v[3]])
    bm.faces.new([v[1], v[2], v[5], v[4]])
    bm.faces.new([v[2], v[0], v[3], v[5]])
    bm.to_mesh(mesh)
    bm.free()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    o.location = location
    o.data.materials.append(mat(material))
    return o

# ---------------- 通用场景构建 ----------------

def build_ground(ground_cfg, backdrop=None):
    g = ground_cfg or {}
    sx, sy = g.get("size", [24, 24])
    plane("ground", (sx, sy), (0, 0, 0), g.get("material", "lawn"))
    if backdrop and backdrop.get("sea"):
        plane("sea", (max(sx * 3, 200), 60), (0, sy / 2 + 30, -0.2), "sea")
    return sx, sy


def build_objects(objects):
    """通用图元批量构建（与 snapshot.py 导出格式一致）"""
    n = 0
    for rec in objects or []:
        t = rec.get("type", "box")
        loc = rec.get("location", [0, 0, 0])
        rot = [math.radians(v) for v in rec.get("rotation", [0, 0, 0])]
        dim = rec.get("size", rec.get("dimensions", [1, 1, 1]))
        if t == "sphere":
            bpy.ops.mesh.primitive_uv_sphere_add(radius=max(dim) / 2, location=loc, rotation=rot)
        elif t == "cylinder":
            bpy.ops.mesh.primitive_cylinder_add(radius=max(dim[0], dim[1]) / 2, depth=dim[2],
                                                location=loc, rotation=rot)
        else:
            bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
            bpy.context.active_object.scale = [v / 2 for v in dim]
        o = bpy.context.active_object
        o.name = rec.get("name", "obj_%d" % n)
        if rec.get("material"):
            o.data.materials.append(mat(rec["material"]))
        n += 1
    return n

# ---------------- 灯光与机位（按场景边界自适应） ----------------

def build_lighting(time_of_day):
    bpy.ops.object.light_add(type='SUN', location=(10, -8, 20))
    sun = bpy.context.active_object
    if time_of_day == "night":
        sun.data.energy = 0.3
        sun.data.color = (0.7, 0.75, 1.0)
        bpy.context.scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.03, 0.08, 1)
    elif time_of_day == "dusk":
        sun.data.energy = 1.2
        sun.data.color = (1.0, 0.75, 0.55)
        sun.rotation_euler = (math.radians(80), 0, math.radians(-35))
        bpy.context.scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.25, 0.28, 1)
    else:  # day
        sun.data.energy = 3.0
        sun.rotation_euler = (math.radians(55), 0, math.radians(-30))
        bpy.context.scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.7, 0.9, 1)


def look_at(cam_obj, target):
    d = Vector(target) - cam_obj.location
    cam_obj.rotation_mode = 'QUATERNION'
    cam_obj.rotation_quaternion = d.to_track_quat('-Z', 'Y')


def scene_bounds(default_size=(24, 24)):
    xs, ys, zs = [], [], []
    for o in bpy.data.objects:
        if o.type != 'MESH':
            continue
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
    if not xs:
        xs = [-default_size[0] / 2, default_size[0] / 2]
        ys = [-default_size[1] / 2, default_size[1] / 2]
        zs = [0, 3]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def camera_preset(name, cfg):
    (x0, x1), (y0, y1), (z0, z1) = scene_bounds(
        (cfg.get("ground", {}) or {}).get("size", [24, 24]))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = max(x1 - x0, 4), max(y1 - y0, 4)
    ext = max(dx, dy)
    h = max(z1, 2.0)
    presets = {
        "front":   ((cx, y0 - ext * 1.1, h * 0.55), (cx, cy, h * 0.35), 35),
        "back":    ((cx, y1 + ext * 1.1, h * 0.55), (cx, cy, h * 0.35), 35),
        "side45":  ((x0 - ext * 0.8, y0 - ext * 0.8, h * 0.7), (cx, cy, h * 0.35), 35),
        "top":     ((cx, cy - 0.01, h + ext * 1.2), (cx, cy + 0.01, 0), 40),
        "wide":    ((cx - ext, y0 - ext * 1.3, h + ext * 0.8), (cx, cy, 1.0), 35),
    }
    if name in presets:
        p = presets[name]
        return (p[0], p[1]), p[2]
    explicit = (cfg.get("cameras_explicit") or {}).get(name)
    if explicit:
        return (explicit.get("location"), explicit.get("look_at", (0, 0, 1))), explicit.get("lens", 35)
    return None


def render_cameras(names, out_dir, tag, quick=False, cfg=None):
    scene = bpy.context.scene
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "CYCLES"):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            continue
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = globals().get("SAMPLES_OVERRIDE", 16 if quick else 96)
    scene.render.resolution_x, scene.render.resolution_y = (1280, 720) if quick else (1920, 1080)
    cfg = cfg or {}
    for name in names:
        preset = camera_preset(name, cfg)
        if preset is None:
            print("[warn] 未知机位 %s，跳过" % name)
            continue
        (pos, target), lens = preset
        cam_data = bpy.data.cameras.new("cam_" + name)
        cam_data.lens = lens
        cam = bpy.data.objects.new("camera_" + name, cam_data)
        bpy.context.collection.objects.link(cam)
        cam.location = Vector(pos)
        look_at(cam, target)
        scene.camera = cam
        out = os.path.join(out_dir, "%s_%s.png" % (tag, name))
        scene.render.filepath = out
        bpy.ops.render.render(write_still=True)
        print("[render]", out)

# ---------------- 主流程 ----------------

def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    layout_path = "layouts/scene.v0.json"
    quick = False
    cameras_override = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--quick":
            quick = True
        elif a == "--samples":
            globals()["SAMPLES_OVERRIDE"] = int(args[i + 1]); i += 1
        elif a == "--camera":
            cameras_override.append(args[i + 1]); i += 1
        elif not a.startswith("--"):
            layout_path = a
        i += 1
    with open(layout_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    ws = os.path.dirname(os.path.dirname(os.path.abspath(layout_path)))
    out_dir = os.path.join(ws, "renders")
    os.makedirs(out_dir, exist_ok=True)

    clear_scene()
    build_ground(cfg.get("ground"), cfg.get("backdrop"))
    n = build_objects(cfg.get("objects"))
    build_lighting(cfg.get("time", "day"))
    cams = cameras_override or cfg.get("cameras", ["front", "side45", "wide"])
    print("[scene] objects=%d cameras=%s" % (n, cams))
    render_cameras(cams, out_dir,
                   os.path.splitext(os.path.basename(layout_path))[0], quick=quick, cfg=cfg)
    print("[done] %s renders in %s" % ("QUICK" if quick else "FULL", out_dir))

if __name__ == "__main__":
    main()
