from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from agents.config_loader import load_project_config
from ccbd.api_models import DeliveryScope, MessageEnvelope
from ccbd.system import parse_utc_timestamp, utc_now
from cli.context import CliContext
from cli.models import ParsedMaintenanceCommand, ParsedPsCommand
from mailbox_runtime import MAINTENANCE_HEARTBEAT_ACTOR
from maintenance_heartbeat import (
    MaintenanceHeartbeatActivation,
    MaintenanceHeartbeatEvaluation,
    MaintenanceHeartbeatLock,
    MaintenanceHeartbeatLockBusy,
    MaintenanceHeartbeatReadResult,
    MaintenanceHeartbeatSchedule,
    MaintenanceHeartbeatStatus,
    MaintenanceHeartbeatStore,
    evaluate_project_view,
    evaluate_ps_summary,
)

from .daemon import connect_mounted_daemon, invoke_mounted_daemon
from .ps import ps_summary

_ACTIVATION_TAIL_LIMIT = 100
_MESSAGE_EVIDENCE_LIMIT = 5
_ACTIVE_ACTIVATION_BUSINESS_STATUSES = {'delivering', 'replying', 'sending'}
_ACTIVE_JOB_STATUSES = {'accepted', 'queued', 'running'}


@dataclass(frozen=True)
class _RuntimeObservation:
    evaluation: MaintenanceHeartbeatEvaluation
    payload: Mapping[str, object]


def maintenance_status(context: CliContext, command: ParsedMaintenanceCommand) -> dict:
    action = str(command.action or 'status').strip().lower()
    if action == 'status':
        return _maintenance_status(context)
    if action == 'tick':
        return _maintenance_tick(context, command)
    if action == 'schedule':
        return _maintenance_schedule(context, command)
    if action in {'enable', 'disable'}:
        return {
            'maintenance_status': 'not_implemented',
            'action': action,
            'reason': 'heartbeat enablement is config-authority in v1; edit [maintenance.heartbeat].enabled',
        }
    return {
        'maintenance_status': 'not_implemented',
        'action': action,
        'reason': 'unsupported maintenance action',
    }


def _maintenance_status(context: CliContext) -> dict:
    loaded = load_project_config(context.project.project_root)
    heartbeat = loaded.config.maintenance_heartbeat
    store = MaintenanceHeartbeatStore(context.paths, project_id=context.project.project_id)
    schedule = store.load_schedule()
    last_status = store.load_status()
    last_activation = _load_last_activation(store, context)
    degraded = schedule.state == 'corrupt' or last_status.state == 'corrupt'
    return {
        'maintenance_status': 'degraded' if degraded else 'ok',
        'project': str(context.project.project_root),
        'project_id': context.project.project_id,
        'config_source_kind': loaded.source_kind,
        'config_source': str(loaded.source_path) if loaded.source_path else None,
        'enabled': heartbeat.enabled,
        'assessor': heartbeat.assessor,
        'assessor_present': heartbeat.assessor in loaded.config.agents,
        'interval_s': heartbeat.interval_s,
        'min_interval_s': heartbeat.min_interval_s,
        'unknown_streak_cap': heartbeat.unknown_streak_cap,
        'escalation_policy': heartbeat.escalation_policy,
        'startup_ensure': heartbeat.startup_ensure,
        'schedule': schedule.to_record(),
        'last_status': last_status.to_record(),
        'last_activation': last_activation,
    }


