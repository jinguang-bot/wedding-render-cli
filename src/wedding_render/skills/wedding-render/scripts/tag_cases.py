#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tag_cases.py — 婚策案例图 VLM 批量打标（断点续跑）

用法：
  python3 tag_cases.py --cases "../婚策方案" --out ../assets/index.csv \
      [--provider gemini] [--limit 20] [--only 北然,启蔻]

打标维度与 index.csv 列一一对应。已打标的文件自动跳过（断点续跑）。
注意：VLM 适配目前实现 gemini；openai/dashscope 在 P0 拿到 key 后按文档补齐。
（在 ZCode 环境中也可以由 agent 直接用内置视觉工具打标后手工写入 CSV，本脚本用于打包后的独立运行。）
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qwenvl  # noqa: E402

FIELDS = ["文件", "婚策", "区域", "风格", "主色系", "花材特征", "材质元素",
          "时段", "氛围标签", "适合风格参考", "备注"]

TAG_PROMPT = """你是婚礼布置案例标注员。看这张图，只输出一个 JSON 对象（不要多余文字）：
{
 "区域": "仪式区|晚宴区|签到区|合影区|细节特写|全景",
 "风格": "如 韩式|森系|白绿色系|欧式|复古|海岛自然|主题定制 等，可组合",
 "主色系": "如 白绿|粉紫|香槟金|日落暖色|白粉 等",
 "花材特征": "如 白玫瑰+尤加利|绣球+郁金香|干花|永生花|以绿植为主",
 "材质元素": "从 [纱幔,木艺,铁艺,玻璃,灯串,烛台,镜面,干花] 中选出现的",
 "时段": "日|暮|夜",
 "氛围标签": "3个词以内，如 清新通透/浪漫温馨/高级简约",
 "适合风格参考": "是|否（构图完整、适合作为生图风格参考则为是）",
 "备注": "一句话描述最突出的元素（拱门形态/桌花形式/吊顶等），无则空字符串"
}"""


def tag_image(path, vlmodel):
    """单图打标：qwen-vl（与生图同一个 key）"""
    raw = qwenvl.call(TAG_PROMPT, [path], model=vlmodel, max_tokens=1200)
    return qwenvl.parse_json_sloppy(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True, help="婚策方案根目录")
    ap.add_argument("--out", required=True, help="index.csv 输出路径")
    ap.add_argument("--only", default=None, help="只处理指定婚策（逗号分隔）")
    ap.add_argument("--vlmodel", default="qwen-vl-max")
    ap.add_argument("--limit", type=int, default=None, help="本次最多处理几张")
    args = ap.parse_args()

    done = set()
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("文件"):
                    done.add(row["文件"])
        print("[resume] 已有 %d 条记录，跳过" % len(done))

    tasks = []
    for comp in sorted(os.listdir(args.cases)):
        cdir = os.path.join(args.cases, comp)
        if not os.path.isdir(cdir) or comp.startswith("."):
            continue
        if args.only and comp not in args.only.split(","):
            continue
        for sub in ("案例图片", ""):
            d = os.path.join(cdir, sub) if sub else cdir
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if fn.lower().endswith((".png", ".jpg", ".jpeg")) and not fn.startswith("."):
                        rel = "%s/%s" % (comp, ("案例图片/" if sub else "") + fn)
                        if rel not in done:
                            tasks.append((comp, os.path.join(d, fn), rel))
                break

    if args.limit:
        tasks = tasks[:args.limit]
    print("[plan] 待打标 %d 张" % len(tasks))

    write_header = not os.path.exists(args.out)
    with open(args.out, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        for i, (comp, path, rel) in enumerate(tasks):
            try:
                tags = tag_image(path, args.vlmodel)
            except Exception as e:
                tags = {k: "" for k in FIELDS}
                tags["备注"] = "打标失败: %s" % str(e)[:80]
            row = {"文件": rel, "婚策": comp}
            row.update({k: str(tags.get(k, "")) for k in FIELDS if k not in ("文件", "婚策")})
            w.writerow(row)
            f.flush()
            print("[%d/%d]" % (i + 1, len(tasks)), rel, "→", tags.get("风格", ""), tags.get("主色系", ""))
    print("[done] 结果写入", args.out)


if __name__ == "__main__":
    main()
