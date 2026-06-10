from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

HEALTH_HEALTHY = 'healthy'
HEALTH_CONCERN = 'concern'
HEALTH_FAILING = 'failing'
HEALTH_UNKNOWN = 'unknown'

RECOMMENDED_ACTION_NONE = 'none'
RECOMMENDED_ACTION_ASSESS_LATER = 'assess_later'

_HEALTH_RANK = {
    HEALTH_HEALTHY: 0,
    HEALTH_UNKNOWN: 1,
    HEALTH_CONCERN: 2,
    HEALTH_FAILING: 3,
}
_KNOWN_ACTIVITY_STATES = {'active', 'failed', 'idle', 'offline', 'pending'}
_BENIGN_PENDING_REASONS = {
    'job_queued',
    'reconcile_active',
    'pane_missing_recovering',
}
_CONCERN_PENDING_REASONS = {
    'callback_child_completed',
    'callback_waiting_child',
    'job_running_stale',
    'provider_prompt_idle',
    'provider_prompt_input_stuck',
    'provider_waiting_for_user',
}
_UNKNOWN_PENDING_REASONS = {
    'health_unknown',
    'runtime_unknown',
}
_FAILING_COMMS_STATUSES = {
    'delivery_failed',
    'failed',
    'incomplete',
}
_CONCERN_COMMS_STATUSES = {
    'blocked',
}
_ACTIVE_COMMS_STATUSES = {
    'delivering',
    'replying',
    'sending',
}


@dataclass(frozen=True)
class MaintenanceHeartbeatEvaluation:
    health: str
    source_kind: str
    summary: dict[str, Any]
    evidence: tuple[dict[str, Any], ...] = ()

    @property
    def recommended_action(self) -> str:
        if self.health == HEALTH_HEALTHY:
            return RECOMMENDED_ACTION_NONE
        return RECOMMENDED_ACTION_ASSESS_LATER

    @property
    def needs_user(self) -> bool:
        return self.health == HEALTH_FAILING


def evaluate_project_view(payload: Mapping[str, object]) -> MaintenanceHeartbeatEvaluation:
    view = _mapping(payload.get('view')) or payload
    ccbd = _mapping(view.get('ccbd'))
    agents = _records(view.get('agents'))
    comms = _records(view.get('comms'))
    ccbd_state = _clean(ccbd.get('state') if ccbd is not None else None)
    health = HEALTH_HEALTHY
    evidence: list[dict[str, Any]] = []
    summary = {
        'source_kind': 'project_view',
        'ccbd_state': ccbd_state or None,
        'agent_count': len(agents),
        'active_agent_count': 0,
        'pending_agent_count': 0,
        'idle_agent_count': 0,
        'offline_agent_count': 0,
        'failed_agent_count': 0,
        'concern_agent_count': 0,
        'unknown_agent_count': 0,
        'comms_count': len(comms),
        'active_comms_count': 0,
        'concern_comms_count': 0,
        'failing_comms_count': 0,
    }

    if ccbd_state and ccbd_state != 'mounted':
        health = _max_health(health, HEALTH_UNKNOWN)
        evidence.append(
            _issue(
                HEALTH_UNKNOWN,
                'ccbd',
                reason='ccbd_not_mounted',
                ccbd_state=ccbd_state,
            )
        )

    for agent in agents:
        issue = _agent_issue(agent, ccbd_state=ccbd_state)
        state = _clean(agent.get('activity_state'))
        if state == 'active':
            summary['active_agent_count'] += 1
        elif state == 'pending':
            summary['pending_agent_count'] += 1
        elif state == 'idle':
            summary['idle_agent_count'] += 1
        elif state == 'offline':
            summary['offline_agent_count'] += 1
        elif state == 'failed':
            summary['failed_agent_count'] += 1
        if issue is None:
            continue
        issue_health = str(issue['health'])
        health = _max_health(health, issue_health)
        if issue_health == HEALTH_CONCERN:
            summary['concern_agent_count'] += 1
        elif issue_health == HEALTH_UNKNOWN:
            summary['unknown_agent_count'] += 1
        evidence.append(issue)

    for comm in comms:
        issue = _comms_issue(comm)
        business_status = _clean(comm.get('business_status'))
        if business_status in _ACTIVE_COMMS_STATUSES:
            summary['active_comms_count'] += 1
        if issue is None:
            continue
        issue_health = str(issue['health'])
        health = _max_health(health, issue_health)
        if issue_health == HEALTH_CONCERN:
            summary['concern_comms_count'] += 1
        elif issue_health == HEALTH_FAILING:
            summary['failing_comms_count'] += 1
        evidence.append(issue)

    return MaintenanceHeartbeatEvaluation(
        health=health,
        source_kind='project_view',
        summary=summary,
        evidence=tuple(evidence[:20]),
    )


