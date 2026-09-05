---
name: wedding-render
description: 婚礼现场效果图总编排（父级技能）：案例图打标检索、把婚礼需求翻译成布局改动、调度 scene-skeleton 建骨架与人在环迭代、调度 photoreal-render 照片级化与审图，产出可发婚策沟通的效果图。当用户提到婚礼效果图、婚礼布置渲染、组合婚策案例元素、婚礼3D场景、改婚礼布局重渲时使用——即使用户只说"换个花色再出一张"也应触发。
---

# wedding-render · 婚礼效果图编排（父级）

本技能是**领域编排层**：持有婚礼领域知识与流程约束，把通用能力委托给两个子技能执行——

- **scene-skeleton**：看图→scene JSON→Blender 骨架渲染（`<skills>/scene-skeleton/`）
- **photoreal-render**：骨架图/任意图→照片级成品+审图闭环（`<skills>/photoreal-render/`）

"调用子技能" = 按对应子技能的 SKILL.md 流程执行其 scripts（子技能与本级同在
`.agents/skills/` 下；若用户仅装了本级，先提示安装子技能）。

## 工作区约定（与子技能一致）

```
<workspace>/
├── .env                  # DASHSCOPE_API_KEY（生图与 qwen-vl 同 key）
├── assets/index.csv      # 婚策案例标签库（本级 tag_cases.py 维护）
├── layouts/wedding.vN.json
├── renders/  finals/  preview.html
```

## 感知分工（v2）

宿主 agent 具备视觉（预设前提）：看图估布局、几何自检、造型微调由 agent 亲自执行
（scene-skeleton v2 工作流）；qwen-vl 通道仅保留两处——批量打标可选通道 + review.py
独立复核（防 agent 自评偏差）。生图正式交付默认 qwen-image-3.0-pro。

## 流程（婚礼特化）

### 1. 案例打标与检索（本级职责）
`assets/index.csv` 缺该婚策记录时先补齐：
```bash
python3 <skill_dir>/scripts/tag_cases.py --cases <案例图根目录> --out assets/index.csv [--only 北然,礼成] [--limit 20]
```
按用户口述的风格/色系/元素在 index.csv 检索候选案例，列清单让用户确认；
组合任务的 style_ref 必须指向 index.csv 中真实存在的案例文件。

### 2. 骨架生成与人在环迭代（委托 scene-skeleton）
```bash
python3 ../scene-skeleton/scripts/compose_layout.py --images <确认的案例图...> \
    --out layouts/wedding.vN.json --base layouts/wedding.v(N-1).json
blender -b -P ../scene-skeleton/scripts/layout.py -- layouts/wedding.vN.json --quick
python3 ../scene-skeleton/scripts/contact_sheet.py --layout layouts/wedding.vN.json --open
```
用户口头反馈的翻译对照（婚礼话术→JSON 字段）见 `references/wedding_notes.md`。
**骨架获用户认可前不要出正式渲染**（婚礼决策点：布局确认是效果图满意的前提）。

### 3. 照片级化（委托 photoreal-render）
```bash
python3 ../photoreal-render/scripts/photoreal.py --layout layouts/wedding.vN.json \
    --refs <风格参考案例图...> --provider dashscope
```
婚礼语境默认：仪式区白绿系优先用用户 ❤️ 案例作参考；晚宴图注意灯串是否点亮（dusk/night）。

### 4. 审图闭环（委托 photoreal-render）
```bash
python3 ../photoreal-render/scripts/review.py --image finals/wedding.vN_<机位>.png --layout layouts/wedding.vN.json
```
修正路由沿用子技能规则；婚礼特有偏好（必备元素/拒绝元素）写进 assets/preferences.md，
review 不达线时优先对照该文件。

## 硬约束
- 原始案例图（婚策方案/）只读
- 每张成品保留四件套可追溯：finals + renders + layout JSON + review 评分卡
- 布局版本只增不改；API 批量前先单图确认
- `scripts/qwenvl.py` 是三技能共享副本，改动需同步另两份

## 部署
跨 runtime 安装与 MCP 配置见 `references/deployment.md`。
