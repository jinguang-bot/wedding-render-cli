---
name: photoreal-render
description: 照片级图像生成与编辑闭环：把 3D 骨架示意图/色块图/草图转成照片级真实感成品，支持图生图风格迁移、局部修改保持布局（换花色换材质换时段），并用 qwen-vl 自动审图评分（四维评分卡+修正路由）。当用户要求"转成真实照片/照片级渲染/换材质换色/风格迁移/审图评分"，或被父级技能（如 wedding-render）编排时使用。不限婚礼场景，任何 img2img 照片级化任务都适用。
---

# photoreal-render · 照片级化与审图闭环

输入图（骨架渲染图/案例图/任意图片）+ 指令/风格参考 → 照片级成品，附 VLM 自动评分。
本技能自包含：脚本在 `<skill_dir>/scripts/`，prompt 库在 `<skill_dir>/references/`。
工作区需有 `.env`（`DASHSCOPE_API_KEY=...`）；先 cd 到工作区再执行。

## 两种用法

### A. 管线模式（输入是 scene-skeleton 的骨架渲染）
```bash
python3 <skill_dir>/scripts/photoreal.py --layout <scene>.vN.json \
    [--renders renders] [--camera ceremony_front] \
    --refs <风格参考图...> --provider dashscope
```
- prompt 从 layout JSON 自动组装（锁布局 + 材质语义翻译 + 时段氛围）
- 骨架色块→材质的翻译依据 `references/prompts.md` 与 scene-skeleton 的 semantic_palette.md（两侧同步）

### B. 直调模式（任意图片，P0 已验证可独立用于风格迁移）
```bash
python3 <skill_dir>/scripts/photoreal.py \
    --images <待编辑图> [<参考图>...] --prompt "指令" --name <输出名> \
    --provider dashscope [--model qwen-image-3.0|qwen-image-3.0-pro]
```

## 参数速查
- `--dry-run` 只打印 prompt 不调 API（批量前先单图确认，省配额）
- 默认模型 qwen-image-3.0；正式交付可用 `--model qwen-image-3.0-pro` 对比画质
- 选型记录与 API 要点见 `references/model_selection.md`（prompt_extend_mode 必须 direct）

## 审图闭环（通过线 3.5）
```bash
python3 <skill_dir>/scripts/review.py --image finals/<成品>.png --layout <scene>.vN.json
```
评分卡写到 `<成品>.png.review.json`。修正路由：布局低 → prompt 加强
"严格保持布局"重跑，仍低回 scene-skeleton 查骨架；元素低 → 改 layout 重渲；
风格低 → 换 --refs；真实感低 → 换时段/氛围模板（`references/prompts.md`）。
同图自动重试 ≤3 次，不过则交人工。

## 双评审制（v2）

宿主多模态 agent 场景下，成品必须过两道独立评审：
1. **agent 自审**：亲看成品+骨架图，按四维 rubric（布局/元素/风格/真实感）逐项打分并写证据
2. **独立 VLM 复核**：`review.py`（qwen-vl 盲评，不知 agent 结论）
裁决：双过→交付｜一门过一门不过→再迭代一轮仍分歧→人裁决｜双不过→按短板路由修正。
正式交付默认 `--model qwen-image-3.0-pro`（质量优先）。

## 硬约束
- API 调用前确认 .env 存在；批量生成前先单图确认
- 成品保留可追溯四件套（若来自管线）：finals + renders + layout JSON + review 评分卡
- `scripts/qwenvl.py` 是三技能共享副本，改动需同步另两份
