#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qwenvl.py — 共享的 qwen-vl 视觉语言模型调用模块（DashScope，与生图同一个 API key）

【共享模块副本】本文件在 scene-skeleton / photoreal-render / wedding-render 三个技能中各有一份副本，修改任意一份时必须同步其余两份（self-contained 技能不做跨目录 import）。
模型默认 qwen-vl-max（视觉理解最强档）；qwen-vl-plus 更快更便宜。
"""
import base64
import json
import mimetypes
import os
import sys
import urllib.request

API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


def load_env():
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def _data_url(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode())


def call(prompt, image_paths=(), model="qwen-vl-max", max_tokens=3000, timeout=300):
    """多图 + 指令 → 文本返回。图片顺序即传入顺序。"""
    load_env()
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        sys.exit("[error] 未设置 DASHSCOPE_API_KEY")
    content = [{"image": _data_url(p)} for p in image_paths] + [{"text": prompt}]
    payload = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {"max_tokens": max_tokens, "result_format": "message"},
    }
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read().decode())
    if out.get("code"):
        sys.exit("[error] dashscope %s: %s" % (out.get("code"), out.get("message")))
    msg = out["output"]["choices"][0]["message"]["content"]
    if isinstance(msg, list):  # 部分模型返回分段 content
        msg = "".join(p.get("text", "") for p in msg)
    return msg


def parse_json_sloppy(text):
    """鲁棒解析：容忍 ```json 围栏与前后杂文"""
    text = text.strip()
    if "```" in text:
        seg = text.split("```")
        for s in seg:
            s = s.strip()
            if s.startswith("json"):
                s = s[4:].strip()
            if s.startswith("{") or s.startswith("["):
                text = s
                break
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("响应中未找到 JSON：" + text[:200])
    return json.loads(text[start:])
