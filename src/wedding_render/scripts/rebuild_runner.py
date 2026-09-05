#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rebuild_runner.py — 三层复现的 L1+L2 一体化重建：base JSON(参数) + overlay.json(增量) → 渲染
用法：blender -b -P rebuild_runner.py -- <base.json> [overlay.json] [--quick]
"""
import bpy, json, os, sys

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
base_path = args[0]
overlay_path = args[1] if len(args) > 1 and not args[1].startswith("--") else None
quick = "--quick" in args

here = os.path.dirname(os.path.abspath(base_path and __file__ or "."))
sys.path.insert(0, here)
import importlib.util
def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(here, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

layout = _load("layout")
with open(base_path, encoding="utf-8") as f:
    cfg = json.load(f)

layout.clear_scene()
layout.build_ground(cfg.get("ground"), cfg.get("backdrop"))
n_base = layout.build_objects(cfg.get("objects"))
layout.build_lighting(cfg.get("time", "day"))
print("[rebuild] base 物体 %d" % n_base)

if overlay_path:
    ov = _load("apply_overlay")
    n = ov.apply(overlay_path)
    print("[rebuild] overlay 物体 %d" % n)

tag = os.path.splitext(os.path.basename(base_path))[0]
ws = os.path.dirname(os.path.dirname(os.path.abspath(base_path)))
out_dir = os.path.join(ws, "renders")
os.makedirs(out_dir, exist_ok=True)
layout.render_cameras(cfg.get("cameras", ["front", "side45", "wide"]), out_dir, tag, quick=quick, cfg=cfg)
print("[rebuild] done ->", out_dir)