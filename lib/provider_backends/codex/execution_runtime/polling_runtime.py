from __future__ import annotations

from dataclasses import replace
import os

from ccbd.system import parse_utc_timestamp
from completion.models import CompletionConfidence, CompletionDecision, CompletionItemKind, CompletionStatus
from provider_execution.active import prepare_active_poll
from provider_execution.base import ProviderPollResult, ProviderSubmission
from provider_execution.common import build_item, request_anchor_from_runtime_state
from provider_hooks.activity import write_activity

from ..binding_evidence import RECOVERY_HINT, collect_codex_binding_evidence
from .event_reading import read_entries
from .start import state_session_path
from .state_machine import (
    apply_session_rotation,
    build_poll_state,
    finalize_poll_result,
    handle_assistant_entry,
    handle_terminal_entry,
    handle_user_entry,
    update_binding_refs,
)


def poll_submission(submission: ProviderSubmission, *, now: str) -> ProviderPollResult | None:
    prepared = prepare_active_poll(submission, now=now)
    if prepared is None or isinstance(prepared, ProviderPollResult):
        return prepared

    state = submission.runtime_state.get("state") or {}
    poll = build_poll_state(submission)
    state = poll_entry_batches(submission, poll, prepared.reader, state, now=now)
    return with_delivery_anchor_timeout(
        finalize_poll_result(submission, poll, state=state),
        fallback_submission=submission,
        now=now,
    )


def poll_entry_batches(submission, poll, reader, state, *, now: str):
    current_state = state
    while True:
        entries, current_state = read_entries(reader, current_state)
        apply_session_state(submission, poll, current_state, now=now)
        if not entries:
            break
        process_entry_batch(submission, poll, entries, now=now)
        if poll.reached_terminal:
            break
    return current_state


def apply_session_state(submission, poll, state, *, now: str) -> None:
    apply_session_rotation(
        submission,
        poll,
        new_session_path=state_session_path(state),
        now=now,
    )


def process_entry_batch(submission, poll, entries, *, now: str) -> None:
    for entry in entries:
        process_entry(submission, poll, entry, now=now)
        if poll.reached_terminal:
            break


def process_entry(submission, poll, entry, *, now: str) -> None:
    update_binding_refs(poll, entry)
    role = str(entry.get("role") or "").strip().lower()
    if role == "user":
        handle_user_entry(submission, poll, text=str(entry.get("text") or ""), now=now)
        return
    if not poll.anchor_seen:
        return
    if role == "assistant":
        handle_assistant_entry(submission, poll, entry, now=now)
        return
    handle_terminal_entry(submission, poll, entry, now=now)


def with_delivery_anchor_timeout(
    result: ProviderPollResult | None,
    *,
    fallback_submission: ProviderSubmission,
    now: str,
) -> ProviderPollResult | None:
    current = result.submission if result is not None else fallback_submission
    if result is not None and result.decision is not None:
        return result
    if not delivery_anchor_timeout_due(current, now=now):
        return result
    timeout_result = delivery_anchor_missing_result(current, now=now)
    if result is None or not result.items:
        return timeout_result
    return ProviderPollResult(
        submission=timeout_result.submission,
        items=tuple(result.items) + tuple(timeout_result.items),
        decision=timeout_result.decision,
    )


def delivery_anchor_timeout_due(submission: ProviderSubmission, *, now: str) -> bool:
    runtime_state = dict(submission.runtime_state)
    if str(runtime_state.get("mode") or "").strip().lower() != "active":
        return False
    if bool(runtime_state.get("no_wrap", False)):
        return False
    if bool(runtime_state.get("anchor_seen", False)):
        return False
    if not bool(runtime_state.get("prompt_sent", True)):
        return False
    started_at = str(
        runtime_state.get("prompt_sent_at")
        or submission.ready_at
        or submission.accepted_at
        or ""
    ).strip()
    if not started_at:
        return False
    try:
        elapsed = (parse_utc_timestamp(now) - parse_utc_timestamp(started_at)).total_seconds()
    except Exception:
        return False
    return elapsed >= delivery_timeout_s(runtime_state)


def delivery_timeout_s(runtime_state: dict[str, object]) -> float:
    raw = str(os.environ.get("CCB_CODEX_PROMPT_DELIVERY_TIMEOUT_S") or "").strip()
    if not raw:
        raw = str(runtime_state.get("delivery_timeout_s") or "120")
    try:
        return max(0.0, float(raw))
    except Exception:
        return 120.0


