# Install Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `curl | bash` one-liner that clones reverie, syncs deps, backfills transcripts, and patches Claude Code's MCP + hook config.

**Architecture:** Single `install.sh` bash script at repo root. JSON patching uses inline Python 3 (no `jq` required). Script is idempotent — safe to re-run.

**Tech Stack:** bash, Python 3 (stdlib only), uv, git

---

### Task 1: Scaffold install.sh with preflight and clone

**Files:**
- Create: `install.sh`

- [ ] **Step 1: Create `install.sh` with preflight and clone logic**

```bash
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
```

- [ ] **Step 2: Make executable and verify preflight runs**

```sh
chmod +x install.sh
bash -c 'command -v uv && echo "uv found" || echo "uv not found"'
bash install.sh 2>&1 | head -5
```

Expected: script clones (or skips if already present) without errors.

- [ ] **Step 3: Commit**

```sh
git add install.sh
git commit -m "feat: add install.sh scaffold with preflight and clone"
```

---

### Task 2: Add dep sync and transcript backfill

**Files:**
- Modify: `install.sh`

- [ ] **Step 1: Append sync and backfill steps to `install.sh`** (add after the clone block, before the final `echo` lines)

```bash
# 3. Sync dependencies
print_step "Syncing dependencies"
uv sync --project "$INSTALL_DIR" --quiet

# 4. Backfill existing transcripts
print_step "Indexing existing transcripts"
uv run --project "$INSTALL_DIR" reverie backfill
```

- [ ] **Step 2: Run script and verify backfill output**

```sh
bash install.sh
```

Expected: lines like `==> Syncing dependencies` and `==> Indexing existing transcripts` followed by JSON like `{"indexed": N, "skipped": M, "errors": 0}`.

- [ ] **Step 3: Commit**

```sh
git add install.sh
git commit -m "feat: add dep sync and transcript backfill to install.sh"
```

---

### Task 3: Patch claude_desktop_config.json

**Files:**
- Modify: `install.sh`

- [ ] **Step 1: Append MCP config patch to `install.sh`** (add after the backfill block)

```bash
# 5. Patch MCP server config
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
```

- [ ] **Step 2: Run script and verify config was written**

```sh
bash install.sh
cat ~/.claude/claude_desktop_config.json | python3 -m json.tool
```

Expected: JSON contains `"mcpServers": { "reverie": { "command": "uv", ... } }`.

- [ ] **Step 3: Run again to verify idempotency**

```sh
bash install.sh
cat ~/.claude/claude_desktop_config.json | python3 -c "import json,sys; d=json.load(sys.stdin); assert list(d['mcpServers'].keys()).count('reverie') == 1, 'duplicate!'; print('OK - no duplicates')"
```

Expected: `OK - no duplicates`

- [ ] **Step 4: Commit**

```sh
git add install.sh
git commit -m "feat: patch claude_desktop_config.json with MCP server entry"
```

---

### Task 4: Patch settings.json with SessionEnd hook

**Files:**
- Modify: `install.sh`

- [ ] **Step 1: Append hook config patch to `install.sh`** (add after the MCP patch block)

```bash
# 6. Patch SessionEnd hook
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
```

- [ ] **Step 2: Run script and verify hook was written**

```sh
bash install.sh
cat ~/.claude/settings.json | python3 -m json.tool
```

Expected: JSON contains `"SessionEnd"` with an entry whose `command` ends in `reverie-hook.sh`.

- [ ] **Step 3: Run again to verify idempotency**

```sh
bash install.sh
python3 -c "
import json
from pathlib import Path
d = json.loads(Path('$HOME/.claude/settings.json').read_text())
cmds = [h['command'] for item in d['hooks']['SessionEnd'] for h in item.get('hooks', [])]
dupes = [c for c in cmds if cmds.count(c) > 1]
assert not dupes, f'Duplicates found: {dupes}'
print('OK - no duplicates')
"
```

Expected: `OK - no duplicates`

- [ ] **Step 4: Commit**

```sh
git add install.sh
git commit -m "feat: patch settings.json with SessionEnd hook"
```

---

### Task 5: Add summary output and update README

**Files:**
- Modify: `install.sh`
- Modify: `README.md`

- [ ] **Step 1: Append summary block to `install.sh`** (add at the end of the script)

```bash
# 7. Summary
echo ""
echo -e "${GREEN}✓ reverie installed${NC} → $INSTALL_DIR"
echo -e "${GREEN}✓ MCP server${NC}       → $CLAUDE_CONFIG"
echo -e "${GREEN}✓ SessionEnd hook${NC}  → $SETTINGS"
echo ""
echo "Restart Claude Code to activate the MCP server."
echo ""
echo "Verify with:"
echo "  uv run --project $INSTALL_DIR reverie stats"
```

- [ ] **Step 2: Run full script and confirm clean output**

```sh
bash install.sh
```

Expected: all `==>` steps print, summary prints with three green checkmarks, no errors.

- [ ] **Step 3: Add curl install command to README.md**

In `README.md`, add a new **Installation** subsection before the existing `git clone` block:

```markdown
## Installation

### One-liner

```sh
curl -fsSL https://raw.githubusercontent.com/bergerg/reverie/main/install.sh | bash
```

Installs to `~/.local/share/reverie`, configures the MCP server and `SessionEnd` hook automatically. Restart Claude Code when done.

### Manual
```

- [ ] **Step 4: Commit and push**

```sh
git add install.sh README.md
git commit -m "feat: complete install.sh with summary; update README with curl one-liner"
git push
```

---

## Verification

Full end-to-end check after all tasks:

```sh
# Fresh install simulation (remove existing if needed)
# REVERIE_INSTALL_DIR=/tmp/reverie-test bash install.sh

# Stats
uv run --project ~/.local/share/reverie reverie stats
# Expected: {"sessions": N, "messages": M, ...}

# Config checks
python3 -c "import json; d=json.load(open('$HOME/.claude/claude_desktop_config.json')); print(d['mcpServers']['reverie'])"
python3 -c "import json; d=json.load(open('$HOME/.claude/settings.json')); print(d['hooks']['SessionEnd'])"

# Restart Claude Code → confirm search_sessions appears as MCP tool
```
