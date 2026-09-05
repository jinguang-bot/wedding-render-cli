#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
photoreal.py — 骨架渲染图 + 风格参考案例 → 照片级成品效果图

用法：
  python3 photoreal.py --layout ../blender/layouts/wedding.v0.json \
      --renders ../renders --refs <案例图1> <案例图2> \
      --provider dashscope [--model qwen-image-edit] [--camera ceremony_front] [--dry-run]

零第三方依赖（标准库）。API key 从环境变量读取：
  dashscope → DASHSCOPE_API_KEY   openai → OPENAI_API_KEY   gemini → GEMINI_API_KEY
注意：各厂商图像编辑接口字段在 P0 选型时需按当日文档核对（标记 VERIFY_P0 处）。
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.request
import urllib.error
import uuid

# ---------------- 环境与 .env ----------------

def load_env():
    """从仓库根目录 .env 读取 KEY=VALUE（不覆盖已有环境变量）"""
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


# ---------------- 材质语义翻译（与 blender/semantic_palette.md 同步） ----------------
PALETTE_TEXT = {
    "white_fabric": "柔软的白色织物与纱幔，哑光织物质感",
    "greenery": "自然舒展的绿植叶材，清透有层次",
    "warm_light": "点亮的暖光灯串与蜡烛，柔和光斑",
    "wood": "原木质感家具与木饰面",
    "wood_dark": "深色胡桃木饰面与木结构",
    "wood_deck": "户外防腐木平台，板条清晰",
    "floor_light": "抛光浅色石材地面，柔和倒影",
    "stone": "天然石材立面与台阶",
    "glass": "清透玻璃幕墙与窗格，反射环境光",
    "metal_black": "哑光黑金属构架",
    "metal": "拉丝金属表面",
    "fabric_red": "深红色织物幕幔",
    "paint_white": "乳白色漆面墙体",
    "paint_cream": "奶油色漆面",
    "lawn": "修剪平整的草坪",
    "sea": "开阔的海面与天际线",
    "stained_green": "绿色系彩绘玻璃",
    "stained_red": "红色系彩绘玻璃",
    "stained_blue": "蓝色系彩绘玻璃",
    "stained_amber": "琥珀色系彩绘玻璃",
}

TIME_TEXT = {
    "day": "正午前后明亮的自然日光，蓝天白云，海风清透",
    "dusk": "三亚黄昏 golden hour，暖橙色斜阳，天边粉橘色晚霞，串灯已点亮",
    "night": "入夜后的海滨草坪，深蓝夜空，串灯与烛光是主要光源，氛围温馨浪漫",
}

LOCK_LAYOUT = (
    "【最重要的要求】严格保持输入图中所有物体的位置、数量、比例、透视与相机角度完全不变，"
    "只替换材质与细节，不得增删移动任何大型物体。"
)


def build_prompt(layout, camera_name):
    """从场景 JSON 通用组装照片级化指令（领域语义交给工作区 palette.json 与用户 prompt）"""
    parts = [
        "把这张场景布局示意图转成照片级真实的实景照片。",
        LOCK_LAYOUT,
        "整体氛围：" + TIME_TEXT.get(layout.get("time", "day"), TIME_TEXT["day"]) + "，专业摄影质感。",
    ]
    g = layout.get("ground", {}) or {}
    if g.get("material") in PALETTE_TEXT:
        parts.append("地面：" + PALETTE_TEXT[g["material"]] + "。")
    objs = layout.get("objects") or []
    described = [PALETTE_TEXT[o.get("material")] for o in objs
                 if isinstance(o, dict) and o.get("material") in PALETTE_TEXT]
    if described:
        uniq = list(dict.fromkeys(described))
        parts.append("场景主要材质：" + "；".join(uniq) + "。")
    if (layout.get("backdrop") or {}).get("sea"):
        parts.append("背景：开阔海面与天际线。")
    parts.append(
        "材质细节丰富、光照物理正确、景深自然，8k 实拍质感。"
    )
    return chr(10).join(parts)

# ---------------- 图片工具 ----------------