def evaluate_ps_summary(payload: Mapping[str, object], *, error: str | None = None) -> MaintenanceHeartbeatEvaluation:
    ccbd_state = _clean(payload.get('ccbd_state'))
    agents = _records(payload.get('agents'))
    health = HEALTH_HEALTHY
    evidence: list[dict[str, Any]] = []
    summary = {
        'source_kind': 'local_ps',
        'ccbd_state': ccbd_state or None,
        'agent_count': len(agents),
        'failed_agent_count': 0,
        'concern_agent_count': 0,
        'unknown_agent_count': 0,
        'fallback_error': error,
    }
    if error:
        health = _max_health(health, HEALTH_UNKNOWN)
        evidence.append(_issue(HEALTH_UNKNOWN, 'snapshot', reason='project_view_unavailable', error=error))
    if ccbd_state and ccbd_state != 'mounted':
        health = _max_health(health, HEALTH_UNKNOWN)
        evidence.append(_issue(HEALTH_UNKNOWN, 'ccbd', reason='ccbd_not_mounted', ccbd_state=ccbd_state))

    for agent in agents:
        name = str(agent.get('agent_name') or agent.get('name') or '').strip()
        state = _clean(agent.get('state') or agent.get('runtime_state'))
        binding_status = _clean(agent.get('binding_status'))
        if state == 'failed':
            summary['failed_agent_count'] += 1
            health = _max_health(health, HEALTH_FAILING)
            evidence.append(_issue(HEALTH_FAILING, 'agent_runtime', agent=name, reason='runtime_failed', runtime_state=state))
        elif ccbd_state == 'mounted' and state in {'degraded', 'stopped', 'stopping'}:
            summary['concern_agent_count'] += 1
            health = _max_health(health, HEALTH_CONCERN)
            evidence.append(_issue(HEALTH_CONCERN, 'agent_runtime', agent=name, reason=f'runtime_{state}', runtime_state=state))
        elif ccbd_state == 'mounted' and state in {'', 'unknown'}:
            summary['unknown_agent_count'] += 1
            health = _max_health(health, HEALTH_UNKNOWN)
            evidence.append(_issue(HEALTH_UNKNOWN, 'agent_runtime', agent=name, reason='runtime_unknown'))
        if ccbd_state == 'mounted' and binding_status and binding_status != 'bound':
            summary['concern_agent_count'] += 1
            health = _max_health(health, HEALTH_CONCERN)
            evidence.append(_issue(HEALTH_CONCERN, 'agent_binding', agent=name, reason='binding_not_bound', binding_status=binding_status))

    return MaintenanceHeartbeatEvaluation(
        health=health,
        source_kind='local_ps',
        summary=summary,
        evidence=tuple(evidence[:20]),
    )


def _agent_issue(agent: Mapping[str, object], *, ccbd_state: str) -> dict[str, Any] | None:
    name = str(agent.get('name') or agent.get('agent_name') or '').strip()
    state = _clean(agent.get('activity_state'))
    reason = _clean(agent.get('activity_reason'))
    source = _clean(agent.get('activity_source'))
    if state == 'failed':
        return _issue(HEALTH_FAILING, 'agent_activity', agent=name, reason=reason or 'activity_failed', source=source)
    if state == 'offline' and ccbd_state == 'mounted':
        return _issue(HEALTH_CONCERN, 'agent_activity', agent=name, reason=reason or 'agent_offline', source=source)
    if state == 'pending' and reason in _CONCERN_PENDING_REASONS:
        return _issue(HEALTH_CONCERN, 'agent_activity', agent=name, reason=reason, source=source)
    if state == 'pending' and reason in _UNKNOWN_PENDING_REASONS:
        return _issue(HEALTH_UNKNOWN, 'agent_activity', agent=name, reason=reason, source=source)
    if state == 'pending' and reason and reason not in _BENIGN_PENDING_REASONS:
        return _issue(HEALTH_UNKNOWN, 'agent_activity', agent=name, reason=reason, source=source)
    if state and state not in _KNOWN_ACTIVITY_STATES:
        return _issue(HEALTH_UNKNOWN, 'agent_activity', agent=name, reason='activity_unknown', activity_state=state)
    return None


def _comms_issue(comm: Mapping[str, object]) -> dict[str, Any] | None:
    business_status = _clean(comm.get('business_status'))
    status = _clean(comm.get('status'))
    job_id = str(comm.get('id') or '').strip()
    target = str(comm.get('target') or '').strip()
    if business_status in _FAILING_COMMS_STATUSES or status in {'failed', 'incomplete'}:
        return _issue(
            HEALTH_FAILING,
            'comms',
            job_id=job_id,
            target=target,
            reason=business_status or status or 'comms_failed',
            status=status,
        )
    if business_status in _CONCERN_COMMS_STATUSES:
        return _issue(
            HEALTH_CONCERN,
            'comms',
            job_id=job_id,
            target=target,
            reason=str(comm.get('block_reason') or business_status or 'comms_blocked'),
            status=status,
        )
    return None


def _issue(health: str, kind: str, **fields: object) -> dict[str, Any]:
    record: dict[str, Any] = {'health': health, 'kind': kind}
    for key, value in fields.items():
        if value is not None and value != '':
            record[key] = value
    return record


def _records(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _clean(value: object) -> str:
    return str(value or '').strip().lower()


def _max_health(current: str, candidate: str) -> str:
    if _HEALTH_RANK.get(candidate, 0) > _HEALTH_RANK.get(current, 0):
        return candidate
    return current


__all__ = [
    'HEALTH_CONCERN',
    'HEALTH_FAILING',
    'HEALTH_HEALTHY',
    'HEALTH_UNKNOWN',
    'MaintenanceHeartbeatEvaluation',
    'evaluate_project_view',
    'evaluate_ps_summary',
]
