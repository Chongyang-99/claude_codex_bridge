# CCB Config Reference

## Authority Files

Effective config precedence is:

1. built-in default config from code;
2. user config at `~/.ccb/ccb.config`;
3. project config at `.ccb/ccb.config`.

Higher layers replace the whole lower-layer config; CCB does not merge partial config documents across layers.

`.ccb/ccb.config` is the highest-priority project config authority. When it is missing, CCB uses `~/.ccb/ccb.config` if present, then the built-in default. CCB does not write a new project config automatically.

The built-in default is a windows topology and includes the managed Neovim tool
window. A project that has no `.ccb/ccb.config` and no user-level config should
still start with a `neovim` tool window when the managed tool is available.

Only write `~/.ccb/ccb.config` when the user explicitly wants a user-level or system-wide default CCB team. For ordinary project setup, write `.ccb/ccb.config`.

Do not write `.ccb_config/ccb.config`. That path is legacy residue in older or migrated workspaces. You may read it as migration evidence, but the current config must be created or updated at `.ccb/ccb.config`.

`.ccb/ccb_memory.md` and `.ccb/agents/<agent>/memory.md` are workflow memory files. They are outside the normal scope of this config skill and are not layout authority.

Do not edit memory files for ordinary config design, migration, provider changes, worktree changes, or window layout changes. If the user needs persistent collaboration rules, remind them to set workflow memory separately after the config work is done.

Do not edit generated runtime state, provider-state homes, `.ccb/provider-profiles/`, `.ccb/ccbd/`, legacy `.ccb_config/`, or generated runtime memory.

## Language Rules

Use the user's language for menu text, explanations, questions, summaries,
warnings, and next-step instructions. Keep CCB syntax literal:

- TOML keys and table names stay as documented.
- Provider names, role ids, command names, env vars, and layout tokens stay
  literal.
- Agent names and window names should remain ASCII-safe identifiers unless the
  current grammar explicitly allows otherwise.
- Localized human text can be placed in `description`, `labels`, sidebar `tips`,
  or normal prose when the user wants localized display text.
- Preserve the existing language of user-authored `description`, `labels`,
  sidebar `tips`, and comments unless the user asks to translate them.

## Config Option Menu

Use this grouping when the user asks what can be configured or wants an interactive, numbered setup pass:

```text
CCB Config Options

Basic
  1. Config source
  2. Topology
  3. Windows
  4. Agents
  5. Role Pack agents
  6. Managed tools
  7. Sidebar

Agent Advanced
  8. Model
  9. API route
 10. Agent metadata

Workspace Advanced
 11. Workspace mode
 12. Shared worktree group
 13. External worktree path
 14. Branch template

Provider Startup Advanced
 15. Provider inheritance
 16. Provider env
 17. Command wrapper
 18. Startup args

Runtime Advanced
 19. Permission
 20. Restore
 21. Queue policy
 22. Watch paths
 23. Pane split percent

Output
 24. Preview TOML
 25. Apply and validate
```

Keep Basic visible for ordinary users. Treat Agent Advanced, Workspace Advanced, Provider Startup Advanced, and Runtime Advanced as opt-in controls unless the user asks for them.

When presenting this menu, translate the headings and descriptions into the
user's language while keeping the option numbers and literal field names stable.

## Compact Format

Use compact format only when the user explicitly wants a persistent `cmd` pane,
asks to keep compact syntax, or needs a tiny one-line single-window layout.
Existing compact configs remain valid, but structural edits should usually
migrate them to `[windows]`:

```text
cmd; main:codex, worker1:codex(worktree); reviewer:claude
```

Leaf tokens:

- `cmd`
- `agent:provider`
- `agent:provider(worktree)`
- `agent:provider@N` or `agent:provider(worktree)@N` when the current CCB
  version supports pane split percent hints

`cmd` is not an agent. It is the shell pane layout keyword and cannot declare a provider.

Layout operators:

- `;` splits horizontally, left to right. Think columns.
- `,` stacks vertically, top to bottom. Think rows inside a column.
- Parentheses group layout expressions.

Examples:

```text
cmd; main:codex
cmd; main:codex, reviewer:claude
cmd, main:codex; worker1:codex(worktree), reviewer:claude
cmd; main:codex, worker1:codex(worktree), worker2:claude(worktree); reviewer:claude, discuss:codex
```

Compact config requires providers on agent leaves. Bare `main` is not valid in compact config; write `main:codex`.

Pane split percent hints:

- `@N` is a layout hint on a leaf, not an agent field.
- Example: `main:codex@60; worker1:codex(worktree)@40`.
- Values are interpreted by the current layout materializer and should be treated
  as presentation hints, not agent identity or workspace policy.
