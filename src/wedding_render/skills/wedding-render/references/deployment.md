# 部署到其他 Agent Runtime

## 首选：CLI 安装（推荐给其他 agent）

让 agent 逐字执行项目根 `cli/install.md`（Museon 风格 onboarding），核心三步：

```bash
uv tool install "https://github.com/jinguang-bot/wedding-render-cli/releases/download/v0.2.0/wedding_render_cli-0.2.0-py3-none-any.whl"
wedding-render setup --agent auto      # 技能族装入宿主（zcode/claude-code/codex）
wedding-render doctor && wedding-render schema
```

CLI 与技能族能力同源（`cli/sync.sh` 同步），命令输出单行 JSON，agent 可全程结构化调用。

## 手工安装（备选）

技能族共三个，**同层级放在同一个 skills 目录下**（父级通过相对路径 `../scene-skeleton/`
调度子技能）：

```
<skills-root>/
├── wedding-render/      # 父级：婚礼编排 + tag_cases + 领域笔记
├── scene-skeleton/      # 子：3D 骨架（compose_layout / layout / contact_sheet）
└── photoreal-render/    # 子：照片级化 + 审图（photoreal / review / qwenvl）
```

工作区数据（layouts/renders/finals/.env/index.csv）留在各项目，不随技能走。

## 全局安装（所有项目可用）

```bash
# ZCode / 通用 .agents 规范（三个技能一起拷）
cp -r wedding-render scene-skeleton photoreal-render ~/.agents/skills/
# Claude Code
cp -r wedding-render scene-skeleton photoreal-render ~/.claude/skills/
```

项目级安装放 `<project>/.agents/skills/`（ZCode 优先发现 `.zcode/skills/`，
同名时 `.zcode` 副本覆盖 `.agents` 副本）。

## Codex（通过 AGENTS.md 编排）

把下段追加到项目 `AGENTS.md`：

```markdown
## wedding-render 技能族
婚礼效果图任务按 .agents/skills/wedding-render/SKILL.md 执行（父级编排）；
骨架生成用 ../scene-skeleton/ 的脚本，照片级化与审图用 ../photoreal-render/ 的脚本。
先 cd 到工作区再执行。
```

## MCP 方式挂载（可选，P5 路线）

```jsonc
// Claude Code: .mcp.json | ZCode: mcp 配置 mcpServers 段
{
  "mcpServers": {
    "blender": { "command": "uvx", "args": ["blender-mcp"] },
    "wedding-render": { "command": "python3",
                        "args": ["<skills-root>/photoreal-render/scripts/mcp_server.py"] }
  }
}
```

```toml
# Codex: ~/.codex/config.toml
[mcp_servers.blender]
command = "uvx"
args = ["blender-mcp"]

[mcp_servers.wedding-render]
command = "python3"
args = ["<skills-root>/photoreal-render/scripts/mcp_server.py"]
```

注：`mcp_server.py`（脚本工具化的 MCP 封装）尚未实现，当前以 SKILL.md 编排 + CLI
为主；实现后此文件同步更新。


## blender-mcp（v2：agent 的手）

```bash
uv tool install blender-mcp        # 或运行时 uvx blender-mcp
# Blender GUI: Edit→Preferences→Add-ons→Install 从 uv 工具目录选 addon 或下载 repo 的 addon.py
# 3D 视口按 N → BlenderMCP 标签 → Start MCP Server（默认端口 9876）
# 客户端配置（ZCode/Claude Code mcp）: {"command":"uvx","args":["blender-mcp"]}
```
约束：MCP 会话中的有效修改必须 snapshot 回 overlay/blend（见 scene-skeleton v2 工作流）。