def _maintenance_tick(context: CliContext, command: ParsedMaintenanceCommand) -> dict:
    loaded = load_project_config(context.project.project_root)
    heartbeat = loaded.config.maintenance_heartbeat
    store = MaintenanceHeartbeatStore(context.paths, project_id=context.project.project_id)
    try:
        tick_options = _parse_tick_args(command.args)
    except ValueError as exc:
        return {
            'maintenance_status': 'invalid',
            'action': 'tick',
            'reason': str(exc),
        }
    if not heartbeat.enabled:
        return {
            **_maintenance_status(context),
            'maintenance_status': 'ok',
            'action': 'tick',
            'tick_status': 'disabled',
            'tick_source_kind': 'disabled',
            'tick_recommended_action': 'none',
            'tick_needs_user': False,
            'tick_next_heartbeat_after_s': None,
            'status_written': False,
            'schedule_written': False,
            'activation_written': False,
            'tick_activation_status': None,
            'tick_activation_id': None,
            'tick_activation_job_id': None,
            'tick_summary': {'source_kind': 'disabled'},
            'tick_evidence': [],
            'reason': 'maintenance heartbeat is disabled by effective config',
        }

    observed_at = utc_now()
    try:
        with _heartbeat_lock(context, action='tick', observed_at=observed_at):
            if not tick_options['force']:
                current_schedule = store.load_schedule()
                if _schedule_is_future(current_schedule, observed_at):
                    return {
                        **_maintenance_status(context),
                        'maintenance_status': 'ok',
                        'action': 'tick',
                        'tick_status': 'too_early',
                        'tick_source_kind': 'schedule',
                        'tick_recommended_action': 'none',
                        'tick_needs_user': False,
                        'tick_next_heartbeat_after_s': None,
                        'status_written': False,
                        'schedule_written': False,
                        'activation_written': False,
                        'tick_activation_status': None,
                        'tick_activation_id': None,
                        'tick_activation_job_id': None,
                        'tick_summary': {'source_kind': 'schedule'},
                        'tick_evidence': [],
                        'reason': 'heartbeat schedule is not due; use `ccb maintenance tick --force` to run now',
                    }
            return _run_due_tick(
                context,
                loaded=loaded,
                heartbeat=heartbeat,
                store=store,
                observed_at=observed_at,
                dispatch=bool(tick_options['dispatch']),
            )
    except MaintenanceHeartbeatLockBusy:
        return {
            **_maintenance_status(context),
            'maintenance_status': 'ok',
            'action': 'tick',
            'tick_status': 'locked',
            'tick_source_kind': 'lock',
            'tick_recommended_action': 'none',
            'tick_needs_user': False,
            'tick_next_heartbeat_after_s': None,
            'status_written': False,
            'schedule_written': False,
            'activation_written': False,
            'tick_activation_status': None,
            'tick_activation_id': None,
            'tick_activation_job_id': None,
            'tick_summary': {'source_kind': 'lock'},
            'tick_evidence': [],
            'reason': 'another maintenance heartbeat tick is active',
        }


def _maintenance_schedule(context: CliContext, command: ParsedMaintenanceCommand) -> dict:
    loaded = load_project_config(context.project.project_root)
    heartbeat = loaded.config.maintenance_heartbeat
    store = MaintenanceHeartbeatStore(context.paths, project_id=context.project.project_id)
    try:
        schedule_options = _parse_schedule_args(command.args)
    except ValueError as exc:
        return {
            'maintenance_status': 'invalid',
            'action': 'schedule',
            'reason': str(exc),
        }
    if not heartbeat.enabled:
        return {
            **_maintenance_status(context),
            'maintenance_status': 'degraded',
            'action': 'schedule',
            'schedule_status': 'disabled',
            'schedule_written': False,
            'requested_after_s': schedule_options['after_s'],
            'scheduled_after_s': None,
            'reason': 'maintenance heartbeat is disabled by effective config',
        }
    observed_at = utc_now()
    delay_s = max(int(schedule_options['after_s']), int(heartbeat.min_interval_s))
    next_run_at = _after_seconds(observed_at, delay_s)
    try:
        with _heartbeat_lock(context, action='schedule', observed_at=observed_at):
            store.save_schedule(
                MaintenanceHeartbeatSchedule(
                    project_id=context.project.project_id,
                    next_run_at=next_run_at,
                    reason=schedule_options['reason'],
                    updated_at=observed_at,
                    updated_by='maintenance_schedule',
                )
            )
    except MaintenanceHeartbeatLockBusy:
        return {
            **_maintenance_status(context),
            'maintenance_status': 'ok',
            'action': 'schedule',
            'schedule_status': 'locked',
            'schedule_written': False,
            'requested_after_s': schedule_options['after_s'],
            'scheduled_after_s': None,
            'reason': 'another maintenance heartbeat operation is active',
        }
    return {
        **_maintenance_status(context),
        'maintenance_status': 'ok',
        'action': 'schedule',
        'schedule_status': 'scheduled',
        'schedule_written': True,
        'requested_after_s': schedule_options['after_s'],
        'scheduled_after_s': delay_s,
        'next_run_at': next_run_at,
    }


