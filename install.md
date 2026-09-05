# wedding-render CLI · Agent 安装指南

> 本文档面向**能执行 shell 命令的 AI Agent**。请逐字遵循步骤执行，不要仅阅读后转述。
> 规则：① 安装来源固定（下方给出的 URL），不得替换为其他分支/镜像；② 每步以验证命令的成功为准，未验证成功不得宣称完成；
> ③ 遇到缺前置条件（Python/uv/Blender/API key）→ 向用户如实报告 blocker 并等待，不要擅自更换运行时或来源；
> ④ 不要向用户展示 API key 或 .env 内容。

## 完成标准

`wedding-render version` 成功、技能族 installed、`doctor` 通过（Blender 与 API key 就绪）、工作区已 init。
若宿主需要重启才能识别新装技能，如实告知用户"complete with restart pending"，不要宣称当前会话已就绪。

---

### 第 1 步 · 检查与安装 CLI

先检查是否已安装：

```bash
wedding-render version
```

成功则跳过安装。否则确认前置（Python ≥3.10、`uv`），然后安装**固定版本 wheel**：

```bash
uv tool install "https://github.com/jinguang-bot/wedding-render-cli/releases/download/v0.4.0/wedding_render_cli-0.4.0-py3-none-any.whl"
```

验证（必须成功才算完成本步）：

```bash
wedding-render version
```

### 第 2 步 · 安装 Blender MCP（必装——交互建模的核心通道）

```bash
wedding-render setup-mcp --ws <工作区目录>
```

该命令完成：安装 blender-mcp 服务端 → 将 addon 装入 Blender 并启用 → 写入 autostart 脚本 → 输出 MCP 客户端配置。
随后**启动 Blender GUI**（macOS：`open -a Blender --args --python '<工作区>/autostart_mcp.py'`，或在 Blender 内 N 面板 → MCP for Blender → Connect）。
验证通道已通（port 9876）：

```bash
wedding-render doctor --ws <工作区目录>
```

`blender_mcp.reachable` 必须为 true 才算本步完成。宿主支持 MCP 时，把输出的 client_config 挂载后 agent 即可直接操作 Blender。

### 第 3 步 · 安装技能族到宿主

```bash
wedding-render setup --agent auto
```

自动识别失败时按宿主显式指定：`--agent zcode` / `--agent claude-code` / `--agent codex`。
成功标准：返回 JSON 中 `installed` 含三个路径（wedding-render / scene-skeleton / photoreal-render）。
宿主不支持技能目录时：告知用户将以 CLI 直调模式使用（跳过本步，不算失败）。

### 第 4 步 · 环境体检

```bash
wedding-render doctor --ws <工作区目录>
```

- Blender 未找到 → 报告用户：`brew install --cask blender`（经同意后代跑）
- DASHSCOPE_API_KEY 未配置 → 请用户提供阿里百炼 key，写入 `<工作区>/.env`：
  `DASHSCOPE_API_KEY=sk-...`（生图与视觉模型共用）后重跑 doctor

### 第 5 步 · 初始化工作区（已有则跳过）

```bash
wedding-render init --ws <工作区目录>
```

### 第 6 步 · 最终校验

依次运行 `version`、`doctor --ws <ws>`、`schema` 三条；**`doctor` 的 blender_mcp.reachable 必须为 true**（MCP 主模式闸门）；向用户**汇报摘要**
（CLI 版本 / 技能安装与重启需求 / Blender 与 key 状态 / 工作区路径），不要粘贴大段原始 JSON。

---

## Onboarding 之后

- 用 `wedding-render schema` 实时发现命令面与用法，不依赖记忆
- 主工作流（MCP 具身模式）：agent 亲眼看参考图/渲染图 → 经 blender MCP 在 GUI 会话中亲手建模复刻与调整 →
  `snapshot`（每轮有效修改后快照三层状态）→ `photoreal`（照片级化）→ `review`（双评审）。
  辅助：`compose`（看图→布局JSON 起草）· `skeleton --quick`（JSON 快速预览，draft 用）
- 只读命令（version/doctor/schema）可直接执行；产生费用（compose/photoreal/review/tag）与
  渲染（skeleton/rebuild）前确认工作区 .env 就绪；批量生成前先单图确认

## 升级

新版本发布后（版本号见仓库 Release 页）：

```bash
uv tool uninstall wedding-render-cli && uv tool install "https://github.com/jinguang-bot/wedding-render-cli/releases/download/v<新版本>/wedding_render_cli-<新版本>-py3-none-any.whl"
```

注意：同版本号重复安装可能命中 uv 的 wheel 缓存；升级请勿只加 --force。
