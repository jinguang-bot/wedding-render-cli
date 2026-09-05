#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_overlay.py — 重建 overlay 增量层（架构v2 L2）
用法：blender -b -P layout.py -- layouts/wedding.vN.json   # 先建 base
      blender -b -P apply_overlay.py -- layouts/wedding.vN.overlay.json [--render-tag wedding.vN]

按 snapshot.py 导出的 overlay.json 重建 agent/MCP 新增的物体与相机。
（也可在同一 bpy 会话里被 import 调用：apply("path")）
"""
import bpy
import json
import math
import os
import sys

PALETTE_FALLBACK = {
    "white_cloth": (0.96, 0.96, 0.96, 1.0), "greenery": (0.30, 0.58, 0.38, 1.0),
    "warm_light": (1.00, 0.82, 0.45, 1.0), "wood": (0.55, 0.40, 0.25, 1.0),
    "floor_light": (0.85, 0.80, 0.70, 1.0), "glass": (0.80, 0.90, 1.00, 1.0),
    "iron": (0.25, 0.25, 0.28, 1.0), "petal": (0.99, 0.93, 0.95, 1.0),
    "chapel_wall": (0.88, 0.86, 0.82, 1.0), "lawn": (0.42, 0.62, 0.30, 1.0),
    "sea": (0.35, 0.55, 0.70, 1.0), "tablecloth": (0.93, 0.91, 0.87, 1.0),
    "monet_lavender": (0.78, 0.70, 0.85, 1.0),
}


def _mat(name):
    key = "SEM_" + name
    m = bpy.data.materials.get(key)
    if m:
        return m
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    color = PALETTE_FALLBACK.get(name, (0.8, 0.8, 0.8, 1.0))
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        if name == "warm_light":
            bsdf.inputs["Emission Strength"].default_value = 5.0
            bsdf.inputs["Emission Color"].default_value = color
    return m


def apply(overlay_path):
    with open(overlay_path, encoding="utf-8") as f:
        ov = json.load(f)
    n = 0
    for rec in ov.get("objects", []):
        t, dim = rec["type"], rec.get("dimensions", [1, 1, 1])
        loc, rot = rec["location"], rec.get("rotation", [0, 0, 0])
        rot_rad = [math.radians(v) for v in rot]
        if t == "sphere":
            r = max(dim) / 2
            bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, rotation=rot_rad)
        elif t == "cylinder":
            r = max(dim[0], dim[1]) / 2
            bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=dim[2], location=loc, rotation=rot_rad)
        else:
            bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot_rad)
            bpy.context.active_object.scale = [v / 2 for v in dim]
        o = bpy.context.active_object
        o.name = rec["name"]
        if rec.get("material"):
            o.data.materials.append(_mat(rec["material"]))
        n += 1
    for rec in ov.get("cameras", []):
        cam_data = bpy.data.cameras.new("cam_ov_" + rec["name"])
        cam_data.lens = rec.get("lens", 28)
        cam = bpy.data.objects.new("camera_" + rec["name"], cam_data)
        bpy.context.collection.objects.link(cam)
        cam.location = rec["location"]
        cam.rotation_euler = [math.radians(v) for v in rec["rotation"]]
    return n


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not args:
        sys.exit("用法: blender -b -P apply_overlay.py -- <overlay.json>")
    with open(args[0], encoding="utf-8") as f:
        ov = json.load(f)
    n = apply(args[0])
    print("[apply_overlay] 重建物体 %d 个，相机 %d 个" % (n, len(ov.get("cameras", []))))


if __name__ == "__main__":
    main()
