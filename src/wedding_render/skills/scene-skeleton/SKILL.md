---
name: scene-skeleton
description: 3D 场景骨架生成：从参考图/需求估计空间布局生成 scene JSON，Blender headless 渲染多机位骨架示意图（秒级快渲染），并产出 preview 对照页供人在环迭代。当用户要求"看图建 3D 场景/生成布局骨架/渲染布局示意图/快速预览布局"，或被父级技能（如 wedding-render）编排时使用。不限婚礼场景，任何需要"先用 3D 锁定空间关系"的可视化任务都适用。
---

# scene-skeleton · 3D 场景骨架

从参考图/需求生成参数化 3D 场景骨架并渲染多机位示意图。**骨架只做空间关系（位置/比例/机位），
不做细节建模——材质用色块语义表达，细节交给照片级化（配合 photoreal-render 技能）。**

本技能自包含：脚本在 `<skill_dir>/scripts/`，契约文档在 `<skill_dir>/references/`。
工作数据放**工作区**（先 cd 过去），不写入技能文件夹。

## 工作区约定

```
<workspace>/
├── layouts/<scene>.vN.json   # 布局 JSON：单一事实源，版本只增不改
├── renders/                  # 骨架渲染图（--quick=1280×720 秒级；正式=1920×1080）
└── preview.html              # contact_sheet.py 产出（参考图/JSON/骨架/成品 对照）
```

首次初始化：`mkdir -p layouts renders && cp <skill_dir>/assets/layouts/seed_chapel.json layouts/<scene>.v0.json`
（种子=精准礼堂纯建筑模板；礼堂几何参数已内置于建模器默认值）

依赖：Blender 4/5（`brew install --cask blender`）；Python 3.10+。

## 流程

### 1. 看图生成布局（两遍：估计 → 自审修正 → 数值钳制）
```bash
python3 <skill_dir>/scripts/compose_layout.py --images <参考图...> \
    --out layouts/<scene>.vN.json [--base layouts/<scene>.v(N-1).json]
```
无参考图时也可手工编辑 JSON——字段含义与取值范围**必须先读** `references/scene_schema.md`。

### 2. 快速预览（每次改 JSON 后必跑）
```bash
blender -b -P <skill_dir>/scripts/layout.py -- layouts/<scene>.vN.json --quick [--camera <机位>]
```
然后生成对照页给人看：`python3 <skill_dir>/scripts/contact_sheet.py --layout layouts/<scene>.vN.json --open`
用户口头反馈 → 改 JSON 字段 → 重跑快渲染 → 刷新对照页，循环到达成为止。
骨架获用户认可后再去掉 `--quick` 出正式渲染（全机位 1920×1080）。

### 3. 交付给照片级化
渲染图路径传给 photoreal-render 技能（或其 scripts/photoreal.py）。色块→材质的翻译
契约见 `references/semantic_palette.md`（该表同时被 photoreal-render 内嵌兜底，
修改时两侧同步）。

## v2 工作流：Agent 视觉直建 + MCP 手 + 状态快照

宿主为多模态 agent 时（本技能族的预设前提）：

1. **看图写布局**：agent 亲自看参考图写 layout JSON（schema 见 references/scene_schema.md，
   尺度标定：椅0.45m/门2.1m/拱门2.2-3m），写完跑
   `python3 <skill_dir>/scripts/compose_layout.py --validate <json>` 仅做钳制校验（不调 VLM）
2. **参数化底座**：layout.py 建精准 base（v4 礼堂参数内置）
3. **MCP 亲手调整**（需要模板外几何时）：开 Blender GUI + blender-mcp addon，
   agent 看渲染图/参考图 → 经 MCP 改场景 → 重渲 → 再看，循环
4. **快照铁律**：每轮有效修改后立即
   `blender -b -P <skill_dir>/scripts/snapshot.py -- --base layouts/x.json --out layouts/x.overlay.json --blend sessions/x.blend`
   复现三层：base JSON（参数）+ overlay.json（增量图元）+ .blend（100%保真）。
   重建：layout.py 建底座后 `apply_overlay.py -- layouts/x.overlay.json`
5. **几何自检**：agent 亲眼看渲染 vs 参考照片，**≥3 机位**逐项核对（窗数/比例/开口）后才算通过

## 硬约束
- 布局版本只增不改；数值遵守 scene_schema.md 的钳制范围
- 渲染图是色块示意图是设计而非 bug；不要试图在骨架阶段做精细建模
- `scripts/qwenvl.py` 是三技能共享副本，改动需同步另两份

## 当前边界（第一步拆分备注）
schema 字段仍是婚礼词汇（arch/aisle/dinner/机位命名），来自原 wedding-render。
出现第二个使用场景时再做通用化重构（blocks/zones 体系），当前保持向后兼容。