- Do not add `@N` unless the current CCB version supports it.

## Workspaces

Compact workspace syntax:

```text
worker1:codex(worktree)
```

Meaning:

- no suffix: `workspace_mode = "inplace"`;
- `(worktree)`: `workspace_mode = "git-worktree"`.

`git-worktree` requires the project root to be a git repository. If the project is not a git repository, ask before using isolation. Do not silently replace it with copy mode.

`workspace_mode = "copy"` is available only in rich TOML and should be used only when explicitly requested.

Worktree branch naming can be customized with `branch_template`, but do not set it by default. Supported variables are `{agent_name}`, `{project_slug}`, and `{date}`. The default branch template is `ccb/{agent_name}`.

Rich or hybrid TOML can pin a worktree to a specific external path:

```toml
[agents.worker1]
workspace_mode = "git-worktree"
workspace_path = "/home/user/project-worktrees/worker1"
```

Semantics:

- `workspace_path` requires `workspace_mode = "git-worktree"`;
- CCB validates the path as an external worktree but does not create, delete,
  copy, prune, or switch branches there;
- use this only when the user provides the path or clearly asks for a specific
  existing workspace.

Rich or hybrid TOML can intentionally share one CCB-managed worktree across
multiple agents:

```toml
[agents.worker1]
workspace_mode = "git-worktree"
workspace_group = "build"

[agents.worker2]
workspace_mode = "git-worktree"
workspace_group = "build"
```

Semantics:

- `workspace_group` requires `workspace_mode = "git-worktree"`;
- agents in the same group share `.ccb/workspaces/groups/<group>`;
- the group uses branch `ccb/group/<group>`;
- use this when the user wants multiple agents to collaborate in the same
  managed worktree;
- `workspace_path`, `workspace_group`, `workspace_root`, and `branch_template`
  must not be mixed for the same agent.

Per-agent workspace controls belong under `[agents.<name>]` overlays. Keep the
layout leaf focused on provider and the simple `(worktree)` marker:

```toml
[windows]
work = "builder:codex(worktree), tester:codex(worktree)"

[agents.builder]
workspace_group = "build"

[agents.tester]
workspace_path = "/home/user/project-worktrees/tester"
```

## Hybrid Format

Use hybrid format when the compact single-window layout is enough but one or more agents need extra fields. Hybrid configs without `[windows]` also remain single-window configs:

```toml
cmd; main:codex, worker1:codex(worktree); reviewer:claude

[agents.main]
description = "Primary Codex agent."
model = "gpt-5"

[agents.reviewer]
description = "Review/check agent."
```

The compact header owns:

- layout;
- `default_agents`;
- `cmd_enabled`;
- agent `provider`;
- agent `workspace_mode`.

Hybrid overlay rules:

- only `[agents.<name>]` tables are allowed;
- each overlay agent must already exist in the compact header;
- overlay must not redefine `provider` or `workspace_mode`;
- use overlay for fields such as `model`, `key`, `url`, `description`, `labels`, `startup_args`, `provider_profile`, `permission`, `restore`, `queue_policy`, `branch_template`, and `watch_paths`.

## Explicit Windows Topology

Use windows topology by default for new CCB configs and for structural
migrations. It supports named tmux windows, per-window agent grouping, tool
windows, and native sidebar layout:

```toml
version = 2
entry_window = "main"

[windows]
main = "main:codex"
work = "worker1:codex(worktree), worker2:codex(worktree), worker3:claude(worktree)"
review = "reviewer:claude, discuss:codex"

[tool_windows.neovim]
command = "ccb-nvim"
label = "neovim"

[ui.sidebar]
mode = "every_window"
width = "15%"
bottom_height = 20

[ui.sidebar.view]
agents_height = "33%"
comms_limit = 5
comms_compact = true
tips_enabled = true
tips = [
  "C-b d  detach",
  "C-b h/j/k/l pane",
  "C-b H/J/K/L resize",
  "C-b o  next pane",
  "C-b z  zoom",
  "C-b w  tree",
  "C-b n/p next/prev",
  "C-b 0-9 jump win",
  "C-b [  copy mode",
  "copy: PgUp/PgDn",
  "copy: v select",
  "copy: y yank",
  "copy: q exit",
  "C-b ]  paste",
  "C-b c  new win",
  "C-b ,  rename",
  "C-b ?  keys",
]
```

Rules:

- Only `[windows]` enables windows topology. Prefer rewriting an existing
  compact/hybrid config into `[windows]` when making topology, roster, role, or
  workspace changes unless the user wants compact/cmd preserved.
