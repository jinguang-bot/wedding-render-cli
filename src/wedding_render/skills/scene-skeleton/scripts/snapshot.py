#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snapshot.py — 场景状态快照（架构v2 L2/L3 层）
用法：blender -b -P snapshot.py -- --base layouts/wedding.vN.json \
        --out layouts/wedding.vN.overlay.json --blend sessions/wedding.vN.blend [--render-tag X]

把当前 Blender 场景中 **不属于 base 模板** 的物体（agent/MCP 新增的）导出为
overlay.json（图元类型/尺寸/位置/旋转/材质语义/相机），并保存完整 .blend 会话。
之后任何 agent 可用 layout.py(base) + apply_overlay.py(overlay) 重建场景。
"""
import bpy
import json
import math
import os
import sys

# 与 layout.py 一致的图元判定：按名称前缀归类型
BASE_PREFIXES = (
    "chapel_", "wall_", "win_", "sea_", "ent_", "roof_", "beam_", "ridge_",
    "seat_", "backrest_", "aisle_", "arch_", "sign_", "table_", "dchair_",
    "light_pole", "wire_", "bulb_", "dessert_", "fence_", "stone_path",
    "porch_", "shrub", "lawn", "sea", "cam_", "Sun", "lamp_petal",
    # replica 级礼堂确定性底座件（v6）
    "skirt_", "sglass_", "post_", "spring_", "sconce_", "stained_",
    "gbl_", "foldoor_", "col_white_", "chand_", "door_", "ent_",
    "terrace_", "sea_curtain", "sea_muntin", "sea_lintel", "sea_pier",
    "wchair_", "platform_", "gazebo_", "palm_", "path_", "beach",
    "site_lawn", "hedge_",
)


def obj_type(o):
    if o.type == "CAMERA":
        return "camera"
    if o.type != "MESH":
        return "other"
    dims = o.dimensions
    if abs(dims.x - dims.y) < 1e-4 and abs(dims.y - dims.z) < 1e-4:
        return "sphere"
    return "box"


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    base = out = blend = None
    i = 0
    while i < len(args):
        if args[i] == "--base":
            base = args[i + 1]; i += 2
        elif args[i] == "--out":
            out = args[i + 1]; i += 2
        elif args[i] == "--blend":
            blend = args[i + 1]; i += 2
        else:
            i += 1

    objects, cameras = [], []
    for o in bpy.data.objects:
        if o.name.startswith(BASE_PREFIXES) or o.type in ("LIGHT", "EMPTY"):
            continue  # base 模板件/Light 由 base JSON 重建
        mat_name = ""
        if o.data.materials:
            mat_name = o.data.materials[0].name.replace("SEM_", "")
        rec = {
            "name": o.name,
            "type": obj_type(o),
            "location": [round(v, 4) for v in o.location],
            "rotation": [round(math.degrees(v), 2) for v in o.rotation_euler],
            "dimensions": [round(v, 4) for v in o.dimensions],
            "material": mat_name,
        }
        if o.type == "CAMERA":
            d = o.rotation_quaternion.to_euler()
            rec["rotation"] = [round(math.degrees(v), 2) for v in d]
            rec["lens"] = round(o.data.lens, 1)
            # 视线目标点（location + 朝向前方 10m）
            import mathutils
            fwd = o.matrix_world.to_quaternion() @ mathutils.Vector((0, 0, -10))
            tgt = o.location + fwd
            rec["look_at"] = [round(v, 3) for v in tgt]
            cameras.append(rec)
        else:
            objects.append(rec)

    overlay = {
        "base": base,
        "objects": objects,
        "cameras": cameras,
        "counts": {"objects": len(objects), "cameras": len(cameras)},
        "note": "snapshot.py 生成；base 件未含（由 base JSON 重建）；完整保真见 blend 会话文件",
    }
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(overlay, f, ensure_ascii=False, indent=2)
    if blend:
        os.makedirs(os.path.dirname(os.path.abspath(blend)), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(blend))
    print("[snapshot] objects=%d cameras=%d -> %s" % (len(objects), len(cameras), out or "(未写文件)"))
    if blend:
        print("[snapshot] session ->", blend)


if __name__ == "__main__":
    main()
