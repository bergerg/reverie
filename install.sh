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

# 4. Backfill existing transcripts
print_step "Indexing existing transcripts"
uv run --project "$INSTALL_DIR" reverie backfill
