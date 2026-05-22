# ccb-agent-sidebar

CCB-native tmux sidebar for rendering `ccbd` ProjectView.

This crate is intentionally not a generic tmux scanner. It talks to the project
`ccbd` Unix socket and treats `ProjectView` as the only UI authority.

Phase 1 launch shape:

```text
ccb-agent-sidebar --ccbd-socket <path> --project-root <path> --pane-window <name>
```

Upstream inspiration and future UI component migration come from
`hiroppy/tmux-agent-sidebar`; its MIT license is retained in `LICENSE.upstream`.
