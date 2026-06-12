# Managed Provider Completion Reliability Roadmap

Date: 2026-06-12

## Done

- Implemented Codex binding evidence collection for managed pane-backed
  runtime artifacts: `codex.pid`, `bridge.pid`, tmux pane pid, pid mismatch,
  runtime dir, input fifo, session file, session log freshness, and provider
  activity freshness.
- Added Codex active-submission preflight so known stale managed bindings fail
  before prompt paste with retryable, non-auto-retried diagnostics.
- Extended `delivery_anchor_missing` diagnostics and provider activity so CCB
  can distinguish mailbox consumption from provider acceptance.
- Surfaced provider binding evidence in project view, `ps`, doctor rendering,
  health assessment, communicator health, and heartbeat diagnostics.
- Preserved healthy Codex delivery behavior: successful starts still enter
  `pending_anchor`, and anchor observation moves delivery state to `accepted`.

## In Progress

- Multi-agent implementation review through `archi` and `reviewer3`.

## Next

- Address blocking review findings if any.
- Consider a real managed Codex smoke scenario after review if a safe fixture is
  available; do not use the source checkout as the live runtime directory.

## Deferred

- Automatic retry or resend after missing anchor. The current policy remains
  operator-driven: `ccb restart <agent>`, smoke ask, then retry intentionally.
