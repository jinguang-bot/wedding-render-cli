#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wedding-render CLI — 婚礼现场效果图渲染管线的命令行入口（供 AI agent 调用）

约定：
- 所有命令输出单行 JSON：{"ok":bool,"cmd":...,"data":{...}}，退出码 0=成功
- 管线命令在工作区（--ws，默认 .）下执行；工作区结构由 init 创建
- 能力脚本随包分发（scripts/），技能族随包分发（skills/），setup 可装入宿主
"""
import argparse
import json
import socket
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

VERSION = "0.3.0"
PKG_DIR = Path(__file__).resolve().parent
SCRIPTS = {
    "compose": PKG_DIR / "scripts" / "compose_layout.py",
    "layout": PKG_DIR / "scripts" / "layout.py",
    "preview": PKG_DIR / "scripts" / "contact_sheet.py",
    "snapshot": PKG_DIR / "scripts" / "snapshot.py",
    "rebuild_runner": PKG_DIR / "scripts" / "rebuild_runner.py",
    "photoreal": PKG_DIR / "scripts" / "photoreal_render" / "photoreal.py",
    "review": PKG_DIR / "scripts" / "photoreal_render" / "review.py",
    "tag": PKG_DIR / "scripts" / "wedding" / "tag_cases.py",
}
SKILL_DIRS = ["wedding-render", "scene-skeleton", "photoreal-render"]


def out(ok, cmd, **data):
    print(json.dumps({"ok": ok, "cmd": cmd, "data": data}, ensure_ascii=False))
    sys.exit(0 if ok else 1)


def find_blender():
    p = shutil.which("blender")
    if p:
        return p
    if platform.system() == "Darwin":
        p = "/Applications/Blender.app/Contents/MacOS/Blender"
        if os.path.exists(p):
            return p
    return None


def run(cmd_args, cwd, timeout=1800):
    """跑子进程，返回 (rc, 输出末尾若干行)"""
    try:
        r = subprocess.run(cmd_args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-12:])
        return r.returncode, tail
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def ws_env_ready(ws):
    envf = Path(ws) / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            if line.startswith("DASHSCOPE_API_KEY=") and len(line.strip()) > 30:
                return True, str(envf)
    return bool(os.environ.get("DASHSCOPE_API_KEY")), "环境变量" if os.environ.get("DASHSCOPE_API_KEY") else str(envf)


# ---------------- 命令实现 ----------------

def cmd_version(a):
    out(True, "version", version=VERSION, python=sys.version.split()[0],
        scripts={k: v.name for k, v in SCRIPTS.items() if v.exists()},
        bundled_skills=SKILL_DIRS)


def cmd_doctor(a):
    ws = Path(a.ws).resolve()
    blender = find_blender()
    bv = ""
    if blender:
        rc, tail = run([blender, "--version"], ws, timeout=60)
        bv = tail.splitlines()[0] if tail else ""
    key_ok, key_at = ws_env_ready(ws)
    mcp_ok = False
    try:
        _s = socket.create_connection(("127.0.0.1", 9876), timeout=1.5)
        _s.close()
        mcp_ok = True
    except Exception:
        pass
    out(True, "doctor",
        python=sys.version.split()[0],
        blender={"found": bool(blender), "path": blender, "version": bv},
        blender_mcp={"reachable": mcp_ok, "port": 9876,
                     "hint": "未连通时：运行 setup-mcp，然后启动 Blender GUI（加载工作区 autostart_mcp.py）或手动 N 面板→MCP for Blender→Connect"},
        dashscope_key={"ready": key_ok, "at": key_at,
                       "hint": "在工作区 .env 写入 DASHSCOPE_API_KEY=sk-...（阿里百炼，生图与 qwen-vl 同 key）"},
        workspace=str(ws), workspace_ready=(ws / "layouts").exists())


def cmd_setup(a):
    agent = a.agent
    if agent == "auto":
        agent = ("claude-code" if Path.home().joinpath(".claude").exists()
                 else "codex" if Path.cwd().joinpath("AGENTS.md").exists()
                 else "zcode")
    dests = {"zcode": Path.home() / ".agents" / "skills",
             "claude-code": Path.home() / ".claude" / "skills",
             "codex": Path.cwd() / ".agents" / "skills"}
    dest = Path(a.skills_dir).expanduser() if a.skills_dir else dests.get(agent)
    if dest is None:
        out(False, "setup", error="未知 agent: %s" % agent)
    dest.mkdir(parents=True, exist_ok=True)
    installed = []
    for s in SKILL_DIRS:
        src = PKG_DIR / "skills" / s
        tgt = dest / s
        if tgt.exists():
            shutil.rmtree(tgt)
        shutil.copytree(src, tgt)
        installed.append(str(tgt))
    agents_md = None
    if agent == "codex":
        am = Path.cwd() / "AGENTS.md"
        snippet = ("\n## wedding-render 技能族\n婚礼效果图任务按 .agents/skills/wedding-render/SKILL.md 执行（父级编排）；"
                   "骨架生成用 scene-skeleton，照片级化与审图用 photoreal-render；"
                   "也可直接调用 wedding-render CLI（`wedding-render schema` 查看命令面）。\n")
        am.open("a", encoding="utf-8").write(snippet) if am.exists() else am.write_text(snippet, encoding="utf-8")
        agents_md = str(am)
    out(True, "setup", agent=agent, dest=str(dest), installed=installed, agents_md=agents_md)


def cmd_init(a):
    ws = Path(a.ws).resolve()
    for d in ("layouts", "renders", "finals", "assets"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    seed_src = PKG_DIR / "assets" / "seed_chapel.json"
    seed = ws / "layouts" / "scene.v0.json"
    if not seed.exists():
        shutil.copy(seed_src, seed)
    envf = ws / ".env"
    env_created = False
    if not envf.exists():
        envf.write_text("# 阿里百炼 API Key（生图 qwen-image 与视觉 qwen-vl 共用）\nDASHSCOPE_API_KEY=\n",
                        encoding="utf-8")
        env_created = True
    out(True, "init", workspace=str(ws), seed=str(seed), env_created=env_created,
        note="请在 .env 填入 DASHSCOPE_API_KEY 后运行 doctor 复核" if env_created else "")


def cmd_skeleton(a):
    ws = Path(a.ws).resolve()
    blender = find_blender()
    if not blender:
        out(False, "skeleton", error="未找到 Blender（brew install --cask blender 或安装到 /Applications）")
    args = [blender, "-b", "-P", str(SCRIPTS["layout"]), "--", a.layout]
    if a.quick:
        args.append("--quick")
    for c in a.camera or []:
        args += ["--camera", c]
    rc, tail = run(args, ws, timeout=2400)
    outs = sorted(str(p) for p in (ws / "renders").glob(Path(a.layout).stem + "_*.png"))
    out(rc == 0, "skeleton", layout=a.layout, rc=rc, renders=outs, log_tail=tail)


def cmd_compose(a):
    ws = Path(a.ws).resolve()
    args = [sys.executable, str(SCRIPTS["compose"]), "--out", a.out]
    if a.validate:
        args += ["--validate", a.validate]
    if a.images:
        args += ["--images"] + a.images
    if a.base:
        args += ["--base", a.base]
    args += ["--passes", str(a.passes)]
    rc, tail = run(args, ws, timeout=1200)
    out(rc == 0, "compose", layout=a.out, rc=rc, log_tail=tail)


def cmd_photoreal(a):
    ws = Path(a.ws).resolve()
    args = [sys.executable, str(SCRIPTS["photoreal"]), "--layout", a.layout,
            "--provider", a.provider]
    if a.camera:
        args += ["--camera", a.camera]
    if a.model:
        args += ["--model", a.model]
    if a.refs:
        args += ["--refs"] + a.refs
    if a.dry_run:
        args.append("--dry-run")
    rc, tail = run(args, ws, timeout=1200)
    out(rc == 0, "photoreal", layout=a.layout, camera=a.camera, rc=rc, log_tail=tail)


def cmd_review(a):
    ws = Path(a.ws).resolve()
    rc, tail = run([sys.executable, str(SCRIPTS["review"]), "--image", a.image,
                    "--layout", a.layout], ws, timeout=600)
    card = Path(a.image)
    card = str(card) + ".review.json" if card.is_absolute() else str(ws / a.image) + ".review.json"
    out(rc == 0, "review", image=a.image, review_json=card if os.path.exists(card) else None,
        log_tail=tail)


def cmd_tag(a):
    ws = Path(a.ws).resolve()
    args = [sys.executable, str(SCRIPTS["tag"]), "--cases", a.cases, "--out", a.out]
    if a.only:
        args += ["--only", a.only]
    if a.limit:
        args += ["--limit", str(a.limit)]
    rc, tail = run(args, ws, timeout=3600)
    out(rc == 0, "tag", index=a.out, rc=rc, log_tail=tail)


def cmd_preview(a):
    ws = Path(a.ws).resolve()
    args = [sys.executable, str(SCRIPTS["preview"]), "--layout", a.layout]
    if a.open:
        args.append("--open")
    rc, tail = run(args, ws, timeout=300)
    out(rc == 0, "preview", page=str(ws / "preview.html"), rc=rc, log_tail=tail)


def cmd_setup_mcp(a):
    """安装 blender-mcp 服务端 + addon 进 Blender + 输出 MCP 客户端配置（v0.3 必装）"""
    ws = Path(a.ws).resolve()
    steps = {}
    blender = find_blender()

    # 1) 服务端
    if shutil.which("blender-mcp"):
        steps["server"] = {"ok": True, "note": "blender-mcp 已安装"}
    else:
        rc, tail = run(["uv", "tool", "install", "blender-mcp"], ws, timeout=600)
        steps["server"] = {"ok": rc == 0, "log": tail[-200:] if rc else tail}
        if rc != 0:
            out(False, "setup-mcp", steps=steps, error="blender-mcp 服务端安装失败（需要 uv）")

    # 2) addon 装入 Blender 用户插件目录
    addon_src = None
    tool_dir = Path(os.environ.get("UV_TOOL_DIR", str(Path.home() / ".local/share/uv/tools")))
    for p in tool_dir.glob("blender-mcp/lib/python3.*/site-packages/blender_mcp/bundled/addon.py"):
        addon_src = p
        break
    if addon_src is None:
        out(False, "setup-mcp", steps=steps, error="未找到 blender-mcp 自带 addon")
    mm = None
    if blender:
        rc, tail = run([blender, "--version"], ws, timeout=60)
        ver = tail.split("(")[0].strip().split()[-1] if tail else ""
        mm = ".".join(ver.split(".")[:2]) or None
    if mm:
        addons_dir = Path.home() / "Library/Application Support/Blender" / mm / "scripts/addons"
    else:
        addons_dir = ws / "blender_addons"
    addons_dir.mkdir(parents=True, exist_ok=True)
    dest = addons_dir / "blender_mcp.py"
    shutil.copy(addon_src, dest)
    steps["addon"] = {"ok": True, "path": str(dest)}

    # 3) headless 启用插件并保存偏好
    if blender:
        rc, tail = run([blender, "-b", "--python-expr",
                        "import bpy\nbpy.ops.preferences.addon_enable(module='blender_mcp')\n"
                        "bpy.ops.wm.save_userpref()\nprint('ADDON_ENABLED')"],
                       ws, timeout=180)
        steps["enable"] = {"ok": "ADDON_ENABLED" in tail}

    # 4) Blender 内置 Python 装 requests（addon 依赖，尽力而为）
    if blender and mm:
        bp = next(iter(Path(f"/Applications/Blender.app/Contents/Resources/{mm}/python/bin").glob("python3.*")), None)
        if bp:
            run([str(bp), "-m", "ensurepip", "--upgrade"], ws, timeout=300)
            rc2, _ = run([str(bp), "-m", "pip", "install", "-q", "requests"], ws, timeout=300)
            steps["blender_requests"] = {"ok": rc2 == 0, "python": str(bp)}
        else:
            steps["blender_requests"] = {"ok": False, "note": "未定位 Blender 内置 Python，首次启动 addon 若报缺 requests 请手动安装"}

    # 5) autostart 脚本写入工作区
    autostart = PKG_DIR / "assets" / "autostart_mcp.py"
    dst_as = ws / "autostart_mcp.py"
    shutil.copy(autostart, dst_as)
    launch = ("open -a Blender --args --python '%s'" % dst_as) if platform.system() == "Darwin" \
             else "blender --python '%s'" % dst_as
    steps["autostart"] = {"ok": True, "path": str(dst_as), "launch": launch}

    # 6) MCP 客户端配置（三平台同构）
    steps["client_config"] = {"mcpServers": {"blender": {"command": "uvx", "args": ["blender-mcp"]}},
                              "note": "ZCode/Claude Code 放入 mcpServers 段；Codex 写 [mcp_servers.blender]"}
    ok = all(v.get("ok") for v in steps.values() if isinstance(v, dict) and "ok" in v)
    out(ok, "setup-mcp", steps=steps,
        note="MCP 会话需 Blender GUI 运行且已 Connect（端口 9876）；headless 命令不受影响")


def cmd_snapshot(a):
    """从已保存的 .blend 会话导出 overlay（L2 增量层）并回写会话"""
    ws = Path(a.ws).resolve()
    blender = find_blender()
    if not blender:
        out(False, "snapshot", error="未找到 Blender")
    args = [blender, "-b", a.blend, "-P", str(SCRIPTS["snapshot"]), "--",
            "--base", a.base, "--out", a.out, "--blend", a.blend]
    rc, tail = run(args, ws, timeout=600)
    out(rc == 0, "snapshot", blend=a.blend, overlay=a.out, rc=rc, log_tail=tail)


def cmd_rebuild(a):
    """三层复现重建：base JSON(+overlay) → Blender 渲染"""
    ws = Path(a.ws).resolve()
    blender = find_blender()
    if not blender:
        out(False, "rebuild", error="未找到 Blender")
    args = [blender, "-b", "-P", str(SCRIPTS["rebuild_runner"]), "--", a.base]
    if a.overlay:
        args.append(a.overlay)
    if a.quick:
        args.append("--quick")
    rc, tail = run(args, ws, timeout=2400)
    outs = sorted(str(p) for p in (ws / "renders").glob(Path(a.base).stem + "_*.png"))
    out(rc == 0, "rebuild", base=a.base, overlay=a.overlay, rc=rc, renders=outs, log_tail=tail)


def cmd_schema(a):
    out(True, "schema", commands={
        "version": "查看版本与随包脚本清单",
        "doctor": {"usage": "wedding-render doctor [--ws DIR]",
                   "checks": ["python>=3.10", "Blender 4/5", "DASHSCOPE_API_KEY（ws/.env 或环境变量）"]},
        "setup": {"usage": "wedding-render setup --agent auto|zcode|claude-code|codex [--skills-dir DIR]",
                  "effect": "把三个技能族装入宿主原生技能目录；codex 额外追加 AGENTS.md 片段"},
        "init": {"usage": "wedding-render init --ws DIR", "effect": "创建工作区 layouts/renders/finals/assets + 种子布局 + .env 模板"},
        "skeleton": {"usage": "wedding-render skeleton --ws DIR --layout layouts/x.json [--quick] [--camera NAME]...",
                     "effect": "Blender 渲染骨架图到 renders/（--quick 秒级 720p）"},
        "compose": {"usage": "wedding-render compose --ws DIR --images a.jpg b.jpg --out layouts/x.json [--base prev.json] [--passes 2]",
                    "effect": "qwen-vl 看图估布局→自审→钳制，生成布局 JSON"},
        "photoreal": {"usage": "wedding-render photoreal --ws DIR --layout layouts/x.json [--camera NAME] [--refs r.jpg ...] [--model qwen-image-3.0] [--dry-run]",
                      "effect": "照片级化到 finals/（锁布局+材质语义+风格参考）"},
        "review": {"usage": "wedding-render review --ws DIR --image finals/x.png --layout layouts/x.json",
                   "effect": "qwen-vl 四维评分卡（通过线3.5），写 <image>.review.json"},
        "tag": {"usage": "wedding-render tag --ws DIR --cases <案例图根目录> --out assets/index.csv [--only 婚策名] [--limit N]",
                "effect": "案例图 VLM 打标，断点续跑"},
        "preview": {"usage": "wedding-render preview --ws DIR --layout layouts/x.json [--open]",
                    "effect": "生成 preview.html 四栏对照页（参考图/JSON/骨架/成品）"},
        "snapshot": {"usage": "wedding-render snapshot --ws DIR --blend sessions/x.blend --base layouts/x.json --out layouts/x.overlay.json",
                     "effect": "从 Blender 会话导出增量层 overlay.json（复现三层之 L2）"},
        "rebuild": {"usage": "wedding-render rebuild --ws DIR --base layouts/x.json [layouts/x.overlay.json] [--quick]",
                    "effect": "L1参数+L2增量 一体化重建并按 cameras 渲染"},
        "setup-mcp": {"usage": "wedding-render setup-mcp --ws DIR",
                      "effect": "安装 blender-mcp 服务端+Blender addon+autostart 脚本，输出 MCP 客户端配置（交互建模必装）"},
    }, tips=[
        "管线命令均需先 init 工作区且 .env 配好 DASHSCOPE_API_KEY",
        "典型流程：compose → skeleton --quick → preview（人审）→ skeleton（正式）→ photoreal → review",
    ])


# ---------------- 入口 ----------------

def main():
    ap = argparse.ArgumentParser(prog="wedding-render")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version").set_defaults(fn=cmd_version)
    p = sub.add_parser("schema"); p.set_defaults(fn=cmd_schema)
    p = sub.add_parser("doctor"); p.add_argument("--ws", default="."); p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("setup"); p.add_argument("--agent", default="auto"); p.add_argument("--skills-dir"); p.set_defaults(fn=cmd_setup)
    p = sub.add_parser("init"); p.add_argument("--ws", default="."); p.set_defaults(fn=cmd_init)

    p = sub.add_parser("skeleton"); p.add_argument("--ws", default=".")
    p.add_argument("--layout", required=True); p.add_argument("--quick", action="store_true")
    p.add_argument("--camera", action="append"); p.set_defaults(fn=cmd_skeleton)

    p = sub.add_parser("compose"); p.add_argument("--ws", default=".")
    p.add_argument("--images", nargs="+"); p.add_argument("--out", required=True)
    p.add_argument("--base"); p.add_argument("--passes", type=int, default=2)
    p.add_argument("--validate"); p.set_defaults(fn=cmd_compose)

    p = sub.add_parser("photoreal"); p.add_argument("--ws", default=".")
    p.add_argument("--layout", required=True); p.add_argument("--camera")
    p.add_argument("--refs", nargs="+"); p.add_argument("--model")
    p.add_argument("--provider", default="dashscope"); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_photoreal)

    p = sub.add_parser("review"); p.add_argument("--ws", default=".")
    p.add_argument("--image", required=True); p.add_argument("--layout", required=True); p.set_defaults(fn=cmd_review)

    p = sub.add_parser("tag"); p.add_argument("--ws", default=".")
    p.add_argument("--cases", required=True); p.add_argument("--out", default="assets/index.csv")
    p.add_argument("--only"); p.add_argument("--limit", type=int); p.set_defaults(fn=cmd_tag)

    p = sub.add_parser("preview"); p.add_argument("--ws", default=".")
    p.add_argument("--layout", required=True); p.add_argument("--open", action="store_true"); p.set_defaults(fn=cmd_preview)
    p = sub.add_parser("snapshot"); p.add_argument("--ws", default=".")
    p.add_argument("--blend", required=True); p.add_argument("--base", required=True)
    p.add_argument("--out", required=True); p.set_defaults(fn=cmd_snapshot)

    p = sub.add_parser("setup-mcp"); p.add_argument("--ws", default="."); p.set_defaults(fn=cmd_setup_mcp)

    p = sub.add_parser("rebuild"); p.add_argument("--ws", default=".")
    p.add_argument("--base", required=True); p.add_argument("--overlay")
    p.add_argument("--quick", action="store_true"); p.set_defaults(fn=cmd_rebuild)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
