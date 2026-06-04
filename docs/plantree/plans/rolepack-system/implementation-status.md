# Role Pack System Implementation Status

Date: 2026-06-04

## Current Phase

Spec-owned `.roles` package-manager bridge, preview/opt-in slice.

## Done This Phase

- `agent-roles-spec` now has a preview `agent-roles` package manager with JSON
  `list`, `install`, `update`, `sync`, `doctor`, and `resolve` commands.
- `agent-roles-spec` records the legacy alias
  `ccb.archi -> agentroles.archi`.
- CCB runtime/config lookup can read both the legacy
  `$XDG_DATA_HOME/ccb/roles` store and spec-owned
  `AGENT_ROLES_STORE` / `~/.roles/installed`.
- CCB role package operations can delegate to `agent-roles` when
  `CCB_AGENT_ROLES_MANAGER=1`.
- The `agent-roles` subprocess bridge now reports missing CLI, exec failures,
  timeouts, nonzero JSON errors, and non-JSON failures through the normal
  `roles_status: failed` CLI channel instead of leaking tracebacks.
- `ccb-config` skill docs say configs must keep canonical role ids and must not
  write local store paths such as `~/.roles` into `.ccb/ccb.config`.

## Active TODO

1. Keep `CCB_AGENT_ROLES_MANAGER=1` as opt-in until the installed
   `agent-roles` version and JSON protocol are release-gated.
2. Keep `ccb roles sync --with-tools` on the follow-up list: the preview manager
   bridge delegates sync only when CCB is not also running tool hooks.
3. Tighten the sync JSON payload contract before default-on so malformed
   `roles` values cannot be silently treated as an empty result.
4. Remove or dev-gate the source-checkout fallback for `~/yunwei/agent-roles-spec`
   before the bridge graduates from preview.
5. Add review coverage for import boundaries so provider startup cannot import
   package-manager subprocess or network-capable code.
6. Decide whether CCB should install/refresh `agent-roles` during `ccb update`
   or only consume an already-installed tool.
7. Define the dual-store migration command from `$XDG_DATA_HOME/ccb/roles` to
   `.roles/installed`.

## Blockers

- None for an opt-in preview release.
- Default-on release is blocked on installed-tool version gating, migration
  policy, and review.

## Next Commit Target

Commit only the Role Pack / Agent Roles bridge files and plan-tree updates.
Do not include unrelated ask/runtime dirty files currently present in the
worktree.

## Last Verified Commands

- In `agent-roles-spec`: `python -m pytest -q`
- In `agent-roles-spec`: `python -m compileall -q agent_roles`
- In `agent-roles-spec`: `git diff --check`
- In `ccb_source`: `python -m pytest -q test/test_rolepacks.py`
- In `ccb_source`: `python -m pytest -q test/test_rolepacks.py test/test_cli_management_update.py test/test_repo_hygiene.py test/test_source_runtime_guard.py`
- In `ccb_source`: `python -m compileall -q lib/agents/config_loader_runtime/role_lookup.py lib/rolepacks/runtime_lookup.py lib/rolepacks/sources.py lib/rolepacks/service.py lib/rolepacks/agent_roles_manager.py`
- In `ccb_source`: `git diff --check`
- In `/home/bfly/yunwei/test_ccb2`: isolated `ccb_test roles install ccb.archi --skip-tools` with `CCB_AGENT_ROLES_MANAGER=1` and `AGENT_ROLES_CLI` pointing at `agent-roles-spec/cli/agent-roles`, followed by `ccb_test roles show ccb.archi`.