def _run_due_tick(
    context: CliContext,
    *,
    loaded,
    heartbeat,
    store: MaintenanceHeartbeatStore,
    observed_at: str,
    dispatch: bool,
) -> dict:
    observation = _evaluate_runtime(context)
    evaluation = observation.evaluation
    previous = store.load_status()
    unknown_streak = _next_unknown_streak(evaluation.health, previous)
    next_after_s = _next_after_s(evaluation.health, heartbeat=heartbeat, unknown_streak=unknown_streak)
    unknown_cap_reached = evaluation.health == 'unknown' and unknown_streak >= int(heartbeat.unknown_streak_cap)
    activation = _maybe_activate_assessor(
        context,
        loaded=loaded,
        heartbeat=heartbeat,
        store=store,
        observation=observation,
        observed_at=observed_at,
        next_after_s=next_after_s,
        dispatch=dispatch,
    )
    needs_user = bool(evaluation.needs_user or unknown_cap_reached or _activation_needs_user(activation))
    status = MaintenanceHeartbeatStatus(
        project_id=context.project.project_id,
        last_tick_status=evaluation.health,
        last_tick_at=observed_at,
        last_ok_at=observed_at if evaluation.health == 'healthy' else _previous_last_ok(previous),
        last_error=_first_issue_reason(evaluation.evidence),
        unknown_streak=unknown_streak,
        updated_at=observed_at,
        source_kind=evaluation.source_kind,
        recommended_action=evaluation.recommended_action,
        next_heartbeat_after_s=next_after_s,
        needs_user=needs_user,
        summary=evaluation.summary,
        evidence=evaluation.evidence,
        last_activation_status=getattr(activation, 'status', None),
        last_activation_id=getattr(activation, 'activation_id', None),
        last_activation_job_id=getattr(activation, 'job_id', None),
        last_activation_target=getattr(activation, 'target_agent', None),
        last_activation_dedup_key=getattr(activation, 'dedup_key', None),
    )
    schedule = MaintenanceHeartbeatSchedule(
        project_id=context.project.project_id,
        next_run_at=_after_seconds(observed_at, next_after_s),
        reason=f'{evaluation.health}_tick',
        updated_at=observed_at,
        updated_by='maintenance_tick',
    )
    store.save_status(status)
    store.save_schedule(schedule)
    return {
        **_maintenance_status(context),
        'maintenance_status': 'degraded' if _activation_needs_user(activation) else 'ok',
        'action': 'tick',
        'tick_status': evaluation.health,
        'tick_source_kind': evaluation.source_kind,
        'tick_recommended_action': evaluation.recommended_action,
        'tick_needs_user': needs_user,
        'tick_next_heartbeat_after_s': next_after_s,
        'status_written': True,
        'schedule_written': True,
        'activation_written': activation is not None,
        'tick_activation_status': getattr(activation, 'status', None),
        'tick_activation_id': getattr(activation, 'activation_id', None),
        'tick_activation_job_id': getattr(activation, 'job_id', None),
        'tick_summary': evaluation.summary,
        'tick_evidence': list(evaluation.evidence),
    }


def _evaluate_runtime(context: CliContext) -> _RuntimeObservation:
    try:
        handle = connect_mounted_daemon(context, allow_restart_stale=False)
        assert handle.client is not None
        payload = handle.client.project_view(schema_version=1)
        return _RuntimeObservation(evaluation=evaluate_project_view(payload), payload=payload)
    except Exception as exc:
        fallback = ps_summary(context, ParsedPsCommand(project=getattr(context.command, 'project', None)))
        return _RuntimeObservation(evaluation=evaluate_ps_summary(fallback, error=str(exc)), payload=fallback)


def _next_after_s(health: str, *, heartbeat, unknown_streak: int = 0) -> int:
    if health == 'healthy':
        return int(heartbeat.interval_s)
    if health == 'unknown' and unknown_streak >= int(heartbeat.unknown_streak_cap):
        return int(heartbeat.interval_s)
    return int(heartbeat.min_interval_s)


def _after_seconds(timestamp: str, seconds: int) -> str:
    return (parse_utc_timestamp(timestamp) + timedelta(seconds=int(seconds))).isoformat().replace('+00:00', 'Z')


def _previous_last_ok(previous: MaintenanceHeartbeatReadResult[MaintenanceHeartbeatStatus]) -> str | None:
    if previous.value is None:
        return None
    return previous.value.last_ok_at


def _next_unknown_streak(health: str, previous: MaintenanceHeartbeatReadResult[MaintenanceHeartbeatStatus]) -> int:
    if health != 'unknown':
        return 0
    if previous.value is None:
        return 1
    return int(previous.value.unknown_streak or 0) + 1


def _first_issue_reason(evidence: tuple[dict, ...]) -> str | None:
    if not evidence:
        return None
    first = evidence[0]
    reason = str(first.get('reason') or '').strip()
    return reason or str(first.get('kind') or '').strip() or None


