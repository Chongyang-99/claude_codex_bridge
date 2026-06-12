from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from ccbd.api_models import JobRecord
from completion.models import CompletionSourceKind
from provider_core.instance_resolution import named_agent_instance
from provider_execution.active import PreparedActiveStart, prepare_active_start
from provider_execution.base import ProviderRuntimeContext, ProviderSubmission
from provider_execution.common import error_submission, no_wrap_requested, normalize_session_path, send_prompt_to_runtime_target

from ..binding_evidence import binding_preflight_diagnostics, collect_codex_binding_evidence
from .readiness import wait_for_runtime_ready


def start_active_submission(
    adapter,
    job: JobRecord,
    *,
    context: ProviderRuntimeContext | None,
    now: str,
    load_session_fn: Callable[[Path, str], object | None],
    backend_for_session_fn: Callable[[dict], object | None],
    reader_factory: Callable[[object, Path | None], object],
    request_anchor_fn: Callable[[str | None], str],
    wrap_prompt_fn: Callable[[str, str], str],
) -> ProviderSubmission:
    prepared = prepare_active_start(
        job,
        context=context,
        provider=adapter.provider,
        source_kind=CompletionSourceKind.PROTOCOL_EVENT_STREAM,
        now=now,
        missing_session_reason='missing_codex_session',
        load_session_fn=load_session_fn,
        backend_for_session_fn=backend_for_session_fn,
    )
    if not isinstance(prepared, PreparedActiveStart):
        return prepared

    reader = reader_factory(prepared.session, None)
    state = reader.capture_state()
    binding_evidence = collect_codex_binding_evidence(
        session=prepared.session,
        backend=prepared.backend,
        pane_id=prepared.pane_id,
        session_log_path=state_session_path(state),
    )
    if binding_evidence.preflight_failed:
        return binding_error_submission(
            adapter,
            job,
            now=now,
            work_dir=prepared.work_dir,
            pane_id=prepared.pane_id,
            project_id=job.request.project_id,
            evidence=binding_evidence,
        )
    request_anchor = request_anchor_fn(job.job_id)
    no_wrap = no_wrap_requested(job)
    prompt = job.request.body if no_wrap else wrap_prompt_fn(job.request.body, request_anchor)
    wait_for_runtime_ready(prepared.backend, prepared.pane_id)
    send_prompt_to_runtime_target(prepared.backend, prepared.pane_id, prompt)

    return ProviderSubmission(
        job_id=job.job_id,
        agent_name=job.agent_name,
        provider=adapter.provider,
        accepted_at=now,
        ready_at=now,
        source_kind=CompletionSourceKind.PROTOCOL_EVENT_STREAM,
        reply='',
        diagnostics={'provider': adapter.provider, 'mode': 'active', 'workspace_path': str(prepared.work_dir)},
        runtime_state={
            'mode': 'active',
            'reader': reader,
            'state': state,
            'backend': prepared.backend,
            'pane_id': prepared.pane_id,
            'request_anchor': request_anchor,
            'next_seq': 1,
            'anchor_seen': no_wrap,
            'bound_turn_id': '',
            'bound_task_id': '',
            'reply_buffer': '',
            'last_agent_message': '',
            'last_final_answer': '',
            'last_assistant_message': '',
            'last_assistant_signature': '',
            'session_path': state_session_path(state),
            'workspace_path': str(prepared.work_dir),
            'no_wrap': no_wrap,
            'prompt_sent': True,
            'prompt_sent_at': now,
            'delivery_state': 'accepted' if no_wrap else 'pending_anchor',
            'delivery_timeout_s': 120.0,
            'binding_evidence': binding_evidence.to_record(),
            'runtime_dir': binding_evidence.runtime_dir,
            'session_file': binding_evidence.session_file,
            'session_id': binding_evidence.session_id,
            'ccb_session_id': binding_evidence.ccb_session_id,
            'project_id': session_project_id(prepared.session),
        },
    )


def binding_error_submission(
    adapter,
    job: JobRecord,
    *,
    now: str,
    work_dir: Path,
    pane_id: str,
    project_id: str,
    evidence,
) -> ProviderSubmission:
    diagnostics = binding_preflight_diagnostics(evidence)
    submission = error_submission(
        job,
        provider=adapter.provider,
        now=now,
        source_kind=CompletionSourceKind.PROTOCOL_EVENT_STREAM,
        reason='codex_binding_unhealthy',
        error=str(diagnostics.get('error') or 'codex_binding_unhealthy'),
    )
    return replace_submission_diagnostics(
        submission,
        diagnostics={
            **dict(submission.diagnostics or {}),
            **diagnostics,
            'workspace_path': str(work_dir),
            'pane_id': pane_id,
            'delivery_state': 'preflight_failed',
            'delivery_failure_kind': 'provider_binding_stale',
            'project_id': str(project_id or '').strip(),
        },
        runtime_state={
            **dict(submission.runtime_state),
            **diagnostics,
            'workspace_path': str(work_dir),
            'pane_id': pane_id,
            'delivery_state': 'preflight_failed',
            'delivery_failure_kind': 'provider_binding_stale',
            'project_id': str(project_id or '').strip(),
        },
    )


def replace_submission_diagnostics(
    submission: ProviderSubmission,
    *,
    diagnostics: dict[str, object],
    runtime_state: dict[str, object],
) -> ProviderSubmission:
    return replace(submission, diagnostics=diagnostics, runtime_state=runtime_state)


def resume_submission(
    job: JobRecord,
    submission: ProviderSubmission,
    *,
    context: ProviderRuntimeContext | None,
    load_session_fn: Callable[[Path, str], object | None],
    backend_for_session_fn: Callable[[dict], object | None],
    reader_factory: Callable[[object, Path | None], object],
) -> ProviderSubmission | None:
    if context is None or not context.workspace_path:
        return None
    state = dict(submission.runtime_state)
    if str(state.get('mode') or 'passive') != 'active':
        return None
    work_dir = Path(context.workspace_path).expanduser()
    session = load_session_fn(work_dir, job.agent_name)
    if session is None:
        return None
    ok, pane_or_err = session.ensure_pane()
    if not ok:
        return None
    backend = backend_for_session_fn(session.data)
    if backend is None:
        return None
    preferred_log = preferred_log_path(state)
    reader = reader_factory(session, preferred_log)
    return replace(
        submission,
        runtime_state={
            **state,
            'reader': reader,
            'backend': backend,
            'pane_id': str(pane_or_err),
            'mode': 'active',
            'session_path': state.get('session_path') or (str(preferred_log) if preferred_log else ''),
            'workspace_path': str(work_dir),
        },
    )


def load_session(load_project_session_fn, work_dir: Path, *, agent_name: str):
    instance = named_agent_instance(agent_name, primary_agent='codex')
    if instance is not None:
        session = load_project_session_fn(work_dir, instance)
        if session is not None:
            return session
        return None
    return load_project_session_fn(work_dir)


def preferred_log_path(state: dict[str, object]) -> Path | None:
    raw = state.get('session_path') or state_session_path(state.get('state') or {})
    session_path = normalize_session_path(raw)
    if not session_path:
        return None
    try:
        return Path(session_path).expanduser()
    except Exception:
        return None


def state_session_path(state: dict[str, object]) -> str:
    return normalize_session_path(state.get('log_path'))


def session_project_id(session) -> str:
    data = getattr(session, 'data', None)
    if not isinstance(data, dict):
        return ''
    return str(data.get('ccb_project_id') or '').strip()


__all__ = [
    'load_session',
    'preferred_log_path',
    'resume_submission',
    'start_active_submission',
    'state_session_path',
]
