#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contact_sheet.py — 生成 HTML 可视化对照页（人在迭代循环中的观察入口）

用法：python3 contact_sheet.py --layout blender/layouts/wedding.v1.json [--open]

页面四栏：原始参考图 / 当前布局 JSON / 骨架渲染图 / 成品效果图。
图片全部 base64 内嵌，preview.html 单文件可分享。人在页面上看出问题 → 口述给 agent →
agent 改 JSON → 重渲 → 刷新本页。
"""
import argparse
import base64
import glob
import html
import json
import os


def img_tag(path, max_w=520, caption=""):
    if not (path and os.path.exists(path)):
        return ""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    cap = ("<div class='cap'>%s</div>" % html.escape(caption)) if caption else ""
    return "<figure><img src='data:image/png;base64,%s' style='max-width:%dpx'/><figcaption>%s%s</figcaption></figure>" % (
        b64, max_w, cap, html.escape(os.path.basename(path)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", required=True)
    ap.add_argument("--open", action="store_true", help="生成后用浏览器打开")
    args = ap.parse_args()

    with open(args.layout, encoding="utf-8") as f:
        cfg = json.load(f)
    tag = os.path.splitext(os.path.basename(args.layout))[0]
    ws = os.getcwd()

    def section(title, figures):
        if not figures:
            return ""
        return "<h2>%s</h2><div class='row'>%s</div>" % (title, "".join(figures))

    srcs = [s for s in cfg.get("source_images", []) if os.path.exists(s)]
    renders = sorted(glob.glob(os.path.join(ws, "renders", tag + "_*.png")))
    finals = sorted(glob.glob(os.path.join(ws, "finals", tag + "_*.png")))
    # 排除带 .review 的json伴生文件不存在问题；finals 中成品图（排除实验图）
    parts = [
        "<html><head><meta charset='utf-8'><title>场景布局预览 %s</title><style>"
        "body{font-family:-apple-system,'PingFang SC',sans-serif;background:#faf9f7;"
        "margin:24px;color:#37352f}h1{font-size:20px}h2{font-size:15px;margin:24px 0 8px;"
        "border-bottom:2px solid #e9e9e8;padding-bottom:4px}"
        ".row{display:flex;flex-wrap:wrap;gap:14px}"
        "figure{margin:0;background:#fff;padding:8px;border-radius:8px;"
        "box-shadow:0 1px 3px rgba(0,0,0,.08)}figcaption{font-size:12px;color:#8c8a84;"
        "margin-top:4px;word-break:break-all}.cap{color:#1B2A4A;font-weight:600}"
        "pre{background:#fff;padding:14px;border-radius:8px;font-size:12px;"
        "overflow:auto;max-width:640px;box-shadow:0 1px 3px rgba(0,0,0,.08)}"
        "</style></head><body>",
        "<h1>场景布局预览 · %s（%s）</h1>" % (tag, cfg.get("time", "")),
        section("1 · 原始参考图（布局来源）", [img_tag(s, caption="参考 %d" % (i + 1))
                                             for i, s in enumerate(srcs)]),
        "<h2>2 · 当前布局 JSON（单一事实源）</h2><pre>%s</pre>"
        % html.escape(json.dumps(cfg, ensure_ascii=False, indent=2)),
        section("3 · 骨架渲染（空间关系检查）",
                [img_tag(r, caption="骨架 · " + os.path.basename(r).replace(tag + "_", "").replace(".png", ""))
                 for r in renders]),
        section("4 · 成品效果图（照片级化后）",
                [img_tag(r, caption="成品 · " + os.path.basename(r).replace(tag + "_", "").replace(".png", ""))
                 for r in finals]),
        "</body></html>",
    ]
    out = os.path.join(ws, "preview.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    print("[done]", out)
    if args.open:
        os.system("open '%s'" % out)


if __name__ == "__main__":
    main()
