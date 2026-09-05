#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
layout.py — 婚礼场地骨架渲染器（Blender headless）
用法：blender -b -P layout.py -- layouts/wedding.v0.json [--quick] [--camera X ...]

设计：读取 layout JSON（单一事实源），搭建礼堂（参数化精确建模：侧墙窗洞/海侧
大开口/双坡顶露梁/三角山墙）+ 草坪晚宴代理几何（材质色块语义），按机位渲染。
骨架只求空间关系正确，细节由照片级化阶段（photoreal-render 技能）完成。
礼堂测量共识（2026-08-25，5 张实拍交叉验证）：内部宽 8.2m、纵深 13.5m、
侧墙高 4.6m、脊高 +1.8m、每侧 5 扇拱窗 1.4×2.8m（台高 1.0）、海侧大开口 4×3m。
坐标系：Y+ 为海侧（尽头大开口），Y- 为入口端（双开门+三角山花采光）。
"""
import bpy
import json
import math
import os
import sys
from mathutils import Vector

# ---------------- 材质色块语义（与 references/semantic_palette.md 一一对应） ----------------
PALETTE = {
    "white_cloth":  (0.96, 0.96, 0.96, 1.0),   # 纱幔/白花
    "greenery":     (0.30, 0.58, 0.38, 1.0),   # 叶材/花植
    "warm_light":   (1.00, 0.82, 0.45, 1.0),   # 灯串/烛光（自发光）
    "wood":         (0.55, 0.40, 0.25, 1.0),   # 深色木（横梁/门/家具）
    "floor_light":  (0.85, 0.80, 0.70, 1.0),   # 浅色石材地面
    "glass":        (0.80, 0.90, 1.00, 1.0),   # 玻璃（半透明）
    "iron":         (0.25, 0.25, 0.28, 1.0),   # 铁艺结构
    "petal":        (0.99, 0.93, 0.95, 1.0),   # 花瓣/地毯
    "monet_lavender": (0.78, 0.70, 0.85, 1.0),  # 莫奈雾紫（睡莲/鸢尾色系）
    "wood_dark":    (0.18, 0.11, 0.07, 1.0),
    "wood_honey":   (0.66, 0.46, 0.26, 1.0),   # 蜂蜜色实木椅   # 深胡桃木（结构/吊顶/栅栏）
    "wood_deck":    (0.35, 0.24, 0.15, 1.0),   # 户外木平台
    "column_white": (0.93, 0.91, 0.87, 1.0),   # 白色圆柱
    "iron_black":   (0.07, 0.07, 0.08, 1.0),   # 黑铁（吊灯/棂条）
    "candle":       (0.95, 0.92, 0.85, 1.0),   # 蜡烛
    "stained_green": (0.20, 0.50, 0.30, 1.0),  # 彩玻-绿
    "stained_red":   (0.60, 0.20, 0.15, 1.0),  # 彩玻-红
    "stained_blue":  (0.20, 0.35, 0.60, 1.0),  # 彩玻-蓝
    "stained_amber": (0.70, 0.50, 0.15, 1.0),  # 彩玻-琥珀
    "chapel_wall":  (0.88, 0.86, 0.82, 1.0),   # 礼堂米白墙面
    "lawn":         (0.42, 0.62, 0.30, 1.0),   # 草坪
    "sea":          (0.35, 0.55, 0.70, 1.0),   # 海面
    "tablecloth":   (0.93, 0.91, 0.87, 1.0),   # 桌布
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
                bsdf.inputs["Alpha"].default_value = 0.15
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
    """两点之间放一根圆柱（灯串挂线用）"""
    p1, p2 = Vector(p1), Vector(p2)
    mid = (p1 + p2) / 2
    d = p2 - p1
    o = cylinder(name, radius, d.length, mid, material)
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = d.to_track_quat('Z', 'Y')
    return o

def tri_prism(name, width, height, depth, location, material):
    """三角形棱柱（山墙/三角楣）：底边沿 X，高沿 Z，深度沿 Y"""
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

# ---------------- 场地：礼堂（参数化精确建模） + 草坪 + 海 ----------------

DEFAULT_CHAPEL = {
    "length": 13.5, "width": 8.2, "wall_h": 4.6, "roof_rise": 1.8, "beams": 5,
    "windows": {"count": 5, "w": 1.4, "h": 2.8, "sill": 1.0},
    "sea_opening": {"w": 4.0, "h": 3.0},
    "entrance": {"door_w": 2.4, "door_h": 2.6, "side_win": {"w": 1.0, "h": 2.0, "sill": 1.0}},
}


def build_venue(cfg):
    """返回 (L, W)。礼堂沿 Y 轴：Y+ 海侧大开口，Y- 入口双开门。"""
    plane("lawn", (80, 60), (0, 0, 0), "lawn")
    plane("sea", (200, 60), (0, 45, -0.2), "sea")

    ch = dict(DEFAULT_CHAPEL)
    ch.update(cfg.get("chapel", {}))
    L, W, H, rise = ch["length"], ch["width"], ch["wall_h"], ch["roof_rise"]
    if ch.get("replica"):
        return build_replica_chapel(ch, L, W, H, rise)
    t = 0.25  # 墙厚

    box("chapel_floor", (W, L, 0.2), (0, 0, 0.1), "floor_light")

    # ---- 两侧墙（窗洞拼墙：下带全长 + 窗间段 + 上带全长 + 玻璃） ----
    win = ch["windows"]
    n, ww, wh, sill = win["count"], win["w"], win["h"], win["sill"]
    pad = (L - n * ww) / (n + 1)
    centers = [-L / 2 + pad * (i + 1) + ww * (i + 0.5) for i in range(n)]
    for side, sx in (("L", -W / 2), ("R", W / 2)):
        box("wall_%s_low" % side, (t, L, sill), (sx, 0, sill / 2), "chapel_wall")
        top0 = sill + wh
        box("wall_%s_top" % side, (t, L, H - top0), (sx, 0, top0 + (H - top0) / 2), "chapel_wall")
        prev = -L / 2
        for ci, c in enumerate(centers):
            a, b = prev, c - ww / 2
            if b - a > 0.05:
                box("wall_%s_mid_%d" % (side, ci), (t, b - a, wh),
                    (sx, (a + b) / 2, sill + wh / 2), "chapel_wall")
            prev = c + ww / 2
        if L / 2 - prev > 0.05:
            box("wall_%s_end" % side, (t, L / 2 - prev, wh),
                (sx, (prev + L / 2) / 2, sill + wh / 2), "chapel_wall")
        for ci, c in enumerate(centers):
            box("win_%s_%d" % (side, ci), (0.06, ww, wh), (sx, c, sill + wh / 2), "glass")
            box("win_%s_%d_sill" % (side, ci), (t + 0.12, ww + 0.12, 0.08),
                (sx, c, sill), "floor_light")

    # ---- 海侧尽头墙（Y=+L/2）：两侧实体 + 顶部横带 + 大开口玻璃 + 三角山墙采光 ----
    so = ch["sea_opening"]
    sw, sh = so["w"], so["h"]
    side_w = (W - sw) / 2
    for k, sx in enumerate((-(sw / 2 + side_w / 2), (sw / 2 + side_w / 2))):
        box("sea_wall_%d" % k, (side_w, t, H), (sx, L / 2 - t / 2, H / 2), "chapel_wall")
    box("sea_lintel", (W, t, H - sh), (0, L / 2 - t / 2, sh + (H - sh) / 2), "chapel_wall")
    box("sea_glass", (sw, 0.06, sh), (0, L / 2 - t / 2, sh / 2), "glass")
    box("sea_open_frame", (sw + 0.3, t + 0.1, 0.18), (0, L / 2 - t / 2, sh), "wood")
    tri_prism("sea_gable", W, rise, t, (0, L / 2 - t, H), "chapel_wall")
    tri_prism("sea_gable_glass", W - 1.2, rise - 0.5, 0.06,
              (0, L / 2 - t + 0.05, H + 0.2), "glass")

    # ---- 入口端墙（Y=-L/2）：双开门 + 两侧小窗 + 三角山花采光 ----
    en = ch["entrance"]
    dw, dh = en["door_w"], en["door_h"]
    swn = en["side_win"]
    e_side = (W - dw) / 2
    for k, sx in enumerate((-(dw / 2 + e_side / 2), (dw / 2 + e_side / 2))):
        box("ent_wall_%d" % k, (e_side, t, H), (sx, -L / 2 + t / 2, H / 2), "chapel_wall")
        box("ent_win_%d" % k, (swn["w"], 0.06, swn["h"]),
            (sx, -L / 2 + t / 2, swn["sill"] + swn["h"] / 2), "glass")
    box("ent_lintel", (W, t, H - dh), (0, -L / 2 + t / 2, dh + (H - dh) / 2), "chapel_wall")
    box("ent_door_leaf_L", (dw / 2 - 0.04, 0.08, dh - 0.1),
        (-dw / 4, -L / 2 + t / 2, (dh - 0.1) / 2), "wood")
    box("ent_door_leaf_R", (dw / 2 - 0.04, 0.08, dh - 0.1),
        (dw / 4, -L / 2 + t / 2, (dh - 0.1) / 2), "wood")
    box("ent_frame", (dw + 0.25, t + 0.1, 0.15), (0, -L / 2 + t / 2, dh), "wood")
    tri_prism("ent_gable", W, rise, t, (0, -L / 2, H), "chapel_wall")
    tri_prism("ent_gable_glass", W - 1.2, rise - 0.5, 0.06,
              (0, -L / 2 + 0.05, H + 0.2), "glass")

    # ---- 双坡屋顶内面（两块斜板）+ 露明横梁 + 脊梁 ----
    slope = math.hypot(W / 2, rise) + 0.15
    ang = math.atan2(rise, W / 2)
    box("roof_L", (slope, L, 0.1), (-W / 4, 0, H + rise / 2), "chapel_wall",
        rotation=(0, -ang, 0))
    box("roof_R", (slope, L, 0.1), (W / 4, 0, H + rise / 2), "chapel_wall",
        rotation=(0, ang, 0))
    nb = ch["beams"]
    for bi in range(nb):
        by = -L / 2 + 1.0 + bi * ((L - 2.0) / max(nb - 1, 1))
        box("beam_%d" % bi, (W - 0.3, 0.22, 0.26), (0, by, H - 0.16), "wood")
    box("ridge_beam", (0.2, L, 0.22), (0, 0, H + rise - 0.13), "wood")
    return L, W

# ---------------- 礼堂外部（栅栏/步道/门廊/绿植） ----------------

DEFAULT_EXTERIOR = {
    "fence": {"enabled": True, "height": 1.2, "offset": 7.0, "side": 11.0, "gate_w": 2.4},
    "path": {"enabled": True, "width": 2.4},
    "porch": {"enabled": True, "depth": 2.0, "height": 3.1},
    "shrubs": {"enabled": True},
}


def fence_run(name, p1, p2, h):
    """一段木栅栏：两根横轨 + 竖条（深棕木）"""
    p1, p2 = Vector(p1), Vector(p2)
    length = (p2 - p1).length
    seg_between(name + "_rail_low", tuple(p1) + (h * 0.45,), tuple(p2) + (h * 0.45,), 0.035, "wood")
    seg_between(name + "_rail_top", tuple(p1) + (h * 0.95,), tuple(p2) + (h * 0.95,), 0.035, "wood")
    d = (p2 - p1).normalized()
    n = max(int(length / 0.4), 2)
    for i in range(n + 1):
        c = p1 + d * (length * i / n)
        box("%s_post_%d" % (name, i), (0.07, 0.07, h), (c.x, c.y, h / 2), "wood")


def _picket_fence(name, p1, p2, h):
    """尖顶木桩栅栏（照片21实证：密排尖头立柱 + 双横轨）"""
    p1, p2 = Vector(p1), Vector(p2)
    length = (p2 - p1).length
    d = (p2 - p1).normalized()
    for zz in (h * 0.35, h * 0.78):
        seg_between(name + "_rail_%d" % int(zz * 100), tuple(p1) + (zz,), tuple(p2) + (zz,), 0.03, "wood_dark")
    gap = 0.15
    n = max(int(length / gap), 2)
    for i in range(n + 1):
        c = p1 + d * (length * i / n)
        box("%s_pk_%d" % (name, i), (0.07, 0.035, h * 0.82), (c.x, c.y, h * 0.41), "wood_dark")
        bpy.ops.mesh.primitive_cone_add(radius1=0.05, depth=0.16, vertices=4,
                                        location=(c.x, c.y, h * 0.82 + 0.08))
        tip = bpy.context.active_object
        tip.name = "%s_tip_%d" % (name, i)
        tip.rotation_euler = (0, 0, math.radians(45))
        tip.data.materials.append(mat("wood_dark"))


def build_replica_exterior(cfg, L, W):
    ex = dict(DEFAULT_EXTERIOR); ex.update(cfg.get("exterior", {}))
    fe = ex["fence"]; h = fe.get("height", 1.05)
    ter = REPLICA["terrace"]; y0 = L / 2
    box("terrace_deck", (ter["w"], ter["d"], 0.12), (0, y0 + ter["d"] / 2, 0.06), "wood_deck")
    box("terrace_step", (7.6, 0.4, 0.07), (0, y0 + 0.25, 0.035), "wood_deck")
    yb = y0 + fe.get("y_off", 5.0)
    hl, gate = fe.get("half_len", 4.0), fe.get("gate", 3.0)
    _picket_fence("fence_bL", (-hl, yb), (-gate / 2, yb), h)
    _picket_fence("fence_bR", (gate / 2, yb), (hl, yb), h)
    for k, sx in enumerate((-1, 1)):
        _picket_fence("fence_s%d" % k, (sx * hl, y0 + 0.9), (sx * hl, yb), h)
    for row, yy in enumerate((yb + 0.5, yb + 1.1)):
        for sx in (-1, 1):
            for k in range(3):
                xk = sx * (2.3 + k * 1.25) + (0.35 if row else -0.3)
                sphere("shrub_f_%d_%d_%d" % (row, sx, k),
                       0.5 + 0.16 * ((k + row) % 3), (xk, yy - k * 0.35, 0.42), "greenery")
    for sx in (-1, 1):
        for k in range(3):
            sphere("shrub_t_%d_%d" % (sx, k), 0.55 + 0.1 * k,
                   (sx * (ter["w"] / 2 + 0.8), y0 + 1.2 + k * 1.6, 0.5), "greenery")


def build_exterior(cfg, L, W):
    """礼堂外部：栅栏围合海侧草坪、石板步道、海侧门廊、灌木绿植。"""
    ex = dict(DEFAULT_EXTERIOR)
    ex.update(cfg.get("exterior", {}))
    y0 = L / 2  # 海侧墙外皮

    fe = ex["fence"]
    if fe.get("enabled", True):
        h, off, side = fe["height"], fe["offset"], fe["side"]
        gate = fe.get("gate_w", 2.4)
        for k, sx in enumerate((-(side / 2), side / 2)):
            fence_run("fence_side_%d" % k, (sx, y0 + 0.3), (sx, y0 + off), h)
        yb = y0 + off
        fence_run("fence_back_L", (-side / 2, yb), (-gate / 2, yb), h)
        fence_run("fence_back_R", (gate / 2, yb), (side / 2, yb), h)

    pa = ex["path"]
    if pa.get("enabled", True):
        off = ex["fence"]["offset"]
        plane("stone_path", (pa["width"], off + 0.2), (0, y0 + off / 2 + 0.05, 0.01), "floor_light")

    po = ex["porch"]
    if po.get("enabled", True):
        d, ph = po["depth"], po["height"]
        for sx in (-(sea_w / 2 + 0.5), sea_w / 2 + 0.5):
            cylinder("porch_post", 0.08, ph, (sx, y0 + d - 0.3, ph / 2), "wood")
        box("porch_canopy", (sea_w + 1.6, d, 0.1), (0, y0 + d / 2 - 0.1, ph + 0.06), "wood")

    if ex["shrubs"].get("enabled", True):
        off = ex["fence"]["offset"]
        i = 0
        yy = y0 + 0.8
        while yy < y0 + off - 0.4:
            for sx in (-(pa["width"] / 2 + 0.7), pa["width"] / 2 + 0.7):
                sphere("shrub_%d" % i, 0.45 + 0.15 * ((i * 7) % 3), (sx, yy, 0.4), "greenery")
                i += 1
            yy += 1.5
        for sx in (-3.5, -5.5, 3.5, 5.5):
            sphere("shrub_wall_%d" % int(abs(sx)), 0.6, (sx, y0 + 0.5, 0.45), "greenery")


# ---------------- 复刻级礼堂（replica=True，2026-08-25 五图实证） ----------------

REPLICA = {
    "opening_w": 7.2, "opening_h": 2.5,      # 海侧通宽敞开口
    "side_post_step": 2.5, "skirt_h": 0.95,  # 侧墙立柱间距/木裙高
    "stained_w": 0.62,                        # 彩玻条带沿坡宽
    "terrace": {"w": 11.0, "d": 4.5},
    "fence": {"h": 1.05, "pickets_gap": 0.15, "y_off": 5.0, "half_len": 4.0, "gate": 3.0},
}


def _gable_glass(L, W, H, rise, y, t):
    """通宽深棂格玻璃三角：轮廓 + 横杠 + 三根竖棂 + 玻璃"""
    tri_prism("gbl_glass_%d" % y, W - 0.3, rise - 0.12, 0.04, (0, y, H + 0.12), "glass")
    seg_between("gbl_rail_L_%d" % y, (-W / 2 + 0.1, y, H + 0.05), (0, y, H + rise), 0.055, "wood_dark")
    seg_between("gbl_rail_R_%d" % y, (W / 2 - 0.1, y, H + 0.05), (0, y, H + rise), 0.055, "wood_dark")
    box("gbl_base_%d" % y, (W - 0.2, 0.1, 0.12), (0, y, H + 0.06), "wood_dark")
    box("gbl_hbar_%d" % y, (W - 0.9, 0.09, 0.1), (0, y, H + rise * 0.45), "wood_dark")
    for k, mx in enumerate((-1.4, 0.0, 1.4)):
        mh = rise * (1 - abs(mx) / (W / 2)) - 0.2
        box("gbl_v_%d_%d" % (y, k), (0.09, 0.09, mh), (mx, y, H + mh / 2 + 0.1), "wood_dark")


def _stained_strip(L, W, H, rise, y0, y1):
    """沿坡彩色玻璃条带（两侧，全长，随坡倾斜）"""
    ang = math.atan2(rise, W / 2)
    colors = ["stained_green", "stained_blue", "stained_red", "stained_amber"]
    seg = 0.75
    n = max(int((y1 - y0) / seg), 1)
    for side, sx in ((-1, -1), (1, 1)):
        for i in range(n):
            ym = y0 + seg * (i + 0.5)
            cx = sx * (W / 2 - 0.30 * math.cos(ang))
            cz = H + 0.30 * math.sin(ang) + 0.02
            box("stained_%d_%d_%d" % (side, int(y0), i), (0.60, seg - 0.04, 0.05),
                (cx, ym, cz), colors[i % 4], rotation=(ang * -sx if False else 0, ang * sx, 0))


def build_replica_chapel(ch, L, W, H, rise):
    t = 0.22
    box("chapel_floor", (W, L, 0.2), (0, 0, 0.1), "floor_light")

    # ---- 侧墙：深木裙 + 通高玻璃 + 立柱 + 弹簧梁 + 壁灯 ----
    step = ch.get("side_post_step", REPLICA["side_post_step"])
    skirt = ch.get("skirt_h", REPLICA["skirt_h"])
    npost = max(int(L / step) + 1, 2)
    for side, sx in (("L", -W / 2), ("R", W / 2)):
        box("skirt_%s" % side, (0.1, L, skirt), (sx, 0, skirt / 2), "wood_dark")
        box("skirt_cap_%s" % side, (0.16, L, 0.05), (sx, 0, skirt + 0.025), "wood_dark")
        box("sglass_%s" % side, (0.04, L - 0.2, H - skirt - 0.35),
            (sx, 0, skirt + (H - skirt - 0.35) / 2), "glass")
        for k in range(npost):
            y = -L / 2 + k * (L / (npost - 1))
            box("post_%s_%d" % (side, k), (0.14, 0.14, H - skirt), (sx, y, skirt + (H - skirt) / 2), "wood_dark")
            if k % 2 == 1:
                cylinder("sconce_%s_%d" % (side, k), 0.11, 0.06,
                         (sx * (W / 2 - 0.16), y, 2.7), "column_white", rotation=(math.radians(90), 0, 0))
        box("spring_%s" % side, (0.18, L, 0.34), (sx, 0, H + 0.17), "wood_dark")

    # ---- 坡屋顶：深木板条吊顶 + 面檐板 + 脊梁（外侧挑檐 0.6） ----
    slope = math.hypot(W / 2, rise) + 0.6
    ang = math.atan2(rise, W / 2)
    box("roof_L", (slope, L + 1.2, 0.08), (-W / 4 - 0.28 * math.cos(ang), 0, H + rise / 2 + 0.28 * math.sin(ang)),
        "wood_dark", rotation=(0, -ang, 0))
    box("roof_R", (slope, L + 1.2, 0.08), (W / 4 + 0.28 * math.cos(ang), 0, H + rise / 2 + 0.28 * math.sin(ang)),
        "wood_dark", rotation=(0, ang, 0))
    for bi in range(ch.get("beams", 6)):
        by = -L / 2 + 1.0 + bi * ((L - 2.0) / max(ch.get("beams", 6) - 1, 1))
        box("beam_%d" % bi, (W - 0.3, 0.2, 0.24), (0, by, H - 0.14), "wood_dark")
    box("ridge_beam", (0.22, L + 1.2, 0.2), (0, 0, H + rise - 0.1), "wood_dark")
    _stained_strip(L, W, H, rise, -L / 2 + 0.4, L / 2 - 0.4)

    # ---- 海侧（Y+）：通宽敞开口 + 折叠门板 + 棂格玻璃三角 + 白圆柱 ----
    so = REPLICA
    ow, oh = so["opening_w"], so["opening_h"]
    side_w = (W - ow) / 2
    for k, sx in enumerate((-(ow / 2 + side_w / 2), (ow / 2 + side_w / 2))):
        box("sea_pier_%d" % k, (side_w, t, H), (sx, L / 2 - t / 2, H / 2), "wood_dark")
    box("sea_lintel", (W, t, 0.35), (0, L / 2 - t / 2, oh + 0.175), "wood_dark")
    gz0, gz1 = oh + 0.35, H
    box("sea_curtain_glass", (W - 0.6, 0.05, gz1 - gz0), (0, L / 2 - t / 2, (gz0 + gz1) / 2), "glass")
    box("sea_curtain_hbar", (W - 0.6, 0.09, 0.08), (0, L / 2 - t / 2, (gz0 + gz1) / 2), "wood_dark")
    nm = 5
    for mi in range(nm):
        mx = -((W - 0.6) / 2) + (W - 0.6) * (mi + 0.5) / nm
        box("sea_muntin_%d" % mi, (0.09, 0.09, gz1 - gz0), (mx, L / 2 - t / 2, (gz0 + gz1) / 2), "wood_dark")
    for si, sx in enumerate((-1, 1)):   # 折叠玻璃门（收拢，之字）
        for p in range(3):
            fx = sx * (ow / 2 - 0.35 - p * 0.55)
            fy = L / 2 - 0.15 + (0.28 if p % 2 else -0.05)
            box("foldoor_%d_%d" % (si, p), (0.62, 0.06, oh - 0.1), (fx, fy, (oh - 0.1) / 2),
                "glass", rotation=(0, 0, math.radians(sx * (18 if p % 2 else -18))))
    _gable_glass(L, W, H, rise, L / 2 - t / 2, t)
    for ci, sx in enumerate((-1, 1)):   # 白色圆柱（两端山墙拐角）
        cylinder("col_white_S%d" % ci, 0.13, H, (sx * (W / 2 - 0.3), L / 2 - 0.35, H / 2), "column_white")

    # ---- 入口端（Y-）：对称棂格玻璃三角 + 中央双开木门 + 玻璃侧扇 + 白圆柱 ----
    dw, dh = 1.7, 2.4
    for k, sx in enumerate((-1, 1)):
        box("ent_glass_%d" % k, (W / 2 - dw / 2 - 0.35, 0.05, H - 0.4),
            (sx * (dw / 2 + 0.35 + (W / 2 - dw / 2 - 0.35) / 2), -L / 2 + t / 2, (H - 0.4) / 2), "glass")
        for p in range(2):   # 门扇 + 内嵌线脚
            box("door_%d_%d" % (k, p), (dw / 2 - 0.03, 0.07, dh), (sx * dw / 4, -L / 2 + t / 2, dh / 2), "wood_dark")
            box("door_panel_%d_%d" % (k, p), (dw / 2 - 0.22, 0.02, dh - 0.5),
                (sx * dw / 4, -L / 2 + t / 2 - 0.045, dh / 2), "wood_deck")
    box("door_frame", (dw + 0.24, 0.1, 0.12), (0, -L / 2 + t / 2, dh + 0.02), "wood_dark")
    tz0, tz1 = dh + 0.15, H
    box("ent_transom_glass", (dw + 0.7, 0.05, tz1 - tz0), (0, -L / 2 + t / 2, (tz0 + tz1) / 2), "glass")
    box("ent_transom_bar", (dw + 0.7, 0.09, 0.07), (0, -L / 2 + t / 2, (tz0 + tz1) / 2), "wood_dark")
    box("ent_beam", (W, t, 0.3), (0, -L / 2 + t / 2, H - 0.15), "wood_dark")
    _gable_glass(L, W, H, rise, -L / 2 + t / 2, t)
    for ci, sx in enumerate((-1, 1)):
        cylinder("col_white_N%d" % ci, 0.13, H, (sx * (W / 2 - 0.3), -L / 2 + 0.35, H / 2), "column_white")

    # ---- 黑铁烛台吊灯（脊下长链，双环） ----
    chx, chz = 0.0, 5.35
    cylinder("chand_chain", 0.018, H + rise - chz - 0.05, (0, 0.5, (H + rise + chz) / 2), "iron_black")
    cylinder("chand_stem", 0.035, 0.5, (0, 0.5, chz + 0.25), "iron_black")
    for ti, (r, z) in enumerate(((0.55, chz), (0.34, chz - 0.22))):
        bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=0.022,
                                         location=(0, 0.5, z))
        tor = bpy.context.active_object; tor.name = "chand_ring_%d" % ti
        tor.rotation_euler = (math.radians(90), 0, 0)
        tor.data.materials.append(mat("iron_black"))
        nc = 8 if ti == 0 else 6
        for ci in range(nc):
            a = 2 * math.pi * ci / nc
            cylinder("chand_c_%d_%d" % (ti, ci), 0.016, 0.16,
                     (0.5 + r * math.cos(a), 0.5 + r * math.sin(a), z + 0.12), "candle")
    return L, W


# ---------------- 仪式区 ----------------

def build_ceremony(cfg):
    c = cfg.get("ceremony", {})
    arch = c.get("arch", {"pos": [0, 0, 0], "width": 3.0, "height": 2.6, "palette": "white_cloth"})
    ax, ay, az = arch.get("pos", [0, 0, 0])
    w, h = arch.get("width", 3.0), arch.get("height", 2.6)
    pal = arch.get("palette", "white_cloth")
    cylinder("arch_pole_L", 0.07, h, (ax - w / 2, ay, az + h / 2), "iron")
    cylinder("arch_pole_R", 0.07, h, (ax + w / 2, ay, az + h / 2), "iron")
    bpy.ops.mesh.primitive_torus_add(major_radius=w / 2, minor_radius=0.07,
                                     location=(ax, ay, az + h))
    ring = bpy.context.active_object
    ring.name = "arch_top"
    ring.rotation_euler = (math.radians(90), 0, 0)
    ring.data.materials.append(mat(pal))
    sphere("arch_flower_L", 0.45, (ax - w / 2, ay, az + 0.45), "greenery")
    sphere("arch_flower_R", 0.45, (ax + w / 2, ay, az + 0.45), "greenery")

    ch_spec = c.get("chairs")
    if ch_spec:
        rows, cols = ch_spec.get("rows", 5), ch_spec.get("cols", 3)
        y0 = ch_spec.get("y_start", -4.5)
        dy = ch_spec.get("row_dy", 0.68)
        x0 = ch_spec.get("aisle_edge", 1.12)
        dx = ch_spec.get("seat_dx", 0.62)
        wid, dep = 0.44, 0.42
        for side in (-1, 1):
            for r in range(rows):
                for cidx in range(cols):
                    cx = side * (x0 + cidx * dx)
                    cy = y0 + r * dy
                    gid = "%s_%d_%d" % ("W" if side < 0 else "E", r, cidx)
                    # 座面 + 软垫
                    box("wchair_%s_seat" % gid, (wid, dep, 0.05), (cx, cy, 0.455), "wood_honey")
                    box("wchair_%s_pad" % gid, (wid - 0.05, dep - 0.05, 0.035), (cx, cy, 0.497), "white_cloth")
                    # 四腿
                    for li, (lx, ly) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
                        cylinder("wchair_%s_leg%d" % (gid, li), 0.018, 0.44,
                                 (cx + lx * (wid / 2 - 0.035), cy + ly * (dep / 2 - 0.035), 0.22), "wood_honey")
                    # 背柱（后侧两根）+ 交叉背两条横档
                    for li, lx in enumerate((-1, 1)):
                        cylinder("wchair_%s_bp%d" % (gid, li), 0.02, 0.5,
                                 (cx + lx * (wid / 2 - 0.035), cy - dep / 2 + 0.035, 0.71), "wood_honey")
                    for bi, bz in enumerate((0.68, 0.86)):
                        box("wchair_%s_sl%d" % (gid, bi), (wid - 0.06, 0.035, 0.06),
                            (cx, cy - dep / 2 + 0.03, bz), "wood_honey")
        return
    aisle = c.get("aisle", {"rows": 4, "seats_per_row": 5, "aisle_w": 1.8})
    rows, per_row, aw = aisle.get("rows", 4), aisle.get("seats_per_row", 5), aisle.get("aisle_w", 1.8)
    for r in range(rows):
        y = ay + 1.6 + r * 0.9
        for s in range(per_row):
            side = -1 if s % 2 == 0 else 1
            idx = s // 2
            x = side * (aw / 2 + 0.45 + idx * 0.55)
            box("seat_%d_%d" % (r, s), (0.45, 0.45, 0.85), (x, y, 0.425), "white_cloth")
            box("backrest_%d_%d" % (r, s), (0.45, 0.08, 0.5), (x, y - 0.2, 1.05), "white_cloth")
    plane("aisle_petals", (aw * 0.8, rows * 0.9), (ax, ay + 1.6 + rows * 0.45, 0.22), "petal")

    if c.get("sign_in"):
        sx, sy = c["sign_in"].get("pos", [-6, 6])
        box("sign_desk", (1.8, 0.6, 1.05), (sx, sy, 0.525), "wood")
        plane("sign_mirror", (1.4, 2.0), (sx, sy, 0.23), "glass")

# ---------------- 晚宴区 ----------------

def build_dinner(cfg):
    d = cfg.get("dinner", {})
    dy = d.get("pos_y", 26)
    tables = d.get("long_tables", 2)
    spacing = d.get("table_spacing", 3.0)
    for i in range(tables):
        x = (i - (tables - 1) / 2) * spacing
        box("table_%d_top" % i, (0.9, 6.0, 0.06), (x, dy, 0.75), "tablecloth")
        for lx in (-0.35, 0.35):
            for ly in (-2.7, 2.7):
                cylinder("table_%d_leg" % i, 0.05, 0.75, (x + lx, dy + ly, 0.375), "wood")
        for fy in (-2.0, 0, 2.0):
            sphere("table_%d_flower" % i, 0.22, (x, dy + fy, 0.92), "greenery")
            cylinder("table_%d_candle" % i, 0.04, 0.25, (x + 0.25, dy + fy, 0.92), "warm_light")
    chairs_per_side = d.get("chairs_per_side", 8)
    for i in range(tables):
        x = (i - (tables - 1) / 2) * spacing
        for s_idx in range(chairs_per_side):
            yy = dy - 2.6 + s_idx * (5.2 / max(chairs_per_side - 1, 1))
            for side in (-1, 1):
                box("dchair_%d_%d_%d" % (i, s_idx, side), (0.42, 0.42, 0.45),
                    (x + side * 0.75, yy, 0.225), "white_cloth")

    lights = d.get("string_lights")
    if lights:
        h = lights.get("height", 3.2)
        x0, x1 = -6.5, 6.5
        y0, y1 = dy - 4.0, dy + 4.0
        for px, py in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            cylinder("light_pole", 0.06, h, (px, py, h / 2), "wood")
        sag = 0.35
        spans = [((x0, y0, h), (0, (y0 + y1) / 2, h - sag)),
                 ((0, (y0 + y1) / 2, h - sag), (x1, y1, h)),
                 ((x1, y1, h), (0, (y0 + y1) / 2 + 2, h - sag)),
                 ((0, (y0 + y1) / 2 + 2, h - sag), (x0, y0, h))]
        for si, (p1, p2) in enumerate(spans):
            seg_between("wire_%d" % si, p1, p2, 0.012, "iron")
            steps = 8
            for t_i in range(1, steps):
                f = t_i / steps
                px = p1[0] + (p2[0] - p1[0]) * f
                py = p1[1] + (p2[1] - p1[1]) * f
                pz = p1[2] + (p2[2] - p1[2]) * f - sag * math.sin(math.pi * f) * 0.3
                sphere("bulb_%d_%d" % (si, t_i), 0.05, (px, py, pz - 0.06), "warm_light")

    if d.get("dessert"):
        ddx, ddy = d["dessert"].get("pos", [9, dy - 3])
        box("dessert_table", (2.0, 0.7, 0.95), (ddx, ddy, 0.475), "wood")
        plane("dessert_runner", (1.7, 0.5), (ddx, ddy, 0.96), "white_cloth")

# ---------------- 灯光与机位 ----------------

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


def camera_preset(name, L, W, cfg):
    """机位预设：静态坐标 + 依赖礼堂尺寸/拱门位置的动态机位。"""
    static = {
        "dinner_wide": ((0, 18.0, 4.0), (0, 26.0, 1.2)),
        "dinner_guest": ((-1.2, 22.5, 1.4), (0.5, 26.0, 1.0)),
        "dinner_night": ((4.5, 19.5, 2.2), (0, 26.5, 1.5)),
    }
    if name in static:
        return static[name]
    try:
        arch_y = cfg.get("ceremony", {}).get("arch", {}).get("pos", [0, 2.0, 0])[1]
    except Exception:
        arch_y = 2.0
    dynamic = {
        # 从入口中轴看向仪式拱门与海侧大开口（照片主视角）
        "ceremony_front": ((0, -L / 2 + 1.6, 1.6), (0, arch_y + 2.5, 2.0)),
        # 仪式区 45° 侧视
        "ceremony_side45": ((-W / 2 + 0.9, -L / 2 + 2.8, 1.8), (0.6, arch_y + 1.0, 1.6)),
        # 站在海侧大开口前往外看草坪晚宴
        "ceremony_doorview": ((0, L / 2 - 1.2, 1.7), (0, 26.0, 2.0)),
        # 礼堂内部对角全景（空间感）
        "chapel_interior": ((-W / 2 + 0.7, -L / 2 + 1.0, 1.6), (W / 4, L / 4, 2.2)),
        # 外部斜侧看礼堂海侧立面（山墙/栅栏/步道）
        "chapel_exterior": ((W / 2 + 5.5, L / 2 + 10.5, 2.4), (0, L / 2 - 1.0, 3.2)),
    }
    return dynamic.get(name)


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
    if quick:
        scene.render.resolution_x = 1280
        scene.render.resolution_y = 720
    else:
        scene.render.resolution_x = 1920
        scene.render.resolution_y = 1080
    cfg = cfg or {}
    ch = cfg.get("venue", {}).get("chapel", DEFAULT_CHAPEL)
    L, W = ch.get("length", DEFAULT_CHAPEL["length"]), ch.get("width", DEFAULT_CHAPEL["width"])
    for name in names:
        preset = camera_preset(name, L, W, cfg)
        if preset is None:
            print("[warn] 未知机位 %s，跳过" % name)
            continue
        cam_data = bpy.data.cameras.new("cam_" + name)
        cam_data.lens = 40 if "dinner" in name else 28  # 内部机位28mm对齐实拍广角
        cam = bpy.data.objects.new("camera_" + name, cam_data)
        bpy.context.collection.objects.link(cam)
        pos, target = preset
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
    layout_path = "layouts/wedding.v0.json"
    quick = False
    cameras_override = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--quick":
            quick = True
        elif a == "--samples":
            SAMPLES_OVERRIDE = int(args[i + 1])
            i += 1
            globals()["SAMPLES_OVERRIDE"] = SAMPLES_OVERRIDE
        elif a == "--camera":
            cameras_override.append(args[i + 1])
            i += 1
        elif not a.startswith("--"):
            layout_path = a
        i += 1
    with open(layout_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 工作区从布局文件位置推断：<ws>/layouts/x.json → 渲染输出到 <ws>/renders/
    ws = os.path.dirname(os.path.dirname(os.path.abspath(layout_path)))
    out_dir = os.path.join(ws, "renders")
    os.makedirs(out_dir, exist_ok=True)

    clear_scene()
    _v = cfg.get("venue", {})
    L, W = build_venue(_v)
    if _v.get("chapel", {}).get("replica"):
        build_replica_exterior(_v, L, W)
    else:
        sea_w = _v.get("chapel", {}).get("sea_opening", {}).get("w", 4.5)
        build_exterior(_v, L, W, sea_w)
    if cfg.get("ceremony"):   # 布置元素默认关闭，由用户后续迭代添加
        build_ceremony(cfg)
    if cfg.get("dinner"):
        build_dinner(cfg)
    build_lighting(cfg.get("time", "day"))
    cams = cameras_override or cfg.get("cameras", ["ceremony_front", "dinner_wide"])
    render_cameras(cams, out_dir,
                   os.path.splitext(os.path.basename(layout_path))[0], quick=quick, cfg=cfg)
    print("[done] %s renders in %s" % ("QUICK" if quick else "FULL", out_dir))

if __name__ == "__main__":
    main()
