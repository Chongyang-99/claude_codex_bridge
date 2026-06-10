# V1 Slice And Tests

Date: 2026-06-10

## V1 Goal

Ship the smallest useful CCB maintenance heartbeat that is independently
invokable, diagnoses configured-agent health from ccbd and communication
evidence, exits when healthy/idle, and escalates risk, unknown, or unhealthy
states to the configured semantic assessor, defaulting to `ccb_self`.

V1 must not perform automatic mutating repair.

## Included

- `ccb maintenance tick`: one-shot runner entrypoint with project discovery and
  optional explicit project root.
- `ccb maintenance status`: read current schedule and last tick state.
- `ccb maintenance schedule --after <duration> --reason <text>`: validated
  schedule update.
- `ccb maintenance enable` / `disable`: user-facing policy commands only.
- Effective `ccb.config` heartbeat enablement and configured assessor lookup.
- Normal `ccb` startup ensures the independent runner when heartbeat is enabled
  and the configured assessor exists by refreshing schedule state and running
  or arranging a one-shot due tick. V1 does not add a long-lived supervised
  runner process unless a startup lifecycle contract is added first.
- Independent heartbeat lock under the heartbeat namespace, with stale-lock
  detection separate from keeper and ccbd lifecycle locks.
- Schedule state under a dedicated namespace such as
  `.ccb/ccbd/maintenance-heartbeat/schedule.json`.
- Programmatic snapshot from existing ccbd diagnostics and CCB communication
  state.
- Healthy idle detection that records `last_ok`, schedules the next normal
  interval, and does not wake the assessor.
- Escalation to the configured assessor for risk, unknown, or unhealthy states,
  using `ask --silence`, a bounded diagnostic package, and a dedup key.
- V1 assessor result validation limited to `report_only`, `ask_user`, and
  schedule recommendations.
- Assessor-requested delayed follow-up through a validated schedule command,
  not through direct self-to-self ask or a provider-side loop.
- A minimal internal `ActivationIntent` envelope for heartbeat diagnostic
  dispatch, with fields that can later support scheduled tasks to other agents.
- A minimal activation-condition model where heartbeat state checks and due
  follow-ups create `ActivationIntent` values, but v1 dispatch only targets
  `self` / `ccb_self`.

## Deferred From V1

- Automatic repair actions: `clear`, `restart`, `repair`, `kill`, force
  cleanup, restart-all, or window-level restart.
- Autonomous assessor enable/disable of heartbeat policy.
- Automatic external scheduler installation.
- Multi-assessor arbitration.
- General user-facing scheduled tasks to arbitrary agents.
- Non-heartbeat activation condition producers.
- Rich `ccb doctor` or sidebar UI integration beyond a minimal status summary.
- Provider-side loops or long-lived assessor turns.
- Direct self-to-self ask chains for delayed diagnosis.

## Contract Update Gate

Before implementing files, config fields, startup behavior, or status fields:

- update [../../../../ccb-config-layout-contract.md](../../../../ccb-config-layout-contract.md)
  with heartbeat config fields, defaults, validation, and reload behavior;
- update [../../../../ccbd-diagnostics-contract.md](../../../../ccbd-diagnostics-contract.md)
  with `.ccb/ccbd/maintenance-heartbeat/`, schedule schema, lock/status files,
  support-bundle inclusion, and the distinction between daemon lease heartbeat,
  subject/job heartbeat evidence, and maintenance heartbeat scheduling;
- update [../../../../ccbd-startup-supervision-contract.md](../../../../ccbd-startup-supervision-contract.md)
  with startup ensure semantics, optional runner failure reporting, and `ccb
  kill` interaction;
- complete [snapshot-and-contract-gates.md](snapshot-and-contract-gates.md)
  with a field-to-read-path map and close any required diagnostics gaps.

## Test Matrix

- `test_maintenance_tick_idle_project`: healthy idle state records `last_ok`,
  advances `next_run_at`, and does not wake the assessor.
- `test_maintenance_tick_risk_escalates_to_assessor`: non-empty risk evidence
  sends one bounded diagnostic package to the configured assessor.
- `test_maintenance_tick_unknown_escalates_and_shortens`: unknown state
  escalates to the assessor with `ask --silence` and schedules a shorter
  validated interval.
