# reverie CLI on PATH Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `reverie` available as a global CLI command after running `install.sh`, without requiring `uv run --project ...` prefixes.

**Architecture:** Add `uv tool install --reinstall "$INSTALL_DIR"` to `install.sh` between the `uv sync` step and the backfill step. uv manages the tool binary in its own bin dir (`~/.local/bin`) which it already adds to PATH during its own installation. Update the summary output to reflect the new command availability.

**Tech Stack:** bash, uv

---

### Task 1: Add `uv tool install` step to `install.sh`

**Files:**
- Modify: `install.sh:35-39`

- [ ] **Step 1: Add the tool install step**

Open `install.sh`. After the `uv sync` block (line 35-36) and before the backfill block (line 38-39), insert a new step:

The file currently reads:
```bash
# 3. Sync dependencies
print_step "Syncing dependencies"
uv sync --project "$INSTALL_DIR" --quiet

# 4. Backfill existing transcripts
```

Change it to:
```bash
# 3. Sync dependencies
print_step "Syncing dependencies"
uv sync --project "$INSTALL_DIR" --quiet

# 4. Install reverie CLI tool
print_step "Installing reverie CLI"
uv tool install --reinstall "$INSTALL_DIR"

# 5. Backfill existing transcripts
```

Renumber all subsequent step comments (`# 4.` → `# 5.`, `# 5.` → `# 6.`, `# 6.` → `# 7.`, `# 7.` → `# 8.`).

- [ ] **Step 2: Verify the script is syntactically valid**

Run:
```bash
bash -n install.sh
```
Expected: no output (exit 0).

- [ ] **Step 3: Commit**

```bash
git add install.sh
git commit -m "feat: install reverie CLI via uv tool install in install.sh"
```

---

### Task 2: Update summary output in `install.sh`

**Files:**
- Modify: `install.sh` (summary block, currently lines ~108-117)

- [ ] **Step 1: Add CLI line to the summary block**

The summary block currently reads:
```bash
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

Replace it with:
```bash
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
```

- [ ] **Step 2: Verify syntax**

Run:
```bash
bash -n install.sh
```
Expected: no output (exit 0).

- [ ] **Step 3: Commit**

```bash
git add install.sh
git commit -m "feat: update install.sh summary to show reverie CLI path and direct commands"
```
