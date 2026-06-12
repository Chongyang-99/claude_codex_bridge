from __future__ import annotations

from pathlib import Path

import pytest

from provider_backends.codex.comm_runtime import check_tmux_runtime_health
from provider_backends.codex.binding_evidence import collect_codex_binding_evidence


def test_check_tmux_runtime_health_reports_missing_bridge_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "codex.pid").write_text("123", encoding="utf-8")
    input_fifo = runtime_dir / "input.fifo"
    input_fifo.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "provider_backends.codex.comm_runtime.session_runtime_runtime.health._probe_pid",
        lambda pid, *, label: (True, f"{label} ok"),
    )

    healthy, status = check_tmux_runtime_health(runtime_dir=runtime_dir, input_fifo=input_fifo)

    assert healthy is False
    assert status == "Bridge process PID file not found"


def test_check_tmux_runtime_health_reports_invalid_codex_pid(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "codex.pid").write_text("bad-pid", encoding="utf-8")
    input_fifo = runtime_dir / "input.fifo"
    input_fifo.write_text("", encoding="utf-8")

    healthy, status = check_tmux_runtime_health(runtime_dir=runtime_dir, input_fifo=input_fifo)

    assert healthy is False
    assert status == "Failed to read Codex process PID"


def test_codex_binding_evidence_reports_dead_pid_with_alive_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "codex.pid").write_text("123\n", encoding="utf-8")
    (runtime_dir / "bridge.pid").write_text("456\n", encoding="utf-8")
    input_fifo = runtime_dir / "input.fifo"
    input_fifo.write_text("", encoding="utf-8")

    class Backend:
        def is_alive(self, pane_id: str) -> bool:
            return pane_id == "%1"

        def pane_pid(self, pane_id: str) -> int:
            assert pane_id == "%1"
            return 789

    monkeypatch.setattr(
        "provider_backends.codex.binding_evidence._pid_alive",
        lambda pid: pid == 456,
    )

    evidence = collect_codex_binding_evidence(
        backend=Backend(),
        pane_id="%1",
        runtime_dir=runtime_dir,
        input_fifo=input_fifo,
        managed_runtime_expected=True,
        now_epoch=1000.0,
    )
    record = evidence.to_record()

    assert evidence.preflight_failed is True
    assert evidence.binding_state == "unhealthy"
    assert "codex_pid_dead" in evidence.unhealthy_reasons
    assert "codex_pid_pane_pid_mismatch" in evidence.unhealthy_reasons
    assert record["pane_alive"] is True
    assert record["codex_pid"]["alive"] is False
    assert record["bridge_pid"]["alive"] is True
    assert record["tmux_pane_pid"] == 789
