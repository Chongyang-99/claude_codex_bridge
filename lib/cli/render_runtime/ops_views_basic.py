from __future__ import annotations

from collections.abc import Mapping

from .common import render_tmux_cleanup_summaries
from .ops_views_common import binding_line


def render_config_validate(summary) -> tuple[str, ...]:
    return (
        'config_status: valid',
        f'project: {summary.project_root}',
        f'project_id: {summary.project_id}',
        f'config_source_kind: {summary.source_kind}',
        f'config_source: {summary.source or "<builtin>"}',
        f'used_builtin_default: {str(summary.used_builtin_default).lower()}',
        f'default_agents: {", ".join(summary.default_agents)}',
        f'agents: {", ".join(summary.agent_names)}',
        f'cmd_enabled: {str(summary.cmd_enabled).lower()}',
        f'layout: {summary.layout_spec}',
    )


def render_start(summary) -> tuple[str, ...]:
    lines = [
        'start_status: ok',
        f'project: {summary.project_root}',
        f'project_id: {summary.project_id}',
        f'ccbd_started: {str(summary.daemon_started).lower()}',
        f'socket_path: {summary.socket_path}',
        f'agents: {", ".join(summary.started)}',
    ]
    lines.extend(render_tmux_cleanup_summaries(getattr(summary, 'cleanup_summaries', ()) or ()))
    return tuple(lines)


def render_logs(summary) -> tuple[str, ...]:
    lines = [
        'logs_status: ok',
        f'project_id: {summary.project_id}',
        f'agent_name: {summary.agent_name}',
        f'provider: {summary.provider}',
        f'runtime_ref: {summary.runtime_ref}',
        f'session_ref: {summary.session_ref}',
        f'log_count: {len(summary.entries)}',
    ]
    if not summary.entries:
        lines.append('log: <none>')
        return tuple(lines)
    for entry in summary.entries:
        lines.append(f'log: {entry.source} {entry.path}')
        for line in entry.lines:
            lines.append(f'log_line: {line}')
    return tuple(lines)


def render_doctor_bundle(summary) -> tuple[str, ...]:
    return (
        'doctor_bundle_status: ok',
        f'project: {summary.project_root}',
        f'project_id: {summary.project_id}',
        f'bundle_id: {summary.bundle_id}',
        f'bundle_path: {summary.bundle_path}',
        f'file_count: {summary.file_count}',
        f'included_count: {summary.included_count}',
        f'missing_count: {summary.missing_count}',
        f'truncated_count: {summary.truncated_count}',
        f'doctor_error: {summary.doctor_error}',
    )


def render_cleanup(summary) -> tuple[str, ...]:
    lines = [
        f'cleanup_status: {summary.status}',
        f'project_root: {summary.project_root}',
        f'project_id: {summary.project_id}',
        f'cleanup_deleted_bytes: {summary.deleted_bytes}',
        f'cleanup_deleted_count: {summary.deleted_count}',
        f'cleanup_skipped_count: {summary.skipped_count}',
    ]
    for action in getattr(summary, 'actions', ()) or ():
        lines.append(
            'cleanup_action: '
            f'provider={action.provider} '
            f'kind={action.kind} '
            f'bytes={action.bytes_removed} '
            f'reason={action.reason} '
            f'path={action.path}'
        )
    for skipped in getattr(summary, 'skipped', ()) or ():
        lines.append(
            'cleanup_skipped: '
            f'provider={skipped.provider} '
            f'reason={skipped.reason} '
            f'path={skipped.path}'
        )
    return tuple(lines)


def render_clear(summary) -> tuple[str, ...]:
    results = tuple(summary.get('results', ()) or ()) if isinstance(summary, Mapping) else ()
    cleared_count = sum(1 for item in results if item.get('status') == 'cleared')
    skipped_count = sum(1 for item in results if item.get('status') == 'skipped')
    failed_count = sum(1 for item in results if item.get('status') == 'failed')
    lines = [
        f'clear_status: {summary.get("status", "unknown") if isinstance(summary, Mapping) else "unknown"}',
        f'cleared_count: {cleared_count}',
        f'skipped_count: {skipped_count}',
        f'failed_count: {failed_count}',
    ]
    for item in results:
        agent = str(item.get('agent') or '')
        status = str(item.get('status') or '')
        pane_id = str(item.get('pane_id') or '')
        reason = str(item.get('reason') or '')
        detail = f'agent={agent} status={status}'
        if pane_id:
            detail += f' pane_id={pane_id}'
        if reason:
            detail += f' reason={reason}'
        lines.append(f'clear_agent: {detail}')
    return tuple(lines)