- `[windows]` owns layout and the effective configured-agent set.
- Each configured agent must appear in exactly one window layout.
- Window layout leaves must declare providers: `agent:provider` or `agent:provider(worktree)`.
- `cmd` is not supported inside `[windows]` topology. Use compact/hybrid config when a persistent command pane is required.
- Do not combine windows topology with `default_agents`, `layout`, or `cmd_enabled`.
- `entry_window` is optional; it defaults to the first window.
- `[tool_windows.<name>]` can define managed tool windows such as `neovim`.
  When writing a new or migrated windows topology, include
  `[tool_windows.neovim]` with `command = "ccb-nvim"` by default unless the user
  asks to disable it. To disable Neovim, omit or remove that block; do not write
  `enabled = false`.
- `[ui.sidebar]` is optional. Defaults are `mode = "every_window"`, `width = "15%"`, and `bottom_height = 20`.
- Agent leaves provide default provider and workspace mode. Same-name `[agents.<name>]` tables are overlays; they may override fields such as `workspace_mode`, and the provider there must match the provider in `[windows]` if it is repeated.
- `[agents.<name>]` tables for names no longer present in `[windows]` are ignored as stale overlay residue.
- `[ui.sidebar.view]` is optional and UI-only. It can tune sidebar tree height, Comms visible row count/compactness, and short Tips text without changing the managed window topology.

Single-window windows topology is valid when the user wants modern config
without a persistent `cmd` pane:

```toml
version = 2
entry_window = "main"

[windows]
main = "main:codex, worker1:codex(worktree), reviewer:claude"

[tool_windows.neovim]
command = "ccb-nvim"
label = "neovim"
```

## Role Pack Agents

CCB can bind installed Role Packs into project config. New configs must use
canonical catalog role ids. For the architecture reviewer role, use
`agentroles.archi`; do not write `ccb.archi` in new config.

Preferred shorthand:

```toml
version = 2
entry_window = "main"

[windows]
main = "main:codex, agentroles.archi:codex"
```

Equivalent explicit binding:

```toml
version = 2
entry_window = "main"

[windows]
main = "main:codex, archi:codex"

[agents.archi]
role = "agentroles.archi"
provider = "codex"
```

Semantics:

- `agentroles.archi` is the stable Role Pack id from the external
  `agent-roles-spec` catalog.
- `archi` is the project-local agent name and the normal ask target.
- Sidebar, pane labels, and primary commands use `archi`.
- Role diagnostics and install commands use `agentroles.archi`.
- `ccb.archi` is a legacy input alias only. When migrating old config, rewrite
  it to `agentroles.archi`.

Common commands:

```bash
ccb roles install agentroles.archi
ccb roles doctor agentroles.archi
ccb roles add agentroles.archi:codex
ccb ask archi "review this change"
```

Do not copy Role Pack memory or skills into `.ccb` by hand. CCB projects role
assets from the installed role store into the bound provider home.

Do not write role store paths such as `~/.roles` or
`$XDG_DATA_HOME/ccb/roles` into config. `.ccb/ccb.config` records the canonical
role id; package storage is resolved by CCB and the Agent Roles package
manager.

Role package install/update uses the Agent Roles `.roles/installed` store by
default. Existing legacy `$XDG_DATA_HOME/ccb/roles` installs are migration input
only; do not preserve legacy store paths in config.

## Migrating Old Configs To Windows

Old compact and hybrid configs are still valid single-window configs. When the
user asks for topology, roster, role, workspace, sidebar, or modernization
changes, recommend migrating them to windows topology by default. Preserve
compact/hybrid only when the user wants a persistent `cmd` pane or explicitly
asks to keep compact syntax.

Migration rules:

- ask one concise target-shape question when needed: confirm windows migration,
  window grouping, workspace sharing, and whether `cmd` must be preserved;
- preserve agent names, providers, worktree markers, and ordering unless the user asks to redesign roles;
- preserve TOML overlay fields by moving them under the same `[agents.<name>]` table after `[windows]`;
- leave memory files untouched; workflow memory is configured separately from `.ccb/ccb.config`;
- remove `cmd` from the migrated layout because `[windows]` does not support the persistent command pane;
- choose concise window names such as `main`, `work`, `review`, `research`, or `ops`;
- keep each agent in exactly one window;
- keep compact/hybrid format only if the requested change is a single-window
  pane rearrangement and the user wants `cmd`/compact preserved.

Compact to windows example:

```text
cmd; main:codex, worker1:codex(worktree), worker2:claude(worktree); reviewer:claude
```

becomes:

```toml
version = 2
entry_window = "main"

[windows]
main = "main:codex"
work = "worker1:codex(worktree), worker2:claude(worktree)"
review = "reviewer:claude"
```

Example with an override:

