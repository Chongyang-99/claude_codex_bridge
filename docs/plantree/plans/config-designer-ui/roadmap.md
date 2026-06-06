# Config Designer UI Roadmap

Date: 2026-06-06

## Done

- Confirmed current config authority is complete replacement by source layer:
  built-in default, then user config, then project config.
- Confirmed current built-in default already includes a managed Neovim tool
  window.
- Confirmed current `ccb-config` skill already prefers `version = 2`
  `[windows]` topology.
- Updated inherited `ccb-config` skill sources so generated windows topology
  includes `[tool_windows.neovim]` by default.
- Cleaned the inherited `ccb-config` skill scope so it is config-only, shows a
  numbered option menu, and treats workflow memory as a separate follow-up.
- Reorganized the config option menu into Basic, Agent Advanced, Workspace
  Advanced, Provider Startup Advanced, Runtime Advanced, and Output groups.
- Documented that the built-in no-config default includes the managed Neovim
  tool window.
- Added language-following rules so `ccb-config` presents menus, questions, and
  explanations in the user's language while keeping CCB syntax literal.

## In Progress

- Validate the config skill cleanup against the inherited Codex and Claude
  copies and keep the staged UI plan aligned.

## Next

1. Dogfood the cleaned `ccb-config` skill on a representative config migration.
2. Design and implement `ccb config ui`:
   - local-only browser UI;
   - current config loading and draft editing;
   - TOML preview, diff, validation, and apply.
3. Add sidebar config icon only after `ccb config ui` is usable:
   - right-side icon in the tree header;
   - launch the same CLI command;
   - show fallback URL/status in the sidebar when browser open fails.

## Deferred

- Remote/shared configuration UI.
- Full drag-and-drop layout designer.
- Import/export of reusable team presets.
- Provider credential vault integration.
- Applying runtime reload directly from the first UI slice.
- Editing project workflow memory from the config UI.

## Phase Gates

Phase 1 is complete when:

- `ccb-config` skill can list supported config knobs clearly.
- The skill writes only `.ccb/ccb.config` or an explicitly requested
  `~/.ccb/ccb.config`; workflow memory remains a separate follow-up.
- Generated windows topology includes the managed Neovim tool window by
  default and validates with the current loader.

Phase 2 is complete when:

- `ccb config ui` opens a local browser editor on `127.0.0.1`.
- The editor can load, preview, validate, and apply `.ccb/ccb.config`.
- Apply shows a diff and validation result before writing.

Phase 3 is complete when:

- The sidebar shows a config icon without adding text buttons.
- Clicking the icon launches `ccb config ui` or displays a fallback URL.
- Existing sidebar restart and kill controls keep their current behavior.
