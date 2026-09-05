#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compose_layout.py — Agent 看图 → 产出 layout JSON（两遍：生成 + 自审修正）

用法：
  python3 compose_layout.py --images <案例图/场地照...> \
      --out ../blender/layouts/wedding.v1.json [--base ../blender/layouts/wedding.v0.json]

流程：
  第 1 遍：qwen-vl 读图，按 schema 估计空间布局输出 JSON
  第 2 遍：把 原图 + 第 1 遍 JSON 再给 qwen-vl 自审，指出估计错误并输出修正版
  最后本地 sanitize（数值钳制到合理区间），写入 out，并记录 source_images。
之后人在 preview.html 上看渲染结果纠偏，改 JSON 再重渲（迭代循环的入口）。
"""
import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qwenvl  # noqa: E402

SCHEMA_PROMPT = """你是婚礼场地空间布局分析师。看图中的婚礼布置，按下面的 JSON schema 估计空间布局并输出。

【尺度标定】拱门高度通常 2.2~3.0 米；婚礼椅宽约 0.45 米；长桌宽约 0.9 米。
【坐标系】原点在礼堂中心，Y 轴指向海（晚宴方向）为正；单位米。

schema（只输出这一个 JSON，不要多余文字）：
{
 "time": "day|dusk|night 按图中光线判断",
 "venue": {"chapel": {"length": 8-16, "width": 5-12, "wall_h": 3-7}},
 "ceremony": {
   "arch": {"pos": [x,y,z], "width": 1.5-5, "height": 2.0-3.5,
            "palette": "white_cloth|greenery|petal 之一（按拱门主材质）"},
   "aisle": {"rows": 0-10, "seats_per_row": 0-14, "aisle_w": 1.2-3.0},
   "sign_in": {"pos": [x,y]}  // 图中无签到区则省略
 },
 "dinner": {  // 图中无晚宴区则整个省略
   "pos_y": 14-40, "long_tables": 0-6, "table_spacing": 1.5-6,
   "chairs_per_side": 4-15,
   "string_lights": {"height": 2.2-4.5} 或省略,
   "dessert": {"pos": [x,y]} 或省略
 },
 "cameras": ["ceremony_front","ceremony_side45","ceremony_doorview","dinner_wide","dinner_guest","dinner_night"] 的子集
}
图中没有的区域直接省略字段；数字按图中实际情况估计，不要照抄示例。"""

REVIEW_PROMPT = """你是空间布局校对员。第一张图是原始参考图，下面是你此前估计的布局 JSON：
%s
请对照原图逐项检查：数量（座椅排数/每排数/长桌数）、尺度（拱门宽高、桌长）、相对位置（拱门在礼堂前端、晚宴在草坪海侧）、时段判断。
只修正与原图不符的地方；确有依据再改，拿不准的保持原值。
只输出修正后的完整 JSON，不要解释。"""

# 数值钳制表：字段路径 → (min, max, default)
CLAMPS = {
    ("venue", "chapel", "length"): (8, 16, 12),
    ("venue", "chapel", "width"): (5, 12, 8),
    ("venue", "chapel", "wall_h"): (3, 7, 5),
    ("ceremony", "arch", "width"): (1.5, 5, 3.0),
    ("ceremony", "arch", "height"): (2.0, 3.5, 2.6),
    ("ceremony", "aisle", "rows"): (0, 10, 4),
    ("ceremony", "aisle", "seats_per_row"): (0, 14, 6),
    ("ceremony", "aisle", "aisle_w"): (1.2, 3.0, 1.8),
    ("dinner", "pos_y"): (14, 40, 26),
    ("dinner", "long_tables"): (0, 6, 2),
    ("dinner", "table_spacing"): (1.5, 6, 3),
    ("dinner", "chairs_per_side"): (4, 15, 8),
}
VALID_PALETTES = {"white_cloth", "greenery", "petal", "monet_lavender"}
VALID_TIMES = {"day", "dusk", "night"}
VALID_CAMERAS = {"ceremony_front", "ceremony_side45", "ceremony_doorview",
                 "dinner_wide", "dinner_guest", "dinner_night"}


def sanitize(cfg, base):
    """v2 语义：cfg（agent/看图产物）为权威源；base 只补缺失的顶层键；
    已知数值字段做钳制、枚举字段做校验。不丢弃任何未知字段（chairs/replica/exterior 等透传）。"""
    out = copy.deepcopy(cfg) if cfg else {}
    if base:
        for k, v in base.items():
            if k not in out:
                out[k] = copy.deepcopy(v)

    def clampv(path, val, dft):
        lo, hi, _ = CLAMPS.get(path, (None, None, dft))
        try:
            v = float(val)
        except (TypeError, ValueError):
            return dft
        if lo is None:
            return v
        return round(max(lo, min(hi, v)), 1)

    def walk(node, path=()):
        if isinstance(node, dict):
            for k in list(node.keys()):
                p = path + (k,)
                if p in CLAMPS:
                    node[k] = clampv(p, node[k], CLAMPS[p][2])
                else:
                    walk(node[k], p)

    walk(out)

    if "time" not in out or out["time"] not in VALID_TIMES:
        out["time"] = "dusk" if "time" not in out else out["time"]
        if out["time"] not in VALID_TIMES:
            out["time"] = "dusk"
    ch = out.setdefault("venue", {}).setdefault("chapel", {})
    pal = ch.get("windows")  # noqa: 占位无操作，保持结构可读
    a = out.setdefault("ceremony", {}).get("arch")
    if isinstance(a, dict) and a.get("palette") not in VALID_PALETTES:
        a["palette"] = "white_cloth"
    cams = [c0 for c0 in (out.get("cameras") or []) if c0 in VALID_CAMERAS]
    if cams:
        out["cameras"] = cams
    else:
        out.pop("cameras", None)
    return out


def diff_summary(a, b, prefix=""):
    lines = []
    for k in sorted(set(a) | set(b)):
        va, vb = a.get(k, "<无>"), b.get(k, "<无>")
        if isinstance(va, dict) and isinstance(vb, dict):
            lines += diff_summary(va, vb, prefix + k + ".")
        elif va != vb:
            lines.append("%s%s: %s → %s" % (prefix, k, va, vb))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", required=False, default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default=None, help="用于补默认值的基准 JSON")
    ap.add_argument("--vlmodel", default="qwen-vl-max")
    ap.add_argument("--passes", type=int, default=2, help="自审遍数（默认 2：生成+修正）")
    ap.add_argument("--validate", metavar="FILE", default=None,
                    help="v2 模式：宿主多模态 agent 亲自看图写好 JSON 后，只做钳制校验与规范化（不调 VLM）")
    args = ap.parse_args()

    if args.validate:
        base = None
        if args.base and os.path.exists(args.base):
            with open(args.base, encoding="utf-8") as bf:
                base = json.load(bf)
        with open(args.validate, encoding="utf-8") as vf:
            cfg = json.load(vf)
        final = sanitize(cfg, base)
        final["source_images"] = args.images or cfg.get("source_images", [])
        # 有 --out 写新文件（保留草稿）；否则原地规范化
        target = args.out if args.out else args.validate
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        with open(target, "w", encoding="utf-8") as vf:
            json.dump(final, vf, ensure_ascii=False, indent=2)
        print("[validate] 已钳制规范化 ->", target)
        return

    base = None
    if args.base and os.path.exists(args.base):
        with open(args.base, encoding="utf-8") as f:
            base = json.load(f)

    # 第 1 遍：看图生成
    cfg = qwenvl.parse_json_sloppy(
        qwenvl.call(SCHEMA_PROMPT, args.images, model=args.vlmodel))
    print("[pass1] 原始估计:", json.dumps(cfg, ensure_ascii=False)[:400])

    # 第 2+ 遍：自审修正
    for i in range(2, args.passes + 1):
        prompt = REVIEW_PROMPT % json.dumps(cfg, ensure_ascii=False, indent=1)
        cfg2 = qwenvl.parse_json_sloppy(qwenvl.call(prompt, args.images, model=args.vlmodel))
        d = diff_summary(cfg, cfg2)
        print("[pass%d] 修正 %d 处: %s" % (i, len(d), "; ".join(d[:8]) or "无"))
        cfg = cfg2

    final = sanitize(cfg, base)
    final["source_images"] = args.images
    final["version"] = os.path.splitext(os.path.basename(args.out))[0].replace("wedding.", "")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print("[done]", args.out)
    print(json.dumps(final, ensure_ascii=False, indent=2)[:1200])


if __name__ == "__main__":
    main()