def _maybe_activate_assessor(
    context: CliContext,
    *,
    loaded,
    heartbeat,
    store: MaintenanceHeartbeatStore,
    observation: _RuntimeObservation,
    observed_at: str,
    next_after_s: int,
    dispatch: bool,
) -> MaintenanceHeartbeatActivation | None:
    evaluation = observation.evaluation
    if evaluation.health == 'healthy':
        return None
    target = str(heartbeat.assessor or '').strip()
    dedup_key = _diagnostic_dedup_key(context, evaluation)
    activation_id = _activation_id()
    common = {
        'project_id': context.project.project_id,
        'activation_id': activation_id,
        'condition_kind': 'heartbeat_state_check',
        'trigger_kind': 'state_check',
        'source': evaluation.source_kind,
        'observed_at': observed_at,
        'target_agent': target,
        'delivery_mode': 'ask_silence',
        'payload_kind': 'maintenance_diagnostic',
        'dedup_key': dedup_key,
        'reason': _first_issue_reason(evaluation.evidence) or evaluation.health,
        'repeat_count': _repeat_count(store, dedup_key),
        'payload_summary': _activation_summary(evaluation, next_after_s=next_after_s),
        'evidence': tuple(evaluation.evidence[:_MESSAGE_EVIDENCE_LIMIT]),
    }
    if target not in loaded.config.agents:
        activation = MaintenanceHeartbeatActivation(
            status='blocked',
            suppressed_reason='assessor_missing',
            error=f'configured assessor is not present: {target}',
            **common,
        )
        store.append_activation(activation)
        return activation
    if not dispatch:
        activation = MaintenanceHeartbeatActivation(
            status='suppressed',
            suppressed_reason='dispatch_disabled',
            **common,
        )
        store.append_activation(activation)
        return activation
    active_job = _active_maintenance_job(observation.payload, target_agent=target)
    if active_job:
        activation = MaintenanceHeartbeatActivation(
            status='suppressed',
            suppressed_reason=f'active_maintenance_job:{active_job}',
            **common,
        )
        store.append_activation(activation)
        return activation
    duplicate = _recent_duplicate(store, dedup_key=dedup_key, observed_at=observed_at, window_s=int(heartbeat.min_interval_s))
    if duplicate is not None:
        activation = MaintenanceHeartbeatActivation(
            status='suppressed',
            suppressed_reason=f'recent_duplicate:{duplicate.activation_id}',
            job_id=duplicate.job_id,
            **common,
        )
        store.append_activation(activation)
        return activation
    try:
        job_id = _dispatch_activation(
            context,
            target_agent=target,
            activation_id=activation_id,
            dedup_key=dedup_key,
            observed_at=observed_at,
            evaluation=evaluation,
            next_after_s=next_after_s,
        )
        activation = MaintenanceHeartbeatActivation(
            status='submitted',
            job_id=job_id,
            submitted_at=observed_at,
            **common,
        )
    except Exception as exc:
        activation = MaintenanceHeartbeatActivation(
            status='failed',
            error=str(exc),
            **common,
        )
    store.append_activation(activation)
    return activation


def _dispatch_activation(
    context: CliContext,
    *,
    target_agent: str,
    activation_id: str,
    dedup_key: str,
    observed_at: str,
    evaluation: MaintenanceHeartbeatEvaluation,
    next_after_s: int,
) -> str | None:
    request = MessageEnvelope(
        project_id=context.project.project_id,
        to_agent=target_agent,
        from_actor=MAINTENANCE_HEARTBEAT_ACTOR,
        body=_activation_message(
            context,
            activation_id=activation_id,
            dedup_key=dedup_key,
            observed_at=observed_at,
            evaluation=evaluation,
            next_after_s=next_after_s,
        ),
        task_id=f'maintenance-heartbeat:{dedup_key}',
        reply_to=None,
        message_type='ask',
        delivery_scope=DeliveryScope.SINGLE,
        silence_on_success=True,
        route_options={
            'maintenance_heartbeat': True,
            'activation_id': activation_id,
            'dedup_key': dedup_key,
        },
    )
    payload = invoke_mounted_daemon(
        context,
        allow_restart_stale=False,
        request_fn=lambda client: client.submit(request),
    )
    return _submitted_job_id(payload)


