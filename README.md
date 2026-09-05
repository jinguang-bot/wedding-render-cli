# wedding-render-cli

婚礼现场效果图渲染管线的 CLI 分发版：**3D 骨架建模 + 照片级化 + 审图闭环**。
面向 AI agent 设计——单行 JSON 输出、`schema` 自描述命令面、`install.md` 可被 agent 逐字执行。

## 快速开始（人类）

```bash
uv tool install --force ./cli          # 或发布后的 wheel URL
wedding-render setup --agent zcode     # 装技能族（zcode/claude-code/codex）
wedding-render init --ws ./wedding-render && $EDITOR wedding-render/.env  # 填 DASHSCOPE_API_KEY
wedding-render doctor --ws ./wedding-render
wedding-render schema
```

## 命令面

`version` / `schema` / `doctor` / `setup` / `init`
`skeleton`（Blender 骨架渲染，--quick 秒级）· `compose`（看图→布局JSON 两遍自审，支持 --validate 纯校验）
`snapshot`（会话→overlay 增量层）· `rebuild`（L1参数+L2增量 一体化重建渲染）
`photoreal`（qwen-image 照片级化，锁布局）· `review`（qwen-vl 四维评分）
`tag`（案例图打标，断点续跑）· `preview`（HTML 四栏对照页）

## 包内结构

```
src/wedding_render/
├── cli.py                # 入口：argparse 命令分发，JSON 输出
├── scripts/              # 能力脚本（随包分发，与技能族同源）
├── skills/               # 三个技能文件夹（setup 时拷入宿主技能目录）
└── assets/seed_chapel.json
```

## 与技能族的关系

- **能力同源**：`./sync.sh` 从项目 `.agents/skills/` 同步脚本与技能到此包（修改能力后需同步再发布）
- **两种用法**：agent 装技能族走 SKILL.md 编排（自然语言触发）；装 CLI 走本入口（结构化调用）
- 命令语义、材质契约、布局 schema 与技能文档完全一致

## 发布（未来）

`uv build` 产出 wheel → GitHub Release 固定版本 URL → install.md 第 1 步切到来源 B。
