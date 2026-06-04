# Spec-Owned Roles Store First Slice

Date: 2026-06-04

## Scope

This checkpoint records the first executable bridge from CCB-owned Role Pack
payload management toward a spec-owned `agent-roles` package manager and
`.roles/installed` store.

## Implemented

- `agent-roles-spec` provides a preview Python CLI/package named
  `agent-roles`.
- The preview CLI owns `.roles/installed` role payload writes and stable JSON
  output for package operations.
- The preview alias table maps `ccb.archi` to `agentroles.archi`.
- CCB reads both legacy `$XDG_DATA_HOME/ccb/roles` and spec-owned
  `.roles/installed` stores for config loading, runtime projection, lock
  lookup, role status, and catalog status.
- CCB can delegate `roles install`, `roles update`, and `roles sync` payload
  operations to `agent-roles` when `CCB_AGENT_ROLES_MANAGER=1`.
- CCB wraps `agent-roles` missing executable, exec failure, timeout, nonzero
  JSON error, and non-JSON failure paths as Role Pack errors so the CLI emits
  `roles_status: failed` without traceback.

## Validation

- `agent-roles-spec`: `3 passed`
- CCB `test/test_rolepacks.py`: `48 passed`
- CCB targeted Role Pack/update/source guard/repo hygiene suite: `99 passed`
- CCB compileall for touched runtime modules: passed
- CCB and `agent-roles-spec` `git diff --check`: passed
- Real isolated `ccb_test` smoke proved:
  - `ccb roles install ccb.archi --skip-tools` can call `agent-roles` and write
    `.roles/installed/agentroles.archi`.
  - `ccb roles show ccb.archi` resolves the spec-owned store snapshot as
    canonical `agentroles.archi`.

## Release Position

This slice is releaseable only as an opt-in preview. It is not ready to become
the default CCB Role Pack payload path because installed `agent-roles` version
gating, migration from existing CCB stores, and final architecture review are
not complete.

## Residual Risks

- A globally installed incompatible `agent-roles` command could return an
  unexpected JSON schema if CCB enables the manager without version checks.
- Dual-store lookup must keep old project locks resolving old content-addressed
  snapshots until a deliberate migration exists.
- Tool hook execution remains CCB-owned; the package manager writes role
  payloads but does not decide CCB required/optional tool policy.
