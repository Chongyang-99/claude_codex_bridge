from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
import time
from typing import Any


RECOVERY_HINT = "Run `ccb restart <agent>`, send a smoke ask, then retry intentionally."


@dataclass(frozen=True)
class PidEvidence:
    label: str
    path: str | None
    pid: int | None
    status: str
    alive: bool | None
    error: str | None = None

    def to_record(self) -> dict[str, object]:
        return {
            "label": self.label,
            "path": self.path,
            "pid": self.pid,
            "status": self.status,
            "alive": self.alive,
            "error": self.error,
        }


@dataclass(frozen=True)
class FileEvidence:
    path: str | None
    exists: bool | None
    readable: bool | None
    size: int | None
    mtime_epoch: float | None
    age_s: float | None
    error: str | None = None

    def to_record(self) -> dict[str, object]:
        return {
            "path": self.path,
            "exists": self.exists,
            "readable": self.readable,
            "size": self.size,
            "mtime_epoch": self.mtime_epoch,
            "age_s": self.age_s,
            "error": self.error,
        }


@dataclass(frozen=True)
class CodexBindingEvidence:
    binding_state: str
    unhealthy_reasons: tuple[str, ...]
    suspicious_reasons: tuple[str, ...]
    managed_runtime_expected: bool
    runtime_dir: str | None
    input_fifo: str | None
    input_fifo_exists: bool | None
    pane_id: str | None
    pane_alive: bool | None
    tmux_pane_pid: int | None
    tmux_pane_pid_status: str
    tmux_pane_pid_error: str | None
    codex_pid: PidEvidence
    bridge_pid: PidEvidence
    codex_pid_matches_pane_pid: bool | None
    pid_mismatch: bool
    session_file: str | None
    session_id: str | None
    ccb_session_id: str | None
    session_log: FileEvidence
    activity: FileEvidence
    checked_at_epoch: float

    @property
    def preflight_failed(self) -> bool:
        return bool(self.unhealthy_reasons)

    def to_record(self) -> dict[str, object]:
        return {
            "provider": "codex",
            "binding_state": self.binding_state,
            "unhealthy_reasons": list(self.unhealthy_reasons),
            "suspicious_reasons": list(self.suspicious_reasons),
            "managed_runtime_expected": self.managed_runtime_expected,
            "runtime_dir": self.runtime_dir,
            "input_fifo": self.input_fifo,
            "input_fifo_exists": self.input_fifo_exists,
            "pane_id": self.pane_id,
            "pane_alive": self.pane_alive,
            "tmux_pane_pid": self.tmux_pane_pid,
            "tmux_pane_pid_status": self.tmux_pane_pid_status,
            "tmux_pane_pid_error": self.tmux_pane_pid_error,
            "codex_pid": self.codex_pid.to_record(),
            "bridge_pid": self.bridge_pid.to_record(),
            "codex_pid_matches_pane_pid": self.codex_pid_matches_pane_pid,
            "pid_mismatch": self.pid_mismatch,
            "session_file": self.session_file,
            "session_id": self.session_id,
            "ccb_session_id": self.ccb_session_id,
            "session_log": self.session_log.to_record(),
            "activity": self.activity.to_record(),
            "preflight_failed": self.preflight_failed,
            "retryable": self.preflight_failed,
            "auto_retry_allowed": False,
            "recovery_hint": RECOVERY_HINT if self.preflight_failed else None,
            "checked_at_epoch": self.checked_at_epoch,
        }


