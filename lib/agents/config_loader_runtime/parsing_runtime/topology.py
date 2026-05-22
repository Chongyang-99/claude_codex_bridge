from __future__ import annotations

from typing import Any

from agents.config_loader_runtime.parsing_runtime.agent_specs import build_agent_spec
from agents.config_loader_runtime.parsing_runtime.expectations import expect_mapping, expect_string
from agents.models import AgentValidationError, SidebarSpec, WindowSpec, normalize_agent_name, parse_layout_spec

from ..common import ConfigValidationError


def parse_sidebar(raw_ui: Any) -> SidebarSpec | None:
    if raw_ui is None:
        return None
    ui = expect_mapping(raw_ui, field_name='ui')
    unknown_ui = sorted(set(ui) - {'sidebar'})
    if unknown_ui:
        raise ConfigValidationError(f'ui contains unknown fields: {", ".join(unknown_ui)}')
    if ui.get('sidebar') is None:
        return None
    sidebar = expect_mapping(ui['sidebar'], field_name='ui.sidebar')
    unknown_sidebar = sorted(set(sidebar) - {'mode', 'width', 'bottom_height'})
    if unknown_sidebar:
        raise ConfigValidationError(
            f'ui.sidebar contains unknown fields: {", ".join(unknown_sidebar)}'
        )
    try:
        return SidebarSpec(
            mode=sidebar.get('mode', 'every_window'),
            width=sidebar.get('width', '15%'),
            bottom_height=sidebar.get('bottom_height', 20),
        )
    except AgentValidationError as exc:
        raise ConfigValidationError(str(exc)) from exc


def parse_topology_windows(raw_windows: Any) -> tuple[WindowSpec, ...] | None:
    if raw_windows is None:
        return None
    windows_map = expect_mapping(raw_windows, field_name='windows')
    if not windows_map:
        raise ConfigValidationError('windows cannot be empty')
    windows: list[WindowSpec] = []
    seen_agents: set[str] = set()
    for index, (raw_name, raw_layout) in enumerate(windows_map.items()):
        if not isinstance(raw_name, str):
            raise ConfigValidationError('windows keys must be strings')
        layout_text = expect_string(raw_layout, field_name=f'windows.{raw_name}')
        try:
            layout = parse_layout_spec(layout_text)
            leaves = layout.iter_leaves()
            agent_names: list[str] = []
            for leaf in leaves:
                if leaf.name.strip().lower() == 'cmd':
                    raise ConfigValidationError('cmd is not supported in windows topology')
                if leaf.provider is None:
                    raise ConfigValidationError(
                        f'windows.{raw_name}: agent leaf {leaf.name!r} must declare a provider'
                    )
                normalized_name = normalize_agent_name(leaf.name)
                if normalized_name in seen_agents:
                    raise ConfigValidationError(
                        f'duplicate agent across windows: {normalized_name}'
                    )
                seen_agents.add(normalized_name)
                agent_names.append(normalized_name)
            windows.append(
                WindowSpec(
                    name=raw_name,
                    order=index,
                    layout_spec=layout.render(),
                    agent_names=tuple(agent_names),
                )
            )
        except ConfigValidationError:
            raise
        except AgentValidationError as exc:
            raise ConfigValidationError(str(exc)) from exc
        except Exception as exc:
            raise ConfigValidationError(f'windows.{raw_name}: invalid layout: {exc}') from exc
    return tuple(windows)


def agents_from_topology_windows(
    windows: tuple[WindowSpec, ...] | None,
    *,
    existing_agents: dict[str, object],
) -> dict[str, object]:
    agents = dict(existing_agents)
    if windows is None:
        return agents
    for window in windows:
        layout = parse_layout_spec(window.layout_spec)
        for leaf in layout.iter_leaves():
            name = normalize_agent_name(leaf.name)
            if name in agents:
                existing = agents[name]
                provider = getattr(existing, 'provider', None)
                if provider and str(provider).strip().lower() != str(leaf.provider).strip().lower():
                    raise ConfigValidationError(
                        f'agent {name!r} provider conflicts between windows and agents table'
                    )
                continue
            agents[name] = build_agent_spec(
                name,
                {
                    'provider': leaf.provider,
                    'target': '.',
                    'workspace_mode': 'git-worktree'
                    if str(leaf.workspace_mode or '').strip() == 'worktree'
                    else 'inplace',
                    'restore': 'auto',
                    'permission': 'manual',
                },
            )
    return agents


__all__ = ['agents_from_topology_windows', 'parse_sidebar', 'parse_topology_windows']