def _activation_message(
    context: CliContext,
    *,
    activation_id: str,
    dedup_key: str,
    observed_at: str,
    evaluation: MaintenanceHeartbeatEvaluation,
    next_after_s: int,
) -> str:
    package = {
        'schema_version': 1,
        'record_type': 'maintenance_heartbeat_diagnostic',
        'activation_id': activation_id,
        'project_id': context.project.project_id,
        'project': str(context.project.project_root),
        'observed_at': observed_at,
        'health': evaluation.health,
        'source_kind': evaluation.source_kind,
        'dedup_key': dedup_key,
        'recommended_action': evaluation.recommended_action,
        'next_heartbeat_after_s': next_after_s,
        'summary': _bounded_mapping(evaluation.summary),
        'evidence': list(evaluation.evidence[:_MESSAGE_EVIDENCE_LIMIT]),
    }
    diagnostic = json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        'CCB maintenance heartbeat detected a runtime condition that needs semantic supervision.\n\n'
        'Assess the diagnostic package from the ccb_self running-supervision perspective. '
        'Do not perform automatic repair in v1. If a delayed follow-up is needed, request '
        '`ccb maintenance schedule --after <duration> --reason <reason>` through the CCB control plane.\n\n'
        'Diagnostic package:\n'
        '```json\n'
        f'{diagnostic}\n'
        '```\n\n'
        'CCB reply guidance:\n'
        '- Silent-on-success requested.\n'
        '- Reply only with blockers, risks, needed user action, or a schedule recommendation.\n'
        '- Do not include raw logs unless essential.'
    )


def _submitted_job_id(payload: dict) -> str | None:
    job_id = str(payload.get('job_id') or '').strip()
    if job_id:
        return job_id
    jobs = payload.get('jobs')
    if isinstance(jobs, (list, tuple)) and jobs:
        first = jobs[0]
        if isinstance(first, Mapping):
            return str(first.get('job_id') or '').strip() or None
    return None


def _activation_summary(evaluation: MaintenanceHeartbeatEvaluation, *, next_after_s: int) -> dict[str, object]:
    return {
        'health': evaluation.health,
        'source_kind': evaluation.source_kind,
        'recommended_action': evaluation.recommended_action,
        'next_heartbeat_after_s': next_after_s,
        **_bounded_mapping(evaluation.summary),
    }