```toml
version = 2

[windows]
main = "main:codex"
work = "worker1:codex(worktree)"

[agents.worker1]
model = "gpt-5"
description = "Implements coherent code changes in an isolated git worktree."
```

## Legacy Rich TOML

Use legacy rich TOML only when compact/hybrid or windows topology cannot express the request, for example explicit `workspace_mode = "copy"`:

```toml
version = 2
default_agents = ["main", "worker1"]
cmd_enabled = true
layout = "cmd; main, worker1"

[agents.main]
provider = "codex"
target = "."
workspace_mode = "inplace"
restore = "auto"
permission = "manual"

[agents.worker1]
provider = "codex"
target = "."
workspace_mode = "copy"
restore = "auto"
permission = "manual"
```

## Provider And Model Fields

Default behavior should inherit provider credentials/config from the user's normal provider home.

Use `key` and `url` only when the user explicitly wants an agent-local API route. These shortcuts are supported for `codex`, `claude`, and `gemini`.

Use `model` only when the user wants a provider model override. Model shortcuts are supported for `codex`, `claude`, `gemini`, and `opencode`.

Do not mix `key` or `url` with provider API env fields under `agents.<name>.env` or `agents.<name>.provider_profile.env`.

Use `provider_profile` only for advanced inheritance or environment behavior. Do not create `.ccb/provider-profiles/` directories manually.

Use `startup_args` for provider-native trailing arguments that belong inside
CCB's generated provider command:

```toml
[agents.research]
startup_args = ["--search"]
```

Use `provider_command_template` only when an agent needs a shell wrapper around
the generated provider command that cannot be represented as `startup_args`:

```toml
[agents.builder]
provider_command_template = "sandbox=1 {command} omx --madmax"
```

Semantics:

- the template must contain exactly one `{command}`;
- CCB first generates the normal provider command segment, including managed
  provider arguments, `startup_args`, and resume flags;
- CCB then replaces `{command}` with that provider command segment;
- the template wraps only the provider command segment, not CCB's env prefix,
  managed provider home exports, caller context, or shell setup;
- do not use this field to replace CCB's generated command or manually encode
  resume behavior.
- when both fields are present, `startup_args` are part of the generated
  `{command}` segment before the template wrapper is applied.

## Skill Inheritance

CCB config supports provider source-home inheritance flags:

```toml
[agents.worker1.provider_profile]
inherit_skills = true
inherit_commands = true
inherit_memory = true
```

These fields only toggle provider source-home inheritance. This skill must not install skills, copy skills into provider homes, write provider-state paths, or perform one-agent temporary skill injection. If the user wants durable skill installation, route that as a separate skill/install task.

## Agent Names

Agent names must match:

```text
^[a-zA-Z][a-zA-Z0-9_-]{0,31}$
```

Names are normalized to lowercase.

Reserved names include:

```text
all, from, user, system, ask, cancel, pend, ping, watch, kill, ps, logs, doctor, config, cmd, version, update, help
```

Prefer role names over generic names:

- `main`
- `worker1`, `worker2`
- `reviewer`
- `discuss`
- `research`
- `qa`
- `docs`

## Common Topologies

Light engineering team, windows-first:

```toml
version = 2
entry_window = "main"

[windows]
main = "main:codex"
work = "worker1:codex(worktree)"
review = "reviewer:claude"

[tool_windows.neovim]
command = "ccb-nvim"
label = "neovim"
```

Full parallel team:

```toml
version = 2
entry_window = "main"

[windows]
main = "main:codex"
work = "worker1:codex(worktree), worker2:codex(worktree), worker3:claude(worktree)"
review = "reviewer:claude, discuss:codex"

[tool_windows.neovim]
command = "ccb-nvim"
label = "neovim"
```

Full parallel team with native sidebars and the default Neovim tool window:

```toml
version = 2
entry_window = "main"

[windows]
main = "main:codex"
work = "worker1:codex(worktree), worker2:codex(worktree), worker3:claude(worktree)"
review = "reviewer:claude, discuss:codex"

[tool_windows.neovim]
command = "ccb-nvim"
label = "neovim"
```

Multi-provider research and implementation:

```toml
version = 2
entry_window = "main"

[windows]
main = "main:codex"
work = "builder:codex(worktree)"
research = "research:gemini"
review = "reviewer:claude"

[tool_windows.neovim]
command = "ccb-nvim"
label = "neovim"
```

Two Codex agents with different explicit API routes:

```toml
version = 2
entry_window = "main"

[windows]
main = "fast:codex, deep:codex"

[agents.fast]
key = "sk-fast..."
model = "gpt-5-mini"

[agents.deep]
key = "sk-deep..."
url = "https://api.example.com/v1"
model = "gpt-5"
```

Never include real secrets in public repositories.
