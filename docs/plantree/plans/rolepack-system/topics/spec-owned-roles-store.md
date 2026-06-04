# Spec-Owned Roles Store Boundary

Date: 2026-06-04

## Objective

Define the target split where `agent-roles-spec` owns reusable role package
management and CCB consumes resolved role packages for project runtime
integration.

This topic refines the earlier CCB-first implementation without deleting the
current implementation snapshot in
[current-roles-management-scheme.md](current-roles-management-scheme.md).

## Target Authority Split

`agent-roles-spec` owns role package state:

- the system-level `.roles` store or equivalent XDG-backed store
- catalog clone/cache state for `https://github.com/SeemSeam/agent-roles-spec`
- role package list, install, update, sync, doctor, repair, and metadata
- content digest, version, provenance, and source records
- role id aliases and migrations such as `ccb.archi -> agentroles.archi`
- package validation, schema compatibility, and contribution gates

CCB owns CCB runtime state:

- `.ccb/ccb.config`
- `.ccb/role-lock.json`
- provider home projection and cleanup
- CCB adapter policy for tool hooks, prompts, i18n output, and required
  failure semantics
- CCB update sequencing around old and new entrypoints
- ask/sidebar/reload/diagnostic behavior for mounted agents

The practical rule is: `.roles` is package-manager state; `.ccb` is project
runtime state.

## Store Model

The target store should be described by `agent-roles-spec`, not CCB:

```text
~/.roles/
  catalogs/
    agent-roles-spec/
      .git/
      roles/
      reference_roles/
  installed/
    agentroles.archi/
      current -> versions/0.2.0/<digest>/
      install.json
      versions/
        0.2.0/<digest>/
          role.toml
          memory.md
          adapters/
          skills/
          tools/
```

The exact path is still an open design point. The important ownership rule is
that CCB does not define the package store schema as a private CCB runtime
detail.

CCB may keep a compatibility bridge from the current
`$XDG_DATA_HOME/ccb/roles/` store while the spec-owned store is introduced.
Project locks must keep resolving old installed snapshots until a deliberate
migration path exists.

## Agent Roles Tool Contract

The spec project should expose a stable tool or library boundary. CCB should be
able to call it without importing CCB runtime modules.

Minimum operations:

```bash
agent-roles sync .
agent-roles list --json
agent-roles install agentroles.archi --json
agent-roles update agentroles.archi --json
agent-roles doctor agentroles.archi --json
agent-roles resolve agentroles.archi --json
```

The JSON contract should include:

- canonical role id
- accepted legacy aliases
- version and digest
- installed path
- source kind and source path
- adapter compatibility
- declared tool hooks and permissions
- warning and failure diagnostics with stable codes

CCB should treat this as a package-manager API. It should not parse human
output or depend on transient filesystem implementation details beyond the
resolved installed path and metadata.

## CCB Wrapper Behavior

CCB keeps user-facing commands where they are already part of CCB workflows:

```bash
ccb roles list
ccb roles sync
ccb roles install agentroles.archi
ccb roles update agentroles.archi
ccb roles doctor agentroles.archi
ccb roles add agentroles.archi:codex
```

For package operations, CCB delegates to the spec-owned package manager and
then adds CCB-specific behavior:

- enforce CCB post-update required/optional failure policy
- run or validate CCB adapter hooks according to CCB policy
- write project config and role locks for `roles add`
- project role memory, skills, prompts, and plugins into provider homes
- report project lock drift and runtime projection diagnostics

`ccb roles add` remains CCB-owned because it mutates `.ccb/ccb.config` and
`.ccb/role-lock.json`.

## Migration Sequence

1. Specify the `agent-roles` package-manager CLI/API and `.roles` metadata in
   `agent-roles-spec`.
2. Add a compatibility command in CCB that can read both the current
   `$XDG_DATA_HOME/ccb/roles/` store and the new spec-owned store.
3. Move catalog sync and same-id role payload update logic behind the
   spec-owned tool/API.
4. Make `ccb roles list/install/update/sync/doctor` call the spec-owned
   package operations for payload work while preserving existing CCB output and
   i18n behavior.
5. Keep CCB project locks stable by recording the resolved digest and installed
   path returned by the spec-owned package manager.
6. Add migration tests for existing v7.2.x installs, including legacy
   `ccb.archi` metadata and stale source paths.
7. Only after compatibility is proven, stop writing new role payloads into the
   CCB-private role store.

## Non-Goals

- Do not move `.ccb/ccb.config` or `.ccb/role-lock.json` into
  `agent-roles-spec`.
- Do not let `agent-roles-spec` manage provider sessions, auth, tmux panes,
  mailbox state, or CCB lifecycle files.
- Do not make CCB startup depend on network access to resolve a mounted role.
- Do not silently update project locks when the package store updates.

## Risks

- A subprocess-only package manager may make errors harder to type-check unless
  the JSON protocol is strict and versioned.
- A library API may tempt CCB runtime paths to import management code; import
  boundary tests remain required.
- A dual-store migration can confuse users unless diagnostics clearly show
  whether a role came from the legacy CCB store or the spec-owned store.
- Tool hook ownership must stay explicit: role packages declare hooks, but CCB
  decides whether running them is allowed or required in a CCB update/install
  context.
- Preview delegation currently leaves `ccb roles sync --with-tools` on the
  legacy CCB path; the default-on design must make package sync and CCB tool-hook
  policy compose without losing the spec-owned store.
- The manager JSON contract should fail closed when `roles` or other structured
  fields have unexpected types, rather than collapsing malformed payloads into an
  apparently empty result.
- Development-only source checkout discovery must not become a stable production
  dependency. Released CCB should prefer `AGENT_ROLES_CLI`, `agent-roles` on
  `PATH`, an installed Python package, or an explicit `AGENT_ROLES_SPEC_HOME`.
