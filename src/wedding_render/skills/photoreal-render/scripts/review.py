#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
review.py — VLM 审图：对成品效果图打四维评分卡，输出结构化结果与修正路由建议

用法：
  python3 review.py --image ../finals/wedding.v0_ceremony_front.png \
      --layout ../blender/layouts/wedding.v0.json --refs <骨架渲染图> [--provider gemini]

评分维度与权重（与实施方案 P4 一致）：
  布局一致性 35%（对照骨架渲染图）/ 元素符合度 25% / 风格匹配 20% / 真实感 20%
输出：<image>.review.json，含总分、分项、问题清单、修正路由建议。
退出码：总分 >= 3.5 → 0（通过）；否则 1（触发修正流程）。
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qwenvl  # noqa: E402

SCORE_PROMPT = """你是婚礼效果图的质检评审。对照【骨架布局图】与【布局要求】，评审【成品效果图】。

维度与权重：布局一致性35 / 元素符合度25 / 风格匹配20 / 真实感20。
各维度打 1~5 分（5 最好），只输出一个 JSON 对象，不要输出其他文字：
{
 "layout_consistency": {"score": n, "issues": ["..."]},
 "element_match":      {"score": n, "issues": ["..."]},
 "style_match":        {"score": n, "issues": ["..."]},
 "realism":            {"score": n, "issues": ["..."]},
 "overall": n,
 "route": "fix_prompt | fix_layout | change_refs | change_time | human"
}
route 判定：布局分低→fix_layout；元素分低→fix_layout；风格分低→change_refs；
真实感低→change_time；多维度低或 overall<2.5→human。"""


def img_part(path):
    with open(path, "rb") as f:
        return {"inline_data": {"mime_type": mimetypes.guess_type(path)[0] or "image/png",
                                "data": base64.b64encode(f.read()).decode()}}


def call_vlm(prompt, image_paths, provider, model):
    if provider == "dashscope":
        # qwen-vl 与生图同一个 API key（qwenvl 模块负责 .env 加载）
        return qwenvl.call(prompt, image_paths, model=model or "qwen-vl-max")
    key_var = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}[provider]
    key = os.environ.get(key_var)
    if not key:
        sys.exit("[error] 未设置 " + key_var)

    if provider == "gemini":
        m = model or "gemini-2.5-flash"
        url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
               % (m, key))
        parts = [{"text": prompt}] + [img_part(p) for p in image_paths]
        payload = {"contents": [{"parts": parts}]}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            out = json.loads(resp.read().decode())
        return out["candidates"][0]["content"]["parts"][0]["text"]
    sys.exit("[error] provider=%s 的 VLM 适配待补齐" % provider)


def parse_json_sloppy(text):
    """模型偶尔会包 ```json 围栏，做个鲁棒解析"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    return json.loads(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="成品效果图")
    ap.add_argument("--layout", required=True)
    ap.add_argument("--render", default=None, help="对应骨架渲染图（默认自动推断）")
    ap.add_argument("--provider", default="dashscope")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    with open(args.layout, encoding="utf-8") as f:
        layout = json.load(f)

    render = args.render
    if not render:
        name = os.path.basename(args.image)
        guess_cam = name.rsplit("_", 1)[1].replace(".png", "") if "_" in name else None
        cand = os.path.join(os.path.dirname(os.path.dirname(args.image)),
                            "renders", name)
        render = cand if os.path.exists(cand) else None

    req_text = SCORE_PROMPT + "\n【布局要求 JSON】\n" + json.dumps(
        {k: layout.get(k) for k in ("time", "ceremony", "dinner")}, ensure_ascii=False)

    images = [args.image] + ([render] if render and os.path.exists(render) else [])
    if len(images) == 1:
        req_text += "\n（注意：未找到骨架图，布局一致性按成品自身结构合理性评估并注明）"
    raw = call_vlm(req_text, images, args.provider, args.model)
    result = parse_json_sloppy(raw)

    weights = {"layout_consistency": 35, "element_match": 25, "style_match": 20, "realism": 20}
    weighted = sum(result.get(k, {}).get("score", 0) * w for k, w in weights.items()) / 100.0
    result["weighted_overall"] = round(weighted, 2)
    result["image"] = args.image
    result["render_reference"] = render

    out_path = args.image + ".review.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("[review]", out_path, "→", "PASS" if weighted >= 3.5 else "NEED_FIX")
    sys.exit(0 if weighted >= 3.5 else 1)


if __name__ == "__main__":
    main()
