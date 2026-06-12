# Codex Prompt Delivery Binding Drift Repair

Date: 2026-06-12

Role: implementation entrypoint
Status: implemented pending review
Authority: [managed provider completion reliability contract](../../../../managed-provider-completion-reliability-plan.md)
Read when: Codex pane-backed asks fail with `codex_prompt_delivery_failed`,
`delivery_anchor_missing`, or an agent appears idle/healthy while the Codex
session never records the active `CCB_REQ_ID`.

## Incident Boundary

The failure is not mailbox loss. A worker mailbox can receive and consume a
task while Codex never records the wrapped prompt anchor in its protocol log.
Mailbox consumed, tmux paste attempted, and pane liveness are not provider
acceptance evidence.

## Implemented Repair

- Codex binding evidence is collected as evidence only, not daemon authority:
  recorded Codex PID and bridge PID liveness, current tmux pane PID, pid
  mismatch, runtime dir, input fifo, session file, session id, CCB session id,
  session-log freshness, and activity freshness.
- Managed Codex active start runs preflight before prompt paste. If binding
  evidence is already unhealthy, CCB returns retryable
  `codex_binding_unhealthy` / `provider_runtime_binding_stale` diagnostics and
  does not paste the prompt.
- Healthy managed starts keep sending the wrapped prompt and enter
  `delivery_state = pending_anchor`.
- Anchor observation moves delivery state to `accepted`.
- If the delivery timeout expires before the anchor appears, the poller emits
  `codex_prompt_delivery_failed` with `delivery_failure_kind =
  delivery_anchor_missing`, `mailbox_consumed = true`, `provider_acceptance =
  anchor_missing`, binding evidence, and explicit recovery guidance.
- Provider activity records the failed delivery condition so project view,
  doctor, `ps`, and heartbeat can surface degraded/suspicious evidence instead
  of plain idle/healthy.

## Retry Policy

The repair is intentionally non-resending. Failures are marked retryable for the
operator, but `auto_retry_allowed = false`. Recovery guidance remains:
`ccb restart <agent>`, send a smoke ask, then retry intentionally.

## Verification

Automated validation on 2026-06-12:

```bash
pytest test/test_v2_execution_service.py test/test_codex_comm_session_runtime.py test/test_ccbd_project_view.py test/test_v2_heartbeat_engine.py test/test_stability_regressions.py test/test_v2_cli_render.py test/test_doctor_runtime_identity.py test/test_v2_provider_binding.py test/test_ccbd_start_agent_runtime.py test/test_ccbd_runtime_refresh.py
```

Result: 168 passed.

```bash
git diff --check
```

Result: passed.

Source wrapper diagnostic was run from `/home/bfly/yunwei/test_ccb2` with
isolated `HOME` and `CCB_SOURCE_HOME`; result passed. A full live managed Codex
smoke scenario was not started in this implementation pass.
