"""셀렉터 헬스체크 주간 래퍼 테스트 (schtasks 실제 호출 없이 검증)."""

from __future__ import annotations

from pathlib import Path

from tools import selector_health_weekly as W

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_paths_inside_repo():
    """로그·대상 스크립트가 저장소 안이어야 한다(repo boundary)."""
    assert W.ROOT == REPO_ROOT
    assert W.LOG_FILE.is_relative_to(REPO_ROOT)
    assert W.CHECKER.exists(), "헬스체크 스크립트 경로가 틀림"
    assert W.CDP_STARTER.exists(), "CDP 기동 스크립트 경로가 틀림"


def test_task_name_is_namespaced():
    """다른 작업과 충돌하지 않도록 프로젝트 접두사를 쓴다."""
    assert W.TASK_NAME.startswith("Haehan")


def test_run_schtasks_decodes_cp949(monkeypatch):
    """schtasks 가 CP949 로 출력해도 죽지 않아야 한다(2026-08-15 실제 사고)."""
    import subprocess

    class FakeProc:
        returncode = 0
        stdout = "예약된 작업을 만들었습니다.".encode("cp949")
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc())
    code, msg = W._run_schtasks(["schtasks", "/query"])
    assert code == 0
    assert "예약된 작업" in msg


def test_run_schtasks_survives_undecodable_bytes(monkeypatch):
    """어떤 인코딩으로도 못 읽는 바이트가 와도 예외로 죽지 않는다."""
    import subprocess

    class FakeProc:
        returncode = 1
        stdout = b"\xff\xfe\x00\x81\x82"
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc())
    code, msg = W._run_schtasks(["schtasks"])
    assert code == 1
    assert isinstance(msg, str)


def test_run_check_aborts_when_cdp_down(monkeypatch, tmp_path):
    """CDP 가 안 뜨면 헬스체크를 돌리지 않고 exit 2 + 로그를 남긴다."""
    monkeypatch.setattr(W, "ensure_cdp", lambda: False)
    monkeypatch.setattr(W, "LOG_DIR", tmp_path)
    monkeypatch.setattr(W, "LOG_FILE", tmp_path / "log.jsonl")

    assert W.run_check() == 2
    content = (tmp_path / "log.jsonl").read_text(encoding="utf-8")
    assert "cdp_down" in content


def test_run_check_logs_drift(monkeypatch, tmp_path):
    """드리프트(exit 1) 가 로그에 drift_detected 로 기록돼야 한다."""
    import subprocess

    monkeypatch.setattr(W, "ensure_cdp", lambda: True)
    monkeypatch.setattr(W, "LOG_DIR", tmp_path)
    monkeypatch.setattr(W, "LOG_FILE", tmp_path / "log.jsonl")

    class FakeProc:
        returncode = 1
        stdout = "  ⚠ 조치 필요:\n    - TAG_INPUT: DOM 에 없음\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc())
    assert W.run_check() == 1
    content = (tmp_path / "log.jsonl").read_text(encoding="utf-8")
    assert "drift_detected" in content
    assert "TAG_INPUT" in content
