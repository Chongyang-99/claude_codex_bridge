from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SidebarPanePlan:
    mode: str
    width: str | int
    bottom_height: int
    launch_args: tuple[str, ...] = ()

    def to_record(self) -> dict[str, object]:
        return {
            'mode': self.mode,
            'width': self.width,
            'bottom_height': self.bottom_height,
            'launch_args': list(self.launch_args),
        }


@dataclass(frozen=True)
class NamespaceWindowPlan:
    name: str
    order: int
    user_layout: str
    realized_layout: str
    agent_names: tuple[str, ...]
    sidebar: SidebarPanePlan | None = None

    def to_record(self) -> dict[str, object]:
        return {
            'name': self.name,
            'order': self.order,
            'user_layout': self.user_layout,
            'realized_layout': self.realized_layout,
            'agent_names': list(self.agent_names),
            'sidebar': self.sidebar.to_record() if self.sidebar is not None else None,
        }


@dataclass(frozen=True)
class NamespaceTopologyPlan:
    signature: str
    entry_window: str
    windows: tuple[NamespaceWindowPlan, ...]
    sidebar_enabled: bool

    def to_record(self) -> dict[str, object]:
        return {
            'signature': self.signature,
            'entry_window': self.entry_window,
            'sidebar_enabled': self.sidebar_enabled,
            'windows': [window.to_record() for window in self.windows],
        }


def build_namespace_topology_plan(config, *, ccbd_socket_path: str | None = None, project_root: str | None = None) -> NamespaceTopologyPlan:
    sidebar_enabled = config.sidebar.mode == 'every_window'
    windows = tuple(
        _window_plan(
            window,
            sidebar=config.sidebar if sidebar_enabled else None,
            ccbd_socket_path=ccbd_socket_path,
            project_root=project_root,
        )
        for window in config.windows
    )
    return NamespaceTopologyPlan(
        signature=config.topology_signature,
        entry_window=config.entry_window,
        windows=windows,
        sidebar_enabled=sidebar_enabled,
    )


def _window_plan(window, *, sidebar, ccbd_socket_path: str | None, project_root: str | None) -> NamespaceWindowPlan:
    sidebar_plan = (
        SidebarPanePlan(
            mode=sidebar.mode,
            width=sidebar.width,
            bottom_height=sidebar.bottom_height,
            launch_args=_sidebar_launch_args(ccbd_socket_path=ccbd_socket_path, project_root=project_root, window_name=window.name),
        )
        if sidebar is not None
        else None
    )
    return NamespaceWindowPlan(
        name=window.name,
        order=window.order,
        user_layout=window.layout_spec,
        realized_layout=_realized_layout(window.layout_spec, sidebar_enabled=sidebar is not None),
        agent_names=window.agent_names,
        sidebar=sidebar_plan,
    )


def _realized_layout(user_layout: str, *, sidebar_enabled: bool) -> str:
    if not sidebar_enabled:
        return user_layout
    return f'sidebar; ({user_layout})'


def _sidebar_launch_args(*, ccbd_socket_path: str | None, project_root: str | None, window_name: str) -> tuple[str, ...]:
    args = ['ccb-agent-sidebar']
    if ccbd_socket_path:
        args.extend(['--ccbd-socket', str(ccbd_socket_path)])
    if project_root:
        args.extend(['--project-root', str(project_root)])
    args.extend(['--pane-window', window_name])
    return tuple(args)


__all__ = [
    'NamespaceTopologyPlan',
    'NamespaceWindowPlan',
    'SidebarPanePlan',
    'build_namespace_topology_plan',
]
