#!/usr/bin/env bash
# 从 .agents/skills 同步能力脚本与技能族到 CLI 包内（发布前运行）
set -e
cd "$(dirname "$0")"
rm -rf src/wedding_render/scripts src/wedding_render/skills src/wedding_render/assets
mkdir -p src/wedding_render/scripts src/wedding_render/skills src/wedding_render/assets
cp ../.agents/skills/scene-skeleton/scripts/{layout.py,compose_layout.py,contact_sheet.py,qwenvl.py,snapshot.py,apply_overlay.py,rebuild_runner.py} src/wedding_render/scripts/
cp ../.agents/skills/photoreal-render/scripts/{photoreal.py,review.py,qwenvl.py} src/wedding_render/scripts/photoreal_render/ 2>/dev/null || {
  mkdir -p src/wedding_render/scripts/photoreal_render
  cp ../.agents/skills/photoreal-render/scripts/{photoreal.py,review.py,qwenvl.py} src/wedding_render/scripts/photoreal_render/
}
cp -R ../.agents/skills/scene-skeleton ../.agents/skills/photoreal-render src/wedding_render/skills/
find src/wedding_render/skills -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
cp ../.agents/skills/scene-skeleton/assets/layouts/seed_scene.json src/wedding_render/assets/
cp ../.agents/skills/scene-skeleton/assets/autostart_mcp.py src/wedding_render/assets/
cp ../.agents/skills/scene-skeleton/assets/autostart_mcp.py src/wedding_render/assets/
echo "synced."