def render_restart(summary) -> tuple[str, ...]:
    payload = summary if isinstance(summary, Mapping) else {}
    status = str(payload.get('restart_status') or payload.get('status') or 'unknown')
    lines = [
        f'restart_status: {status}',
        f'agent_name: {payload.get("agent_name", "")}',
    ]
    restartable = tuple(str(item) for item in (payload.get('restartable_agents') or ()) if str(item))
    if restartable:
        lines.append(f'restartable_agents: {", ".join(restartable)}')
    reason = str(payload.get('reason') or '').strip()
    if reason:
        lines.append(f'reason: {reason}')
    busy_gate = payload.get('busy_gate')
    if isinstance(busy_gate, Mapping):
        lines.append(_restart_busy_gate_line(busy_gate))
    blockers = tuple(payload.get('blockers') or ())
    for blocker in blockers:
        if isinstance(blocker, Mapping):
            reason_text = str(blocker.get('reason') or '').strip()
            detail = str(blocker.get('detail') or '').strip()
            line = f'blocker: reason={reason_text}'
            if detail:
                line += f' detail={detail}'
            lines.append(line)
        else:
            lines.append(f'blocker: {blocker}')
    old_runtime = payload.get('old_runtime')
    if isinstance(old_runtime, Mapping):
        lines.append(f'old_runtime: {_runtime_evidence_text(old_runtime)}')
    new_runtime = payload.get('new_runtime')
    if isinstance(new_runtime, Mapping):
        lines.append(f'new_runtime: {_runtime_evidence_text(new_runtime)}')
    result = payload.get('result')
    if isinstance(result, Mapping):
        lines.append(f'restart_result: {_flat_mapping_text(result)}')
    error = str(payload.get('error') or '').strip()
    if error:
        lines.append(f'error: {error}')
    return tuple(lines)


def _restart_busy_gate_line(gate: Mapping[str, object]) -> str:
    fields = {
        'passed': str(bool(gate.get('passed'))).lower(),
        'runtime_state': gate.get('runtime_state'),
        'runtime_queue_depth': gate.get('runtime_queue_depth'),
        'queue_depth': gate.get('queue_depth'),
        'pending_reply_count': gate.get('pending_reply_count'),
        'active_job_id': gate.get('active_job_id'),
        'active_inbound_event_id': gate.get('active_inbound_event_id'),
        'pending_callback_count': gate.get('pending_callback_count'),
    }
    return 'restart_busy_gate: ' + _flat_mapping_text(fields)


def _runtime_evidence_text(evidence: Mapping[str, object]) -> str:
    fields = {
        'state': evidence.get('state'),
        'health': evidence.get('health'),
        'pane_id': evidence.get('pane_id'),
        'active_pane_id': evidence.get('active_pane_id'),
        'runtime_ref': evidence.get('runtime_ref'),
        'session_ref': evidence.get('session_ref'),
        'runtime_pid': evidence.get('runtime_pid'),
        'restart_count': evidence.get('restart_count'),
    }
    return _flat_mapping_text(fields)


def _flat_mapping_text(payload: Mapping[str, object]) -> str:
    return ' '.join(f'{key}={_render_value(value)}' for key, value in payload.items())


def _render_value(value: object) -> str:
    if value is None:
        return 'None'
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, tuple)):
        return ','.join(str(item) for item in value)
    return str(value).replace('\n', '\\n')


def render_kill(summary) -> tuple[str, ...]:
    lines = [
        'kill_status: ok',
        f'project_id: {summary.project_id}',
        f'state: {summary.state}',
        f'socket_path: {summary.socket_path}',
        f'forced: {str(summary.forced).lower()}',
    ]
    lines.extend(render_tmux_cleanup_summaries(getattr(summary, 'cleanup_summaries', ()) or ()))
    return tuple(lines)


def render_ps(payload: Mapping[str, object]) -> tuple[str, ...]:
    lines = [
        f'project_id: {payload["project_id"]}',
        f'ccbd_state: {payload["ccbd_state"]}',
    ]
    for agent in payload['agents']:
        lines.append(
            f'agent: name={agent["agent_name"]} state={agent["state"]} provider={agent["provider"]} queue={agent["queue_depth"]}'
        )
        lines.append(binding_line(agent))
    return tuple(lines)


__all__ = [
    'render_clear',
    'render_cleanup',
    'render_config_validate',
    'render_doctor_bundle',
    'render_kill',
    'render_logs',
    'render_ps',
    'render_restart',
    'render_start',
]