def img_to_data_url(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return "data:%s;base64,%s" % (mime, b64)


def http_json(url, payload, headers, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def http_multipart(url, fields, files, headers, timeout=600):
    boundary = uuid.uuid4().hex
    body = []
    for k, v in fields.items():
        body.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                     % (boundary, k, v)).encode())
    for k, (fname, data) in files.items():
        body.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                     "Content-Type: application/octet-stream\r\n\r\n" % (boundary, k, fname)).encode())
        body.append(data)
        body.append(b"\r\n")
    body.append(("--%s--\r\n" % boundary).encode())
    payload = b"".join(body)
    headers = dict(headers)
    headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    req = urllib.request.Request(url, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ---------------- Provider 适配器 ----------------

def gen_dashscope(prompt, image_paths, model):
    """qwen-image-3.0 / 3.0-pro 图像编辑（I2I），同步 multimodal-generation 端点。
    文档：help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference
    输入图 1-3 张（首张为待编辑图，其余为参考图）；响应图片 URL 24 小时有效，立即下载。"""
    load_env()
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        sys.exit("[error] 未设置 DASHSCOPE_API_KEY")
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    content = [{"image": img_to_data_url(p)} for p in image_paths[:3]] + [{"text": prompt}]
    payload = {
        "model": model or "qwen-image-3.0",
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {"prompt_extend": True, "prompt_extend_mode": "direct",
                       "watermark": False, "n": 1},
    }
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    out = http_json(url, payload, headers, timeout=600)
    if out.get("code"):
        sys.exit("[error] dashscope %s: %s" % (out.get("code"), out.get("message")))
    try:
        for part in out["output"]["choices"][0]["message"]["content"]:
            if "image" in part:
                u = part["image"]
                if u.startswith("http"):
                    with urllib.request.urlopen(u, timeout=120) as r:
                        return r.read()
                return base64.b64decode(u.split(",", 1)[1])
    except Exception as e:
        sys.exit("[error] dashscope 响应解析失败(%s)：%s"
                 % (e, json.dumps(out, ensure_ascii=False)[:800]))


def gen_openai(prompt, image_paths, model):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("[error] 未设置 OPENAI_API_KEY")
    url = "https://api.openai.com/v1/images/edits"
    fields = {"model": model or "gpt-image-1", "prompt": prompt, "size": "1792x1024"}
    files = {}
    for i, p in enumerate(image_paths):
        with open(p, "rb") as f:
            files["image[]" if i else "image"] = (os.path.basename(p), f.read())
    headers = {"Authorization": "Bearer " + key}
    out = http_multipart(url, fields, files, headers)
    data = out["data"][0]
    if data.get("b64_json"):
        return base64.b64decode(data["b64_json"])
    with urllib.request.urlopen(data["url"], timeout=120) as r:
        return r.read()


def gen_gemini(prompt, image_paths, model):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("[error] 未设置 GEMINI_API_KEY")
    # VERIFY_P0: 模型名按当日可用图像编辑模型核对（如 gemini-2.5-flash-image）
    m = model or "gemini-2.5-flash-image"
    url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
           % (m, key))
    parts = [{"text": prompt}]
    for p in image_paths:
        with open(p, "rb") as f:
            parts.append({"inline_data": {"mime_type": mimetypes.guess_type(p)[0] or "image/png",
                                          "data": base64.b64encode(f.read()).decode()}})
    payload = {"contents": [{"parts": parts}],
               "generationConfig": {"responseModalities": ["IMAGE"]}}
    out = http_json(url, payload, {"Content-Type": "application/json"})
    for part in out["candidates"][0]["content"]["parts"]:
        if "inline_data" in part:
            return base64.b64decode(part["inline_data"]["data"])
    sys.exit("[error] gemini 响应无图像：" + json.dumps(out, ensure_ascii=False)[:800])


PROVIDERS = {"dashscope": gen_dashscope, "openai": gen_openai, "gemini": gen_gemini}


# ---------------- 主流程 ----------------

def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", default=None, help="layout JSON（管线模式）")
    ap.add_argument("--renders", default="../renders")
    ap.add_argument("--refs", nargs="*", default=[], help="风格参考案例图")
    ap.add_argument("--provider", default="dashscope",
                    choices=list(PROVIDERS) + ["none"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--camera", default=None, help="只处理指定机位（如 ceremony_front）")
    ap.add_argument("--out", default="../finals")
    ap.add_argument("--dry-run", action="store_true", help="只打印 prompt，不调 API")
    # --custom 模式（P0 实验等）：直接给定图片与指令，不走 layout 组装
    ap.add_argument("--images", nargs="*", default=None,
                    help="custom 模式输入图（首张为待编辑图）")
    ap.add_argument("--prompt", default=None, help="custom 模式指令")
    ap.add_argument("--name", default="custom", help="custom 模式输出文件名前缀")
    args = ap.parse_args()

    # 默认输出/输入目录锚定到仓库根，避免受运行时工作目录影响
    if args.renders == "../renders":
        args.renders = "renders"
    if args.out == "../finals":
        args.out = "finals"
    os.makedirs(args.out, exist_ok=True)

    if args.images or args.prompt:
        if not (args.images and args.prompt):
            sys.exit("[error] --custom 需要 --images 与 --prompt 同时提供")
        prompt = args.prompt
        if args.refs:
            prompt += "\n花艺与布置风格参考随附的案例图（只取其风格与花材感觉，布局以首张输入图为准）。"
        if args.dry_run or args.provider == "none":
            print("=== %s prompt ===\n%s" % (args.name, prompt))
            return
        images = args.images + args.refs
        print("[gen]", args.name, "provider=", args.provider, "images=", len(images))
        data = PROVIDERS[args.provider](prompt, images, args.model)
        out = os.path.join(args.out, args.name + ".png")
        with open(out, "wb") as f:
            f.write(data)
        print("[done]", out)
        return

    if not args.layout:
        sys.exit("[error] 需要提供 --layout（管线模式）或 --images+--prompt（custom 模式）")
    with open(args.layout, encoding="utf-8") as f:
        layout = json.load(f)
    # 渲染文件名与 layout.py 保持一致：使用布局文件名（去扩展名）作为 tag
    tag = os.path.splitext(os.path.basename(args.layout))[0]

    cams = args.camera and [args.camera] or layout.get("cameras", [])
    for cam in cams:
        base = "%s_%s" % (tag, cam)
        render = os.path.join(args.renders, base + ".png")
        if not os.path.exists(render):
            print("[skip] 无骨架渲染图:", render)
            continue
        prompt = build_prompt(layout, cam)
        if args.refs:
            prompt += "\n花艺与布置风格参考随附的案例图（只取其风格与花材感觉，布局仍以输入图为准）。"
        if args.dry_run or args.provider == "none":
            print("=== %s prompt ===\n%s\n" % (base, prompt))
            continue
        images = [render] + args.refs
        print("[gen]", base, "provider=", args.provider, "refs=", len(args.refs))
        data = PROVIDERS[args.provider](prompt, images, args.model)
        out = os.path.join(args.out, base + ".png")
        with open(out, "wb") as f:
            f.write(data)
        print("[done]", out)


if __name__ == "__main__":
    main()
