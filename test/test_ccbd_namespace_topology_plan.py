from __future__ import annotations

from agents.config_loader import build_default_project_config
from agents.models import AgentSpec, PermissionMode, ProjectConfig, QueuePolicy, RestoreMode, RuntimeMode, SidebarSpec, WindowSpec, WorkspaceMode
from ccbd.services.project_namespace_runtime import build_namespace_topology_plan


def _spec(name: str, provider: str) -> AgentSpec:
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


def test_namespace_topology_plan_projects_sidebar_outside_user_layout() -> None:
    config = build_default_project_config()

    plan = build_namespace_topology_plan(
        config,
        ccbd_socket_path='/tmp/ccbd.sock',
        project_root='/repo',
    )

    assert plan.signature == config.topology_signature
    assert plan.entry_window == 'main'
    assert plan.sidebar_enabled is True
    assert len(plan.windows) == 1
    window = plan.windows[0]
    assert window.name == 'main'
    assert window.user_layout == 'agent1:codex, agent2:codex, agent3:claude'
    assert window.realized_layout == 'sidebar; (agent1:codex, agent2:codex, agent3:claude)'
    assert window.sidebar is not None
    assert window.sidebar.width == '15%'
    assert window.sidebar.launch_args == (
        'ccb-agent-sidebar',
        '--ccbd-socket',
        '/tmp/ccbd.sock',
        '--project-root',
        '/repo',
        '--pane-window',
        'main',
    )


def test_namespace_topology_plan_leaves_layout_plain_when_sidebar_off() -> None:
    config = ProjectConfig(
        version=2,
        default_agents=('agent1',),
        agents={'agent1': _spec('agent1', 'codex')},
        layout_spec='agent1:codex',
        windows=(WindowSpec(name='main', order=0, layout_spec='agent1:codex', agent_names=('agent1',)),),
        entry_window='main',
        sidebar=SidebarSpec(mode='off', width='15%', bottom_height=20),
    )

    plan = build_namespace_topology_plan(config)

    assert plan.sidebar_enabled is False
    assert plan.windows[0].realized_layout == 'agent1:codex'
    assert plan.windows[0].sidebar is None
