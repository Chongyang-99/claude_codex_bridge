from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.models import AgentSpec, PermissionMode, ProjectConfig, QueuePolicy, RestoreMode, RuntimeMode, WindowSpec, WorkspaceMode
from ccbd.project_focus import ProjectFocusDependencies, ProjectFocusError, ProjectFocusService
from ccbd.services.project_namespace import ProjectNamespaceController
from ccbd.services.project_namespace_state import ProjectNamespaceState, ProjectNamespaceStateStore
from storage.paths import PathLayout


def _spec(name: str, provider: str = 'codex') -> AgentSpec:
    return AgentSpec(
        name=name,
        provider=provider,
        target='.',
        workspace_mode=WorkspaceMode.INPLACE,
        workspace_root=None,
        runtime_mode=RuntimeMode.PANE_BACKED,
        restore_default=RestoreMode.AUTO,
        permission_default=PermissionMode.MANUAL,
        queue_policy=QueuePolicy.SERIAL_PER_AGENT,
    )


def _config() -> ProjectConfig:
    return ProjectConfig(
        version=2,
        default_agents=('agent1', 'agent2'),
        agents={'agent1': _spec('agent1'), 'agent2': _spec('agent2', 'claude')},
        cmd_enabled=False,
        layout_spec='agent1:codex',
        windows=(
            WindowSpec(name='main', order=0, layout_spec='agent1:codex', agent_names=('agent1',)),
            WindowSpec(name='ops', order=1, layout_spec='agent2:claude', agent_names=('agent2',)),
        ),
        entry_window='main',
    )


class _FakeTmuxBackend:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.panes = {
            '%1': {
                '@ccb_project_id': 'proj-1',
                '@ccb_role': 'agent',
                '@ccb_slot': 'agent1',
                '@ccb_window': 'main',
                '@ccb_managed_by': 'ccbd',
            },
            '%2': {
                '@ccb_project_id': 'proj-1',
                '@ccb_role': 'agent',
                '@ccb_slot': 'agent2',
                '@ccb_window': 'ops',
                '@ccb_managed_by': 'ccbd',
            },
        }
        self.missing_windows: set[str] = set()
        self.missing_panes: set[str] = set()

    def list_panes_by_user_options(self, expected: dict[str, str]) -> list[str]:
        matches = []
        for pane_id, options in self.panes.items():
            if pane_id in self.missing_panes:
                continue
            if all(options.get(name) == value for name, value in expected.items()):
                matches.append(pane_id)
        return matches

    def _tmux_run(self, args: list[str], *, capture=False, check=False, timeout=None):
        del check, timeout
        self.calls.append(list(args))
        if args[:2] == ['select-window', '-t']:
            window = args[2].split(':', 1)[1]
            return SimpleNamespace(returncode=1 if window in self.missing_windows else 0, stdout='', stderr='')
        if args[:2] == ['select-pane', '-t']:
            return SimpleNamespace(returncode=1 if args[2] in self.missing_panes else 0, stdout='', stderr='')
        raise AssertionError(f'unexpected tmux args: {args}, capture={capture}')


def _service(tmp_path: Path, backend: _FakeTmuxBackend, *, epoch: int = 4) -> ProjectFocusService:
    project_root = tmp_path / 'repo'
    project_root.mkdir()
    layout = PathLayout(project_root)
    ProjectNamespaceStateStore(layout).save(
        ProjectNamespaceState(
            project_id='proj-1',
            namespace_epoch=epoch,
            tmux_socket_path=str(layout.ccbd_tmux_socket_path),
            tmux_session_name='ccb-test',
            layout_version=2,
        )
    )
    controller = ProjectNamespaceController(
        layout,
        'proj-1',
        backend_factory=lambda socket_path=None: backend,
    )
    return ProjectFocusService(
        ProjectFocusDependencies(
            project_id='proj-1',
            config=_config(),
            namespace_controller=controller,
        )
    )


def test_project_focus_agent_selects_configured_window_and_pane(tmp_path: Path) -> None:
    backend = _FakeTmuxBackend()
    service = _service(tmp_path, backend)

    result = service.focus_agent(agent='agent2', namespace_epoch=4)

    assert result == {
        'focused': True,
        'kind': 'agent',
        'window': 'ops',
        'agent': 'agent2',
        'namespace_epoch': 4,
    }
    assert backend.calls == [
        ['select-window', '-t', 'ccb-test:ops'],
        ['select-pane', '-t', '%2'],
    ]


def test_project_focus_window_focuses_first_configured_agent_when_available(tmp_path: Path) -> None:
    backend = _FakeTmuxBackend()
    service = _service(tmp_path, backend)

    result = service.focus_window(window='main')

    assert result['focused'] is True
    assert result['kind'] == 'window'
    assert result['agent'] == 'agent1'
    assert backend.calls == [
        ['select-window', '-t', 'ccb-test:main'],
        ['select-pane', '-t', '%1'],
    ]


def test_project_focus_rejects_stale_namespace_epoch(tmp_path: Path) -> None:
    service = _service(tmp_path, _FakeTmuxBackend())

    with pytest.raises(ProjectFocusError, match='stale_view'):
        service.focus_agent(agent='agent1', namespace_epoch=3)


def test_project_focus_rejects_unknown_agent(tmp_path: Path) -> None:
    service = _service(tmp_path, _FakeTmuxBackend())

    with pytest.raises(ProjectFocusError, match='unknown_agent'):
        service.focus_agent(agent='missing')


def test_project_focus_reports_missing_agent_pane(tmp_path: Path) -> None:
    backend = _FakeTmuxBackend()
    backend.missing_panes.add('%2')
    service = _service(tmp_path, backend)

    with pytest.raises(ProjectFocusError, match='target_missing'):
        service.focus_agent(agent='agent2')


def test_project_focus_reports_missing_window(tmp_path: Path) -> None:
    backend = _FakeTmuxBackend()
    backend.missing_windows.add('ops')
    service = _service(tmp_path, backend)

    with pytest.raises(ProjectFocusError, match='target_missing'):
        service.focus_agent(agent='agent2')