def collect_codex_binding_evidence(
    *,
    session: object | None = None,
    backend: object | None = None,
    pane_id: str | None = None,
    runtime_dir: str | Path | None = None,
    input_fifo: str | Path | None = None,
    session_log_path: str | Path | None = None,
    session_file: str | Path | None = None,
    session_id: str | None = None,
    ccb_session_id: str | None = None,
    managed_runtime_expected: bool | None = None,
    now_epoch: float | None = None,
) -> CodexBindingEvidence:
    checked_at = time.time() if now_epoch is None else float(now_epoch)
    data = _session_data(session)
    session_runtime_root = _path_or_none(getattr(session, "runtime_dir", None)) if session is not None else None
    explicit_runtime_dir = (
        runtime_dir is not None
        or bool(str(data.get("runtime_dir") or "").strip())
        or session_runtime_root is not None
    )
    runtime_root = _path_or_none(runtime_dir) or _path_or_none(data.get("runtime_dir")) or session_runtime_root
    expects_managed = explicit_runtime_dir if managed_runtime_expected is None else bool(managed_runtime_expected)

    resolved_pane_id = _clean_text(pane_id) or _clean_text(getattr(session, "pane_id", None))
    codex_pid = _pid_evidence("codex", runtime_root / "codex.pid" if runtime_root is not None else None)
    bridge_pid = _pid_evidence("bridge", runtime_root / "bridge.pid" if runtime_root is not None else None)
    pane_alive = _pane_alive(backend, resolved_pane_id) if expects_managed else None
    if expects_managed:
        pane_pid, pane_pid_status, pane_pid_error = _tmux_pane_pid(backend, resolved_pane_id)
    else:
        pane_pid, pane_pid_status, pane_pid_error = None, "missing", None
    pid_match = _pid_match(codex_pid.pid, pane_pid)
    pid_mismatch = pid_match is False

    session_log = _file_evidence(
        _path_or_none(session_log_path)
        or _path_or_none(getattr(session, "codex_session_path", None))
        or _path_or_none(data.get("codex_session_path")),
        now_epoch=checked_at,
    )
    activity = _file_evidence(
        runtime_root / "activity.json" if runtime_root is not None else None,
        now_epoch=checked_at,
    )
    input_path = _path_or_none(input_fifo) or (runtime_root / "input.fifo" if runtime_root is not None else None)
    input_exists = input_path.exists() if input_path is not None else None

    unhealthy = _unhealthy_reasons(
        managed_runtime_expected=expects_managed,
        input_fifo_exists=input_exists,
        pane_alive=pane_alive,
        codex_pid=codex_pid,
        bridge_pid=bridge_pid,
        pid_mismatch=pid_mismatch,
        session_log=session_log,
    )
    suspicious = _suspicious_reasons(
        managed_runtime_expected=expects_managed,
        runtime_dir=runtime_root,
        pane_alive=pane_alive,
        pane_pid_status=pane_pid_status,
        session_log=session_log,
    )
    binding_state = _binding_state(unhealthy, suspicious, managed_runtime_expected=expects_managed)

    return CodexBindingEvidence(
        binding_state=binding_state,
        unhealthy_reasons=tuple(unhealthy),
        suspicious_reasons=tuple(suspicious),
        managed_runtime_expected=expects_managed,
        runtime_dir=str(runtime_root) if runtime_root is not None else None,
        input_fifo=str(input_path) if input_path is not None else None,
        input_fifo_exists=input_exists,
        pane_id=resolved_pane_id,
        pane_alive=pane_alive,
        tmux_pane_pid=pane_pid,
        tmux_pane_pid_status=pane_pid_status,
        tmux_pane_pid_error=pane_pid_error,
        codex_pid=codex_pid,
        bridge_pid=bridge_pid,
        codex_pid_matches_pane_pid=pid_match,
        pid_mismatch=pid_mismatch,
        session_file=str(_path_or_none(session_file) or _path_or_none(getattr(session, "session_file", None)) or "")
        or None,
        session_id=_clean_text(session_id) or _clean_text(getattr(session, "codex_session_id", None)) or _clean_text(data.get("codex_session_id")),
        ccb_session_id=_clean_text(ccb_session_id) or _clean_text(getattr(session, "ccb_session_id", None)) or _clean_text(data.get("ccb_session_id")),
        session_log=session_log,
        activity=activity,
        checked_at_epoch=checked_at,
    )


def binding_preflight_diagnostics(evidence: CodexBindingEvidence) -> dict[str, object]:
    reasons = list(evidence.unhealthy_reasons)
    reason = reasons[0] if reasons else "codex_binding_unhealthy"
    return {
        "reason": "codex_binding_unhealthy",
        "error": reason,
        "error_type": "provider_runtime_binding_stale",
        "provider_runtime_error": True,
        "retryable": True,
        "auto_retry_allowed": False,
        "recovery_hint": RECOVERY_HINT,
        "binding_evidence": evidence.to_record(),
    }


def _unhealthy_reasons(
    *,
    managed_runtime_expected: bool,
    input_fifo_exists: bool | None,
    pane_alive: bool | None,
    codex_pid: PidEvidence,
    bridge_pid: PidEvidence,
    pid_mismatch: bool,
    session_log: FileEvidence,
) -> list[str]:
    reasons: list[str] = []
    if managed_runtime_expected and pane_alive is False:
        reasons.append("pane_dead")
    if managed_runtime_expected:
        _append_pid_reason(reasons, "codex_pid", codex_pid)
        _append_pid_reason(reasons, "bridge_pid", bridge_pid)
        if input_fifo_exists is False:
            reasons.append("input_fifo_missing")
    if managed_runtime_expected and pid_mismatch:
        reasons.append("codex_pid_pane_pid_mismatch")
    if managed_runtime_expected and session_log.path and session_log.exists is False:
        reasons.append("session_log_missing")
    if managed_runtime_expected and session_log.path and session_log.exists and session_log.readable is False:
        reasons.append("session_log_unreadable")
    return reasons


def _append_pid_reason(reasons: list[str], prefix: str, evidence: PidEvidence) -> None:
    if evidence.status == "alive":
        return
    if evidence.status in {"missing", "invalid", "dead"}:
        reasons.append(f"{prefix}_{evidence.status}")


