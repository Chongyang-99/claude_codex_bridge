from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from agents.models_runtime.layout import LayoutNode, parse_layout_spec, prune_layout

from ..names import AgentValidationError, normalize_agent_name


_WINDOW_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_-]*$')
SIDEBAR_MODE_EVERY_WINDOW = 'every_window'
SIDEBAR_MODE_OFF = 'off'


@dataclass(frozen=True)
class SidebarSpec:
    mode: str = SIDEBAR_MODE_EVERY_WINDOW
    width: str | int = '15%'
    bottom_height: int = 20

    def __post_init__(self) -> None:
        mode = str(self.mode or '').strip()
        if mode not in {SIDEBAR_MODE_EVERY_WINDOW, SIDEBAR_MODE_OFF}:
            raise AgentValidationError('ui.sidebar.mode must be every_window or off')
        object.__setattr__(self, 'mode', mode)
        object.__setattr__(self, 'width', normalize_sidebar_width(self.width))
        try:
            bottom_height = int(self.bottom_height)
        except Exception as exc:
            raise AgentValidationError('ui.sidebar.bottom_height must be a non-negative integer') from exc
        if bottom_height < 0:
            raise AgentValidationError('ui.sidebar.bottom_height must be a non-negative integer')
        object.__setattr__(self, 'bottom_height', bottom_height)

    def to_record(self) -> dict[str, object]:
        return {
            'mode': self.mode,
            'width': self.width,
            'bottom_height': self.bottom_height,
        }


@dataclass(frozen=True)
class WindowSpec:
    name: str
    order: int
    layout_spec: str
    agent_names: tuple[str, ...]

    def __post_init__(self) -> None:
        name = validate_window_name(self.name)
        try:
            order = int(self.order)
        except Exception as exc:
            raise AgentValidationError('window order must be an integer') from exc
        layout_spec = str(self.layout_spec or '').strip()
        if not layout_spec:
            raise AgentValidationError(f'windows.{name} layout cannot be empty')
        agent_names = tuple(normalize_agent_name(item) for item in self.agent_names)
        if not agent_names:
            raise AgentValidationError(f'windows.{name} must contain at least one agent')
        if len(set(agent_names)) != len(agent_names):
            raise AgentValidationError(f'windows.{name} cannot contain duplicate agents')
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'order', order)
        object.__setattr__(self, 'layout_spec', layout_spec)
        object.__setattr__(self, 'agent_names', agent_names)

    def to_record(self) -> dict[str, object]:
        return {
            'name': self.name,
            'order': self.order,
            'layout_spec': self.layout_spec,
            'agent_names': list(self.agent_names),
        }


def default_sidebar_spec() -> SidebarSpec:
    return SidebarSpec()


def validate_window_name(value: str) -> str:
    name = str(value or '').strip()
    if not _WINDOW_NAME_RE.fullmatch(name):
        raise AgentValidationError(
            f'invalid window name {name!r}; expected ^[A-Za-z][A-Za-z0-9_-]*$'
        )
    return name


def normalize_sidebar_width(value: str | int) -> str | int:
    if isinstance(value, bool):
        raise AgentValidationError('ui.sidebar.width must be a positive integer or percentage string')
    if isinstance(value, int):
        if value <= 0:
            raise AgentValidationError('ui.sidebar.width must be positive')
        return value
    text = str(value or '').strip()
    if text.endswith('%'):
        number = text[:-1].strip()
        if not number.isdigit() or int(number) <= 0:
            raise AgentValidationError('ui.sidebar.width percentage must be positive')
        return f'{int(number)}%'
    if text.isdigit() and int(text) > 0:
        return int(text)
    raise AgentValidationError('ui.sidebar.width must be a positive integer or percentage string')


def normalize_windows(
    windows: tuple[WindowSpec, ...] | None,
    *,
    layout_spec: str,
    default_agents: tuple[str, ...],
) -> tuple[WindowSpec, ...]:
    if windows:
        return _validate_windows(windows)
    return (legacy_main_window(layout_spec=layout_spec, default_agents=default_agents),)


def legacy_main_window(*, layout_spec: str, default_agents: tuple[str, ...]) -> WindowSpec:
    layout = parse_layout_spec(layout_spec)
    pruned = prune_layout(layout, include_names=default_agents)
    if pruned is None:
        raise AgentValidationError('legacy layout does not contain any configured agents')
    leaf_names = tuple(normalize_agent_name(leaf.name) for leaf in pruned.iter_leaves())
    return WindowSpec(
        name='main',
        order=0,
        layout_spec=pruned.render(),
        agent_names=leaf_names,
    )


def _validate_windows(windows: tuple[WindowSpec, ...]) -> tuple[WindowSpec, ...]:
    if not windows:
        raise AgentValidationError('at least one window must be configured')
    seen_windows: set[str] = set()
    seen_agents: set[str] = set()
    normalized: list[WindowSpec] = []
    for index, window in enumerate(windows):
        spec = WindowSpec(
            name=window.name,
            order=index,
            layout_spec=window.layout_spec,
            agent_names=window.agent_names,
        )
        if spec.name in seen_windows:
            raise AgentValidationError(f'duplicate window name: {spec.name}')
        seen_windows.add(spec.name)
        duplicates = [name for name in spec.agent_names if name in seen_agents]
        if duplicates:
            raise AgentValidationError(f'duplicate agent across windows: {duplicates[0]}')
        seen_agents.update(spec.agent_names)
        normalized.append(spec)
    return tuple(normalized)


def validate_entry_window(entry_window: str | None, *, windows: tuple[WindowSpec, ...]) -> str:
    if not windows:
        raise AgentValidationError('at least one window must be configured')
    value = str(entry_window or '').strip() or windows[0].name
    value = validate_window_name(value)
    names = {window.name for window in windows}
    if value not in names:
        raise AgentValidationError(f'entry_window references unknown window: {value}')
    return value


def validate_windows_reference_agents(
    windows: tuple[WindowSpec, ...],
    *,
    normalized_agents: dict[str, object],
) -> None:
    configured = set(normalized_agents)
    referenced: list[str] = []
    for window in windows:
        referenced.extend(window.agent_names)
    missing = [name for name in referenced if name not in configured]
    if missing:
        raise AgentValidationError(f'windows reference unknown agents: {missing}')
    unused = [name for name in configured if name not in set(referenced)]
    if unused:
        raise AgentValidationError(f'configured agents missing from windows: {unused}')


def topology_signature_payload(
    *,
    windows: tuple[WindowSpec, ...],
    entry_window: str,
    sidebar: SidebarSpec,
) -> dict[str, object]:
    return {
        'version': 1,
        'windows': [
            {
                'name': window.name,
                'order': window.order,
                'layout': window.layout_spec,
                'agents': list(window.agent_names),
            }
            for window in windows
        ],
        'entry_window': entry_window,
        'sidebar': sidebar.to_record(),
    }


def topology_signature(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    'SIDEBAR_MODE_EVERY_WINDOW',
    'SIDEBAR_MODE_OFF',
    'SidebarSpec',
    'WindowSpec',
    'default_sidebar_spec',
    'legacy_main_window',
    'normalize_sidebar_width',
    'normalize_windows',
    'topology_signature',
    'topology_signature_payload',
    'validate_entry_window',
    'validate_window_name',
    'validate_windows_reference_agents',
]
