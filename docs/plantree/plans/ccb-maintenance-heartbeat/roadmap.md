# CCB Maintenance Heartbeat Roadmap

Date: 2026-06-10

## Done

- Accepted the boundary correction: heartbeat scheduling, wake policy, and
  next-run state belong to CCB rather than to the `ccb_self` Role Pack.
- Promoted the external heartbeat idea from the general ideas inbox into this
  CCB-level planning root.
- Accepted the direction that the heartbeat should be an independent CCB
  program/helper that `ccb_self` can trigger or reschedule through a sanctioned
  skill or control-plane command.
- Accepted the user's correction that the heartbeat is generic CCB
  infrastructure: it periodically diagnoses all configured agents from ccbd and
  communication evidence, then escalates risk, unknown, or unhealthy states to
  the configured semantic assessor, defaulting to `ccb_self`.
- Accepted reviewer1's architecture feedback: avoid hard-coding `ccb_self`,
  prefer a hybrid `ccb maintenance ...` one-shot surface over ccbd/keeper
  internal ticks, keep the heartbeat lock independent from keeper/ccbd locks,
  and constrain v1 assessor actions to report-only advice.
- Accepted the startup/config direction: heartbeat enablement belongs in
  effective `ccb.config`; normal `ccb` project startup should ensure the
  independent runner when heartbeat is enabled and the configured assessor
  exists; ambiguous unfinished work is escalated to `self` with
  `ask --silence` so the runner does not block waiting for semantic analysis.
- Accepted the abstraction direction: activation conditions are separate from
  activation dispatch. Heartbeat state checks and scheduled follow-ups are the
  first condition producers; v1 uses one `ActivationIntent` structure and only
  activates `self`, while future conditions may target other configured agents.
- Accepted reviewer1's design review: clarify maintenance heartbeat namespace
  versus existing job heartbeat evidence, avoid long-lived runner lifecycle
  ambiguity in v1, collapse condition/record data into `ActivationIntent`,
  require a snapshot-field/read-path map, and expand integration tests.
- Accepted worker1's implementation analysis: land contracts, config parsing,
  namespace/store, and read-only status before any tick dispatch; keep
  `enable/disable` mutation, startup runner lifecycle, and internal
  `ask --silence` sender identity as explicit implementation decisions.
- Landed the first safe implementation slice: `[maintenance.heartbeat]`
  config parsing/defaults, `.ccb/ccbd/maintenance-heartbeat/` path helpers,
  schedule/status data models, read-only `ccb maintenance status`,
  diagnostics bundle inclusion, and reserved non-mutating parser entries for
  `tick|schedule|enable|disable`. Verified with targeted pytest, py_compile,
  `git diff --check`, and isolated external `ccb_test` smoke tests from
  `/home/bfly/yunwei/test_ccb2`.
- Landed the one-shot tick snapshot slice: `ccb maintenance tick` now runs only
  when heartbeat is enabled, reads bounded `project_view` evidence from the
  mounted daemon with local `ps` fallback, classifies `healthy|concern|failing|unknown`,
  writes only `maintenance-heartbeat/status.json` and `schedule.json`, shortens
  non-healthy cadence to `min_interval_s`, and still does not dispatch
  `ask --silence`, repair, or start providers.
- Landed the activation/schedule/startup ensure slice: non-healthy due ticks
  create a bounded `ActivationIntent` audit record, validate the configured
  assessor, suppress active or recent duplicate maintenance activations,
  submit one `ask --silence` through the mounted daemon dispatcher with
  `from_actor=maintenance-heartbeat`, then exit. `ccb maintenance schedule`
  writes the next CCB-owned follow-up time with `min_interval_s` enforcement.
  `ccb` startup now performs a non-fatal due-tick ensure when heartbeat is
  enabled, `startup_ensure=true`, and the assessor exists.
- Completed v1 verification: full `python -m pytest -q` passed with
  `2518 passed, 2 skipped`, `git diff --check` passed, and isolated
  `/home/bfly/yunwei/ccb_source/ccb_test` smoke tests from
  `/home/bfly/yunwei/test_ccb2` covered disabled status/tick/schedule plus an
  enabled temporary project schedule/too-early/force-no-dispatch flow.

## In Progress

- None for v1.

## Next

1. Define the `ccb_self` running-supervision skill input/output contract as
   the v1 default assessor implementation.
2. Add a public scheduled-activation surface for targets other than the
   configured assessor only after a second use case needs it.
3. Define config-edit policy if `ccb maintenance enable/disable` should ever
   mutate `.ccb/ccb.config` instead of staying config-only.

## V1 Readiness Blockers

1. None for the current code slice.

## Deferred

- Automatic mutating repairs beyond explicit low-risk policy.
- Always-on provider-side self loops.
- Project-wide shutdown or force cleanup from heartbeat logic.
- Multiple maintenance roles with arbitration.
- Automatic external scheduler installation.
- Multi-assessor arbitration beyond the default `ccb_self` assessor.
- Public scheduled activation to arbitrary target agents.
- `ccb maintenance enable/disable` editing `.ccb/ccb.config`; v1 keeps
  enablement as config authority.
