#!/bin/bash
# Install session-continuity-mcp skills for Claude Code
# Symlinks skill directories into ~/.claude/skills/ so they're available as /sesh:briefing, /sesh:intent, /sesh:done

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"
TARGET_DIR="$HOME/.claude/skills"

mkdir -p "$TARGET_DIR"

for skill_dir in "$SKILLS_DIR"/sesh-*; do
    skill_name="$(basename "$skill_dir")"
    target="$TARGET_DIR/$skill_name"
    if [ -L "$target" ]; then
        echo "  skip: $skill_name (already symlinked)"
    elif [ -d "$target" ]; then
        echo "  skip: $skill_name (directory exists — not overwriting)"
    else
        ln -s "$skill_dir" "$target"
        echo "  link: $skill_name -> $skill_dir"
    fi
done

echo ""
echo "Installed skills:"
for skill_dir in "$SKILLS_DIR"/sesh-*; do
    skill_name="$(basename "$skill_dir")"
    echo "  /$(echo "$skill_name" | sed 's/-/:/') — $(head -3 "$skill_dir/SKILL.md" | grep 'name:' | sed 's/.*name: //')"
done

echo ""
echo "Usage in Claude Code:"
echo "  /sesh:briefing  — get session context at start"
echo "  /sesh:intent    — record what you'll work on"
echo "  /sesh:done      — wrap up session, mark items complete"
