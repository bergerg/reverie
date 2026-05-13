# reverie CLI on PATH

**Date:** 2026-05-13

## Problem

Running `reverie stats` or `reverie usage` requires the full invocation
`uv run --project $INSTALL_DIR reverie <subcommand>`, which is too verbose for
day-to-day use.

## Goal

After running `install.sh`, users can run `reverie stats` and `reverie usage`
(and any other subcommand) directly from any shell without a `uv run` prefix.

## Approach

Use `uv tool install` to register reverie as a managed uv tool. This:

- Places the binary in `~/.local/bin/reverie` (managed by uv).
- Requires no PATH configuration — uv already ensures its bin dir is on PATH
  when it is installed.
- Is idempotent via `--reinstall`: re-running `install.sh` after an update
  replaces the old binary.

## Changes

### `install.sh`

Add step 3.5 between `uv sync` and `backfill`:

```bash
# 3.5. Install reverie as a uv-managed tool
print_step "Installing reverie CLI"
uv tool install --reinstall "$INSTALL_DIR"
```

Update the summary block:

```
✓ reverie CLI  → $(uv tool dir)/reverie/bin/reverie
```

Replace the "Verify with:" snippet:

```
# before
uv run --project $INSTALL_DIR reverie stats

# after
reverie stats
reverie usage
```

### No other changes

`pyproject.toml` already declares the `reverie = "reverie.cli:main"` entrypoint,
which is all `uv tool install` needs.

## Non-goals

- No new subcommands or combined dashboard view.
- No changes to Python source.