def _suspicious_reasons(
    *,
    managed_runtime_expected: bool,
    runtime_dir: Path | None,
    pane_alive: bool | None,
    pane_pid_status: str,
    session_log: FileEvidence,
) -> list[str]:
    reasons: list[str] = []
    if not managed_runtime_expected:
        reasons.append("managed_runtime_artifacts_not_declared")
    if pane_pid_status not in {"available", "missing"}:
        reasons.append(f"tmux_pane_pid_{pane_pid_status}")
    if pane_pid_status == "missing" and pane_alive is False:
        reasons.append("pane_dead")
    if runtime_dir is None:
        reasons.append("runtime_dir_unknown")
    if not session_log.path:
        reasons.append("session_log_path_unknown")
    if not managed_runtime_expected and session_log.path and session_log.exists is False:
        reasons.append("session_log_missing")
    if not managed_runtime_expected and session_log.path and session_log.exists and session_log.readable is False:
        reasons.append("session_log_unreadable")
    return reasons


def _binding_state(unhealthy: list[str], suspicious: list[str], *, managed_runtime_expected: bool) -> str:
    if unhealthy:
        return "unhealthy"
    if suspicious:
        return "suspicious" if managed_runtime_expected else "unknown"
    return "healthy"


def _pid_evidence(label: str, path: Path | None) -> PidEvidence:
    if path is None:
        return PidEvidence(label=label, path=None, pid=None, status="unknown", alive=None)
    if not path.exists():
        return PidEvidence(label=label, path=str(path), pid=None, status="missing", alive=False)
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        return PidEvidence(label=label, path=str(path), pid=None, status="invalid", alive=False, error=str(exc))
    pid = _positive_int(raw)
    if pid is None:
        return PidEvidence(label=label, path=str(path), pid=None, status="invalid", alive=False)
    alive = _pid_alive(pid)
    return PidEvidence(label=label, path=str(path), pid=pid, status="alive" if alive else "dead", alive=alive)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        try:
            result = subprocess.run(["ps", "-p", str(pid)], capture_output=True, timeout=2)
            return result.returncode == 0
        except Exception:
            return True
    except OSError:
        return False


def _tmux_pane_pid(backend: object | None, pane_id: str | None) -> tuple[int | None, str, str | None]:
    if not pane_id:
        return None, "missing", None
    if backend is None:
        return None, "unknown", "terminal backend unavailable"
    reader = getattr(backend, "pane_pid", None)
    if callable(reader):
        try:
            pid = _positive_int(reader(pane_id))
        except Exception as exc:
            return None, "unavailable", str(exc)
        return (pid, "available", None) if pid is not None else (None, "unavailable", "pane_pid returned no pid")
    runner = getattr(backend, "_tmux_run", None)
    if not callable(runner):
        return None, "unknown", "terminal backend does not expose pane_pid"
    try:
        result = runner(["display-message", "-p", "-t", pane_id, "#{pane_pid}"], capture=True, timeout=1.0)
    except Exception as exc:
        return None, "unavailable", str(exc)
    if getattr(result, "returncode", 0) not in (0, None):
        return None, "unavailable", str(getattr(result, "stderr", "") or "").strip() or "tmux pane pid probe failed"
    pid = _positive_int(getattr(result, "stdout", "") or "")
    if pid is None:
        return None, "unavailable", "tmux pane pid probe returned no pid"
    return pid, "available", None


def _pane_alive(backend: object | None, pane_id: str | None) -> bool | None:
    if not pane_id or backend is None:
        return None
    for name in ("is_tmux_pane_alive", "is_alive"):
        checker = getattr(backend, name, None)
        if not callable(checker):
            continue
        try:
            return bool(checker(pane_id))
        except Exception:
            return False
    return None


def _file_evidence(path: Path | None, *, now_epoch: float) -> FileEvidence:
    if path is None:
        return FileEvidence(path=None, exists=None, readable=None, size=None, mtime_epoch=None, age_s=None)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return FileEvidence(path=str(path), exists=False, readable=False, size=None, mtime_epoch=None, age_s=None)
    except Exception as exc:
        return FileEvidence(path=str(path), exists=None, readable=False, size=None, mtime_epoch=None, age_s=None, error=str(exc))
    readable = None
    if path.is_file():
        try:
            with path.open("rb"):
                pass
            readable = True
        except Exception:
            readable = False
    return FileEvidence(
        path=str(path),
        exists=True,
        readable=readable,
        size=int(stat.st_size),
        mtime_epoch=float(stat.st_mtime),
        age_s=round(max(0.0, now_epoch - float(stat.st_mtime)), 3),
    )


def _pid_match(recorded_pid: int | None, pane_pid: int | None) -> bool | None:
    if recorded_pid is None or pane_pid is None:
        return None
    return recorded_pid == pane_pid


def _session_data(session: object | None) -> dict[str, Any]:
    data = getattr(session, "data", None)
    return data if isinstance(data, dict) else {}


def _path_or_none(value: object) -> Path | None:
    if value is None:
        return None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return Path(text).expanduser()
    except Exception:
        return None


def _clean_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _positive_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text.isdigit():
        return None
    pid = int(text)
    return pid if pid > 0 else None


__all__ = [
    "CodexBindingEvidence",
    "FileEvidence",
    "PidEvidence",
    "RECOVERY_HINT",
    "binding_preflight_diagnostics",
    "collect_codex_binding_evidence",
]
