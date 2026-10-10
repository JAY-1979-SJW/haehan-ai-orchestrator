"""AI 코드 품질 게이트 훅 스크립트 단위테스트.

기준서: docs/specs/2026-09-26_ai_code_quality_gate.md
대상: tools/hooks/pre_edit_dup_check.py, tools/hooks/post_edit_fast_gate.py,
      tools/hooks/stop_fast_verify.py

각 스크립트를 실제 Claude Code 훅과 동일한 방식(stdin JSON → subprocess 실행 →
exit code/stdout/stderr 확인)으로 검증한다. 실제 ruff/pytest 를 사용한다(모킹 없음) —
기준서 §8 "동작 증명"과 동일한 경로.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# post_edit_fast_gate 는 `python -m ruff` 로 새 ruff 오류를 찾는다. ruff 가 없으면 그 검사 자체가 동작하지 않아
# 시험이 실패하므로(CI 는 requirements.txt 만 설치하고 거기에 ruff 가 없다) 그때만 건너뛴다.
requires_ruff = pytest.mark.skipif(
    importlib.util.find_spec("ruff") is None,
    reason="ruff 가 설치돼 있지 않다 — post_edit_fast_gate 의 ruff 검사를 시험할 수 없다",
)
PRE_EDIT = ROOT / "tools" / "hooks" / "pre_edit_dup_check.py"
POST_EDIT = ROOT / "tools" / "hooks" / "post_edit_fast_gate.py"
STOP_VERIFY = ROOT / "tools" / "hooks" / "stop_fast_verify.py"


def _run_hook(script: Path, payload: dict, timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="ignore",
    )


# ---- pre_edit_dup_check.py ----------------------------------------------


def test_pre_edit_dup_check_no_warning_for_unique_name():
    proc = _run_hook(
        PRE_EDIT,
        {
            "tool_input": {
                "file_path": "ai_orchestrator/notify/telegram_notifier.py",
                "new_string": "def send_notification_batch_unique_xyz123(x):\n    pass\n",
            }
        },
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "" or "additionalContext" not in proc.stdout


def test_pre_edit_dup_check_warns_on_known_duplicate_name():
    # "revoke" is defined in >=2 other files under ai_orchestrator/ as of this writing.
    proc = _run_hook(
        PRE_EDIT,
        {
            "tool_input": {
                "file_path": "ai_orchestrator/notify/telegram_notifier.py",
                "new_string": "def revoke(x):\n    pass\n",
            }
        },
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "revoke" in ctx
    assert "차단" in ctx  # states it does not block


def test_pre_edit_dup_check_fails_open_on_bad_input():
    proc = subprocess.run(
        [sys.executable, str(PRE_EDIT)],
        input="not json",
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
        encoding="utf-8",
    )
    assert proc.returncode == 0


# ---- post_edit_fast_gate.py ---------------------------------------------


def _tmp_copy_of_community_router(tmp_path) -> Path:
    """community_router.py 를 임시 사본으로 — 원본(추적 파일)은 손대지 않는다.

    예전엔 원본을 직접 write_bytes 로 고쳐 쓰고 try/finally 로 복원했는데, 시험이
    타임아웃·강제종료로 중단되면 finally 가 못 돌아 원본(운영 소스)에 시험용 더미 함수
    (`_clean_noop_test_marker` 등)가 그대로 남는 결함이 있었다(실측 발견, 2026-10-10).
    사본은 post_edit_fast_gate.py 가 `file_path.resolve().relative_to(ROOT)` 로 저장소
    루트 안의 실제 경로를 요구해서(post_edit_fast_gate.py:383) pytest 기본 tmp_path(저장소
    밖)에는 못 둔다 — 같은 디렉터리(ruff 설정도 그대로 위로 찾아짐)에 따로 만든다. 중단돼도
    사본(추적 안 됨)만 남고 원본은 전혀 안 건드린다.
    """
    real = ROOT / "ai_orchestrator" / "connectors" / "community_router.py"
    copy_path = real.parent / f"_tmp_test_copy_{tmp_path.name}_community_router.py"
    copy_path.write_bytes(real.read_bytes())
    return copy_path


@requires_ruff
def test_post_edit_fast_gate_blocks_new_ruff_error(tmp_path):
    target = _tmp_copy_of_community_router(tmp_path)
    try:
        # 바이트로 다룬다 — read_text/write_text 는 윈도우에서 줄바꿈(CRLF/LF)을 바꿀 수 있다
        target.write_bytes(
            target.read_bytes()
            + b"\n\ndef _unused_var_demo_test_marker():\n    unused_local_var = 123\n    return True\n"
        )
        proc = _run_hook(
            POST_EDIT,
            {
                "tool_input": {"file_path": str(target)},
            },
            timeout=30,
        )
        assert proc.returncode == 2
        assert "F841" in proc.stderr or "unused" in proc.stderr.lower()
    finally:
        target.unlink(missing_ok=True)


def test_post_edit_fast_gate_passes_clean_edit(tmp_path):
    target = _tmp_copy_of_community_router(tmp_path)
    try:
        target.write_bytes(target.read_bytes() + b"\n\ndef _clean_noop_test_marker():\n    return True\n")
        proc = _run_hook(
            POST_EDIT,
            {
                "tool_input": {"file_path": str(target)},
            },
            timeout=30,
        )
        # ruff must not flag this addition as a new error (exit 2 would only be
        # legitimate here if a mapped test genuinely fails, which is covered
        # separately). We only assert ruff-level cleanliness by checking stderr
        # does not mention a rule code for our added function.
        assert "_clean_noop_test_marker" not in proc.stderr
    finally:
        target.unlink(missing_ok=True)


def test_post_edit_fast_gate_skips_missing_file():
    proc = _run_hook(
        POST_EDIT,
        {
            "tool_input": {"file_path": str(ROOT / "does_not_exist_xyz.py")},
        },
    )
    assert proc.returncode == 0


def test_post_edit_fast_gate_fails_open_on_bad_input():
    proc = subprocess.run(
        [sys.executable, str(POST_EDIT)],
        input="not json",
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
        encoding="utf-8",
    )
    assert proc.returncode == 0


# ---- stop_fast_verify.py -------------------------------------------------


def test_stop_fast_verify_passes_immediately_when_stop_hook_active():
    proc = _run_hook(STOP_VERIFY, {"stop_hook_active": True}, timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_stop_fast_verify_passes_when_no_session_record(tmp_path, monkeypatch):
    """세션 편집 기록이 없으면(다른 세션의 미커밋 변경과 무관하게) 즉시 통과해야 한다."""
    session_id = "test-session-no-records-xyz"
    session_dir = ROOT / "data" / ".session_edits"
    record_path = session_dir / f"{session_id}.json"
    assert not record_path.exists()
    proc = _run_hook(STOP_VERIFY, {"stop_hook_active": False, "session_id": session_id}, timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_stop_fast_verify_only_checks_this_sessions_files():
    """post_edit_fast_gate 가 기록한 세션별 목록만 stop_fast_verify 가 검사하고,
    다른(가짜) 세션 id 로는 그 파일이 보이지 않아야 한다 — 다른 세션의 미커밋
    변경분이 이 세션의 Stop 게이트를 막지 않는다는 것을 확인."""
    session_id = "test-session-isolated-abc"
    other_session_id = "test-session-other-def"
    session_dir = ROOT / "data" / ".session_edits"
    record_path = session_dir / f"{session_id}.json"
    other_record_path = session_dir / f"{other_session_id}.json"

    target = ROOT / "ai_orchestrator" / "connectors" / "community_router.py"
    original = target.read_bytes()
    try:
        # 세션 A 가 이 파일을 편집했다고 기록만 남긴다(실제 ruff 신규 오류는 넣지 않음 —
        # 통과 경로에서 격리 여부만 확인).
        _run_hook(
            POST_EDIT,
            {
                "tool_input": {"file_path": str(target)},
                "session_id": session_id,
            },
            timeout=30,
        )
        assert record_path.exists()

        # 세션 B(다른 세션 id)로 Stop 을 실행하면 세션 A의 기록이 보이면 안 된다.
        assert not other_record_path.exists()
        proc = _run_hook(STOP_VERIFY, {"stop_hook_active": False, "session_id": other_session_id}, timeout=10)
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""
    finally:
        target.write_bytes(original)
        for p in (record_path, other_record_path):
            if p.exists():
                p.unlink()


def test_stop_fast_verify_fails_open_on_bad_input():
    # No stop_hook_active in payload (json.load fails -> payload={}) means the
    # script proceeds to scan changed files, which can take up to its own
    # 30s internal budget, so allow more wall-clock time here.
    proc = subprocess.run(
        [sys.executable, str(STOP_VERIFY)],
        input="not json",
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=40,
        encoding="utf-8",
    )
    assert proc.returncode == 0