def delivery_anchor_missing_result(submission: ProviderSubmission, *, now: str) -> ProviderPollResult:
    runtime_state = dict(submission.runtime_state)
    evidence = current_binding_evidence(submission).to_record()
    request_anchor = request_anchor_from_runtime_state(runtime_state, fallback=submission.job_id)
    diagnostics = {
        **dict(submission.diagnostics or {}),
        "provider": submission.provider,
        "mode": "active",
        "reason": "codex_prompt_delivery_failed",
        "error_type": "provider_runtime_prompt_delivery",
        "delivery_failure_kind": "delivery_anchor_missing",
        "delivery_anchor_seen": False,
        "delivery_state": "anchor_missing",
        "mailbox_consumed": True,
        "provider_acceptance": "anchor_missing",
        "request_anchor": request_anchor,
        "prompt_sent_at": str(runtime_state.get("prompt_sent_at") or ""),
        "prompt_delivery_timeout_s": delivery_timeout_s(runtime_state),
        "retryable": True,
        "auto_retry_allowed": False,
        "recovery_hint": RECOVERY_HINT,
        "binding_evidence": evidence,
    }
    next_seq = int(runtime_state.get("next_seq", 1))
    item = build_item(
        submission,
        kind=CompletionItemKind.ERROR,
        timestamp=now,
        seq=next_seq,
        payload={
            "reason": "codex_prompt_delivery_failed",
            "error_type": "provider_runtime_prompt_delivery",
            "delivery_failure_kind": "delivery_anchor_missing",
            "request_anchor": request_anchor,
            "binding_evidence": evidence,
        },
    )
    updated_state = {
        **runtime_state,
        "mode": "passive",
        "next_seq": next_seq + 1,
        "delivery_state": "anchor_missing",
        "delivery_failure_kind": "delivery_anchor_missing",
        "delivery_anchor_seen": False,
        "binding_evidence": evidence,
    }
    updated = replace(
        submission,
        status=CompletionStatus.FAILED,
        reason="codex_prompt_delivery_failed",
        confidence=CompletionConfidence.DEGRADED,
        diagnostics=diagnostics,
        runtime_state=updated_state,
    )
    record_delivery_anchor_missing_activity(updated, diagnostics=diagnostics, now=now)
    return ProviderPollResult(
        submission=updated,
        items=(item,),
        decision=CompletionDecision(
            terminal=True,
            status=CompletionStatus.FAILED,
            reason="codex_prompt_delivery_failed",
            confidence=CompletionConfidence.DEGRADED,
            reply="",
            anchor_seen=False,
            reply_started=False,
            reply_stable=False,
            provider_turn_ref=request_anchor or submission.job_id,
            source_cursor=item.cursor,
            finished_at=now,
            diagnostics=diagnostics,
        ),
    )


def current_binding_evidence(submission: ProviderSubmission):
    state = dict(submission.runtime_state)
    return collect_codex_binding_evidence(
        backend=state.get("backend"),
        pane_id=str(state.get("pane_id") or "").strip() or None,
        runtime_dir=state.get("runtime_dir"),
        session_log_path=state.get("session_path"),
        session_file=state.get("session_file"),
        session_id=str(state.get("session_id") or "").strip() or None,
        ccb_session_id=str(state.get("ccb_session_id") or "").strip() or None,
        managed_runtime_expected=bool(str(state.get("runtime_dir") or "").strip()),
    )


def record_delivery_anchor_missing_activity(
    submission: ProviderSubmission,
    *,
    diagnostics: dict[str, object],
    now: str,
) -> None:
    state = dict(submission.runtime_state)
    runtime_dir = str(state.get("runtime_dir") or "").strip()
    project_id = str(state.get("project_id") or diagnostics.get("project_id") or "").strip()
    if not runtime_dir or not project_id:
        return
    try:
        write_activity(
            provider="codex",
            project_id=project_id,
            agent_name=submission.agent_name,
            runtime_dir=runtime_dir,
            state="failed",
            source="ccb_delivery",
            event_name="PromptDeliveryAnchorMissing",
            ccb_session_id=str(state.get("ccb_session_id") or "").strip() or None,
            pane_id=str(state.get("pane_id") or "").strip() or None,
            workspace_path=str(state.get("workspace_path") or "").strip() or None,
            provider_session_id=str(state.get("session_id") or "").strip() or None,
            diagnostics={
                "reason": "delivery_anchor_missing",
                "mailbox_consumed": True,
                "provider_acceptance": "anchor_missing",
                "binding_evidence": diagnostics.get("binding_evidence"),
            },
            updated_at=now,
        )
    except Exception:
        return


__all__ = ["poll_submission"]