- `test_maintenance_tick_unhealthy_escalates_user_visible`: unhealthy state
  records user-visible diagnostics and sends the bounded package to the
  assessor.
- `test_maintenance_tick_duplicate_wakeup`: existing assessor maintenance task
  prevents a duplicate wakeup.
- `test_maintenance_tick_lock`: concurrent ticks are deduplicated by the
  heartbeat lock.
- `test_maintenance_tick_stale_lock`: stale heartbeat lock is released only by
  the heartbeat stale-lock rule.
- `test_maintenance_disabled`: disabled heartbeat exits without diagnostics
  mutation beyond a status result.
- `test_maintenance_too_early`: tick exits when `next_run_at` is in the
  future unless explicitly forced by a user command.
- `test_maintenance_assessor_missing`: healthy states still succeed
  programmatically; non-healthy states become user-visible diagnostics.
- `test_maintenance_assessor_degraded`: degraded assessor is not woken
  repeatedly; the runner backs off and records reason.
- `test_maintenance_schedule_validation`: intervals below the minimum, missing
  reasons, or zero-delay loops are rejected.
- `test_maintenance_enable_disable`: user commands change policy state and
  `status` reflects it.
- `test_maintenance_config_enablement`: effective config controls heartbeat
  enablement and assessor target.
- `test_maintenance_startup_ensures_runner`: normal `ccb` project startup
  ensures the runner only when heartbeat is enabled and the assessor exists.
- `test_maintenance_startup_runner_failure_nonfatal`: optional runner launch
  failure is reported as diagnostics/status evidence without failing ordinary
  project startup.
- `test_maintenance_kill_concurrent`: `ccb kill` during a tick does not leave
  keeper/ccbd locks blocked and heartbeat lock cleanup follows heartbeat rules.
- `test_maintenance_schedule_corrupt`: malformed schedule state degrades to a
  visible diagnostics error without crashing startup or tick.
- `test_maintenance_multi_project_isolation`: two projects with heartbeat
  enabled use separate schedule, lock, and activation state.
- `test_maintenance_diagnostics_read_race`: runner tolerates ccbd diagnostics
  files being updated while it reads snapshots.
- `test_maintenance_followup_conflict`: assessor schedule request that
  conflicts with an active follow-up is deduplicated or rejected with a clear
  reason.
- `test_maintenance_config_hot_reload`: config changes while ccbd is mounted
  update heartbeat policy only through the accepted reload semantics.
- `test_maintenance_unmounted_residue`: stale schedule state with an unmounted
  project records diagnostics and does not invent backend authority.
- `test_maintenance_ask_silence_dispatch`: inconclusive unfinished work sends
  one silence ask to the assessor and the runner exits without waiting.
- `test_maintenance_activation_intent`: heartbeat dispatch is represented as
  a bounded `ActivationIntent` with target, trigger kind, dedup key, delivery
  mode, reason, and payload reference.
- `test_maintenance_activation_condition_state_check`: risk or unknown
  programmatic state creates an `ActivationIntent` without hard-coding dispatch
  in the condition evaluator.
- `test_maintenance_activation_condition_due_followup`: a due follow-up
  creates the same `ActivationIntent` shape as a state-check condition.
- `test_maintenance_activation_target_scope_v1`: v1 rejects non-self target
  dispatch even though the activation envelope has a generic target field.
- `test_maintenance_assessor_schedules_followup`: self can register a delayed
  follow-up through the sanctioned schedule surface with reason and diagnostic
  fingerprint.
- `test_maintenance_followup_resolves_without_wakeup`: a due follow-up takes a
  fresh snapshot and resolves without waking self when the condition cleared.
- `test_maintenance_followup_reasks_when_still_ambiguous`: a due follow-up
  sends one new `ask --silence` to self when the same ambiguity remains.
- `test_maintenance_followup_cap_escalates_user`: repeated follow-ups hit the
  configured cap, stop shortening the interval, and surface `needs_user=true`.
- `test_maintenance_snapshot_reuses_diagnostics`: required snapshot fields come
  from existing diagnostics/communication surfaces rather than a parallel
  collection path.
