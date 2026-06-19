# Fork Notice

This repository is a **fork** of
[SeemSeam/claude_codex_bridge](https://github.com/SeemSeam/claude_codex_bridge) (CCB).

It is **not** an original project. All core functionality, design, and the vast
majority of the code belong to the upstream authors. This fork only adds a small,
clearly marked behavioral change on top of upstream.

## Relationship to upstream

- **Forked from:** SeemSeam/claude_codex_bridge
- **Fork base:** v7.6.12, commit `cf036b2`
- **Fork date:** 2026-06-19
- **License:** AGPL-3.0-only (unchanged — this fork remains under the same license)

## Changes made in this fork

This fork adds a **non-invasive mode** that, by default, stops CCB from mutating
the user's tmux configuration (session theme, status bar, pane-border styling,
global mouse bindings, hooks, and `~/.tmux.conf` edits). Agents and all
collaboration features still launch and work exactly as upstream; only the tmux
*visual theming* is suppressed.

Upstream's original behavior can be restored at any time by setting the
environment variable `XB_TMUX_THEME=1`.

All modifications are additive and marked in-source with the searchable comment
`=== xbridge customization: NON-INVASIVE MODE ===`. The changed files are:

| File | Change |
|:--|:--|
| `config/ccb-tmux-on.sh` | early-exit guard (no session theming by default) |
| `config/ccb-tmux-off.sh` | early-exit guard (nothing to restore) |
| `install.sh` (`install_tmux_config`) | skip writing to `~/.tmux.conf` |
| `lib/cli/services/tmux_ui_runtime/service.py` (`apply_project_tmux_ui`) | entry guard for the Python theming path |

See `文件说明.md` for the full Chinese-language description and the
upstream-sync guide.

## AGPL-3.0 obligations

This software is licensed under AGPL-3.0-only, inherited from upstream. If you
distribute it or offer it as a network service, you must comply with the AGPL,
including making the corresponding source available. The original `LICENSE` and
upstream copyright are retained unchanged.
