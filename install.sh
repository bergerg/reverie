#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${REVERIE_INSTALL_DIR:-$HOME/.local/share/reverie}"
REPO_URL="https://github.com/bergerg/reverie"

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
print_step()  { echo -e "${GREEN}==>${NC} $1"; }
print_error() { echo -e "${RED}Error:${NC} $1" >&2; }

# 1. Preflight
if ! command -v uv &>/dev/null; then
    print_error "uv is not installed."
    print_error "Install it from: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

if ! command -v git &>/dev/null; then
    print_error "git is not installed."
    exit 1
fi

# 2. Clone or update
if [ -d "$INSTALL_DIR/.git" ]; then
    print_step "Updating existing install at $INSTALL_DIR"
    git -C "$INSTALL_DIR" pull --ff-only
else
    print_step "Installing reverie to $INSTALL_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# 3. Sync dependencies
print_step "Syncing dependencies"
uv sync --project "$INSTALL_DIR" --quiet

# 4. Install reverie CLI tool
print_step "Installing reverie CLI"
uv tool install --reinstall "$INSTALL_DIR"

# 5. Backfill existing transcripts
print_step "Indexing existing transcripts"
uv run --project "$INSTALL_DIR" reverie backfill

# 6. Patch MCP server config
CLAUDE_CONFIG="$HOME/.claude/claude_desktop_config.json"
print_step "Configuring MCP server in $CLAUDE_CONFIG"
python3 - "$INSTALL_DIR" "$CLAUDE_CONFIG" <<'PYEOF'
import json, sys
from pathlib import Path

install_dir, config_path = sys.argv[1], sys.argv[2]
path = Path(config_path)
path.parent.mkdir(parents=True, exist_ok=True)

config = {}
if path.exists():
    try:
        config = json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"  Warning: could not parse {path}, starting fresh", file=sys.stderr)

config.setdefault("mcpServers", {})
config["mcpServers"]["reverie"] = {
    "command": "uv",
    "args": ["run", "--project", install_dir, "reverie", "serve"]
}
path.write_text(json.dumps(config, indent=2) + "\n")
print(f"  Written: {path}")
PYEOF

# 7. Patch SessionEnd hook
SETTINGS="$HOME/.claude/settings.json"
print_step "Configuring SessionEnd hook in $SETTINGS"
python3 - "$INSTALL_DIR" "$SETTINGS" <<'PYEOF'
import json, os, sys
from pathlib import Path

install_dir, settings_path = sys.argv[1], sys.argv[2]
hook_cmd = os.path.join(install_dir, "bin", "reverie-hook.sh")
path = Path(settings_path)
path.parent.mkdir(parents=True, exist_ok=True)

config = {}
if path.exists():
    try:
        config = json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"  Warning: could not parse {path}, starting fresh", file=sys.stderr)

config.setdefault("hooks", {})
config["hooks"].setdefault("SessionEnd", [])

# Idempotent: only add if this hook command isn't already present
existing = config["hooks"]["SessionEnd"]
already_present = any(
    any(h.get("command") == hook_cmd for h in item.get("hooks", []))
    for item in existing
    if isinstance(item, dict)
)
if not already_present:
    existing.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": hook_cmd}]
    })

path.write_text(json.dumps(config, indent=2) + "\n")
print(f"  Written: {path}")
PYEOF

# 8. Summary
echo ""
echo -e "${GREEN}✓ reverie installed${NC} → $INSTALL_DIR"
echo -e "${GREEN}✓ reverie CLI${NC}       → $(uv tool dir)/reverie/bin/reverie"
echo -e "${GREEN}✓ MCP server${NC}        → $CLAUDE_CONFIG"
echo -e "${GREEN}✓ SessionEnd hook${NC}   → $SETTINGS"
echo ""
echo "Restart Claude Code to activate the MCP server."
echo ""
echo "Verify with:"
echo "  reverie stats"
echo "  reverie usage"