def _bounded_mapping(payload: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[str(key)] = value
    return result


def _diagnostic_dedup_key(context: CliContext, evaluation: MaintenanceHeartbeatEvaluation) -> str:
    payload = {
        'project_id': context.project.project_id,
        'health': evaluation.health,
        'source_kind': evaluation.source_kind,
        'summary': _bounded_mapping(evaluation.summary),
        'evidence': list(evaluation.evidence[:_MESSAGE_EVIDENCE_LIMIT]),
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
    return f'maintenance:{digest[:20]}'


def _activation_id() -> str:
    return f'act_{uuid.uuid4().hex[:16]}'


def _active_maintenance_job(payload: Mapping[str, object], *, target_agent: str) -> str | None:
    view = payload.get('view') if isinstance(payload.get('view'), Mapping) else payload
    if not isinstance(view, Mapping):
        return None
    comms = view.get('comms')
    if not isinstance(comms, (list, tuple)):
        return None
    for item in comms:
        if not isinstance(item, Mapping):
            continue
        sender = str(item.get('sender') or '').strip()
        target = str(item.get('target') or '').strip()
        if sender != MAINTENANCE_HEARTBEAT_ACTOR or target != target_agent:
            continue
        business_status = str(item.get('business_status') or '').strip()
        status = str(item.get('status') or '').strip()
        if business_status in _ACTIVE_ACTIVATION_BUSINESS_STATUSES or status in _ACTIVE_JOB_STATUSES:
            return str(item.get('id') or '').strip() or '<unknown>'
    return None


def _repeat_count(store: MaintenanceHeartbeatStore, dedup_key: str) -> int:
    return 1 + sum(1 for item in _activation_tail(store) if item.dedup_key == dedup_key)


def _recent_duplicate(
    store: MaintenanceHeartbeatStore,
    *,
    dedup_key: str,
    observed_at: str,
    window_s: int,
) -> MaintenanceHeartbeatActivation | None:
    observed = parse_utc_timestamp(observed_at)
    for item in reversed(_activation_tail(store)):
        if item.dedup_key != dedup_key or item.status != 'submitted':
            continue
        submitted_at = item.submitted_at or item.observed_at
        try:
            submitted = parse_utc_timestamp(submitted_at)
        except Exception:
            return item
        if (observed - submitted).total_seconds() < int(window_s):
            return item
        return None
    return None


def _activation_tail(store: MaintenanceHeartbeatStore) -> tuple[MaintenanceHeartbeatActivation, ...]:
    try:
        return store.load_activation_tail(_ACTIVATION_TAIL_LIMIT)
    except Exception:
        return ()


def _activation_needs_user(activation: MaintenanceHeartbeatActivation | None) -> bool:
    return activation is not None and activation.status in {'blocked', 'failed'}


def _parse_tick_args(args: tuple[str, ...]) -> dict[str, bool]:
    force = False
    dispatch = True
    for token in args:
        if token == '--force':
            force = True
        elif token == '--no-dispatch':
            dispatch = False
        else:
            raise ValueError('tick supports only: --force, --no-dispatch')
    return {'force': force, 'dispatch': dispatch}


def _parse_schedule_args(args: tuple[str, ...]) -> dict[str, object]:
    after_s: int | None = None
    reason = 'manual_schedule'
    index = 0
    while index < len(args):
        token = args[index]
        if token == '--after':
            index += 1
            if index >= len(args):
                raise ValueError('schedule --after requires a duration')
            after_s = _duration_seconds(args[index])
        elif token == '--reason':
            index += 1
            if index >= len(args):
                raise ValueError('schedule --reason requires text')
            reason = str(args[index] or '').strip() or 'manual_schedule'
        else:
            raise ValueError('schedule supports only: --after <duration> [--reason <text>]')
        index += 1
    if after_s is None:
        raise ValueError('schedule requires --after <duration>')
    return {'after_s': after_s, 'reason': reason}


def _duration_seconds(value: str) -> int:
    text = str(value or '').strip().lower()
    if not text:
        raise ValueError('duration cannot be empty')
    multiplier = 1
    number = text
    if text[-1:] in {'s', 'm', 'h', 'd'}:
        suffix = text[-1]
        number = text[:-1]
        multiplier = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[suffix]
    try:
        amount = int(number)
    except ValueError as exc:
        raise ValueError(f'invalid duration: {value}') from exc
    seconds = amount * multiplier
    if seconds <= 0:
        raise ValueError('duration must be positive')
    return seconds


def _schedule_is_future(
    schedule: MaintenanceHeartbeatReadResult[MaintenanceHeartbeatSchedule],
    observed_at: str,
) -> bool:
    if schedule.value is None or not schedule.value.next_run_at:
        return False
    try:
        return parse_utc_timestamp(schedule.value.next_run_at) > parse_utc_timestamp(observed_at)
    except Exception:
        return False


def _heartbeat_lock(context: CliContext, *, action: str, observed_at: str) -> MaintenanceHeartbeatLock:
    return MaintenanceHeartbeatLock(
        context.paths.ccbd_maintenance_heartbeat_lock_path,
        payload={
            'schema_version': 1,
            'record_type': 'maintenance_heartbeat_lock',
            'project_id': context.project.project_id,
            'pid': os.getpid(),
            'action': action,
            'started_at': observed_at,
        },
    )


def _load_last_activation(store: MaintenanceHeartbeatStore, context: CliContext) -> dict[str, object]:
    path = context.paths.ccbd_maintenance_heartbeat_activations_path
    if not path.exists():
        return {'state': 'missing', 'path': str(path), 'error': None}
    try:
        tail = store.load_activation_tail(1)
    except Exception as exc:
        return {'state': 'corrupt', 'path': str(path), 'error': str(exc)}
    if not tail:
        return {'state': 'missing', 'path': str(path), 'error': None}
    return {'state': 'ok', 'path': str(path), 'error': None, 'record': tail[-1].to_record()}


def startup_ensure_maintenance_heartbeat(context: CliContext) -> dict | None:
    try:
        loaded = load_project_config(context.project.project_root)
        heartbeat = loaded.config.maintenance_heartbeat
        if not heartbeat.enabled or not heartbeat.startup_ensure:
            return None
        if heartbeat.assessor not in loaded.config.agents:
            return {
                'maintenance_status': 'degraded',
                'action': 'startup_ensure',
                'tick_status': 'skipped',
                'reason': f'configured heartbeat assessor is not present: {heartbeat.assessor}',
            }
        return maintenance_status(context, ParsedMaintenanceCommand(project=getattr(context.command, 'project', None), action='tick'))
    except Exception as exc:
        return {
            'maintenance_status': 'degraded',
            'action': 'startup_ensure',
            'tick_status': 'failed',
            'reason': str(exc),
        }


__all__ = ['maintenance_status', 'startup_ensure_maintenance_heartbeat']
