# Roadmap

Date: 2026-06-16

## Done

- Captured a real lifecycle CPU profile from an isolated source runtime under
  `/home/bfly/yunwei/test_ccb2` using `/home/bfly/yunwei/ccb_source/ccb_test`.
  Evidence:
  [history/real-lifecycle-cpu-profile-2026-06-16.md](history/real-lifecycle-cpu-profile-2026-06-16.md).
- Confirmed the currently landed Rust helpers improve local paths but do not
  explain the dominant lifecycle CPU share in the sampled workload.
- Established the current optimization priority: shell/tmux/subprocess
  orchestration first, then provider lifecycle policy, then CCB core only if it
  remains above the agreed threshold after those reductions.
- Added a repeatable lifecycle profiling harness and reviewed it for
  source-runtime-safe invocation and project-scoped process attribution.
- Added a low-risk detached tmux prepare cache keyed by socket identity and
  environment fingerprint.
- Added a narrow project_focus fast path that queues sidebar refresh through
  project_view when available, while preserving synchronous refresh fallback.
- Fixed the pending sidebar-refresh crash exposed by that fast path by adding
  the missing project_view refresh metrics helper and regression coverage.

## In Progress

- Main-agent packaging and review for the first safe slices: profiling
  attribution, tmux prepare caching, and interactive focus latency. Worker3's
  wider project_view/Rust-helper output remains quarantined because the reply
  and worktree did not match. Reviewer agents are not used for this task. Topic:
  [startup-and-runtime-low-latency-plan.md](topics/startup-and-runtime-low-latency-plan.md).

## Next

1. Split the current `shell-system` bucket into tmux server, ask CLI process
   creation, shell wrappers, terminal frontend, and unrelated OS/UI work.
2. Add a repeatable startup profile gate with wall time, cumulative CPU, peak
   process count, and provider mount timing.
3. Add a high-load profile matrix by provider mix: Codex-only, Gemini-only,
   mixed mounted-idle, and mixed active.
4. Add an interactive latency probe for click-to-pane-focus and
   click-to-stable-sidebar-refresh.
5. Promote the highest-ROI implementation slice only after the refined profile
   shows a clear owner and acceptance threshold.

## Deferred

- Full CCB core rewrite or broad Rust migration.
- Provider CLI internal optimization.
- Default-enabling opt-in Rust storage summary without broader fixture evidence.
