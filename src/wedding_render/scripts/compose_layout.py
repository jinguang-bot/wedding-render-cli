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

SCHEMA_PROMPT = """你是场地空间布局分析师。看图中的场景布置，按下面的 JSON schema 估计空间布局并输出。

【尺度标定】座椅宽约 0.45 米；人行门高约 2.1 米；标准层高 2.8~3.5 米。
【坐标系】原点在场地中心，X 轴向右，Y 轴向远处（纵深），Z 向上；单位米。

schema（只输出这一个 JSON，不要多余文字）：
{
 "time": "day|dusk|night 按图中光线判断",
 "ground": {"size": [宽, 深], "material": "lawn|floor_light|stone|wood_deck 之一"},
 "backdrop": {"sea": true} 或省略,
 "objects": [   // 场地中的主要结构件与元素（数量按图估计，通常 3~30 个）
   {"name": "英文标识", "type": "box|sphere|cylinder",
    "size": [x,y,z], "location": [x,y,z], "rotation": [0,0,z角度],
    "material": "wood|wood_dark|wood_deck|glass|metal_black|white_fabric|greenery|stone|floor_light|warm_light 之一"}
 ],
 "cameras": ["front", "side45", "top", "wide"] 的子集
}
objects 覆盖图中可辨识的主要结构（舞台/墙体/桌椅成组时可合并为大件示意）；不要照抄示例。"""

REVIEW_PROMPT = """你是空间布局校对员。第一张图是原始参考图，下面是你此前估计的布局 JSON：
%s
请对照原图逐项检查：物体数量与类别、尺寸比例、相对位置、时段判断。
只修正与原图不符的地方；确有依据再改，拿不准的保持原值。
只输出修正后的完整 JSON，不要解释。"""

VALID_TIMES = {"day", "dusk", "night"}
VALID_MATERIALS = None  # 材质自由字符串，渲染端对未知材质回退灰色
VALID_CAMERAS = {"front", "back", "side45", "top", "wide"}


def sanitize(cfg, base):
    """通用语义：cfg 为权威源；base 只补缺失顶层键；
    校验 time 枚举、objects 列表结构、cameras 预设名；不做领域字段钳制。"""
    import copy
    out = copy.deepcopy(cfg) if cfg else {}
    if base:
        for k, v in base.items():
            if k not in out:
                out[k] = copy.deepcopy(v)

    if "time" not in out:
        out["time"] = "day"
    if out["time"] not in VALID_TIMES:
        out["time"] = "day"

    g = out.get("ground")
    if not isinstance(g, dict) or not g.get("size"):
        out["ground"] = {"size": [24, 24], "material": "lawn"}

    objs = out.get("objects")
    if not isinstance(objs, list):
        out["objects"] = []
    else:
        clean = []
        for i, o in enumerate(objs):
            if not isinstance(o, dict):
                continue
            o.setdefault("name", "obj_%d" % i)
            o.setdefault("type", "box")
            o.setdefault("location", [0, 0, 0])
            o.setdefault("size", [1, 1, 1])
            o.setdefault("rotation", [0, 0, 0])
            clean.append(o)
        out["objects"] = clean

    cams = [c for c in (out.get("cameras") or []) if c in VALID_CAMERAS]
    out["cameras"] = cams or ["front", "side45", "wide"]
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
