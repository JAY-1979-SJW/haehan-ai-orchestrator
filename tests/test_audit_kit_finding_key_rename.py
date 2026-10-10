"""finding_key()/excess_findings() — 이동(rename)된 파일의 기존 문제를 "새 문제"로 오탐하지 않아야 한다.

배경(2026-10-10): finding_key() 가 줄 번호만 지우고 경로는 남겨서, 파일이 옛 경로에서 새 경로로 이동하면
메시지 속 경로 문자열이 달라져 기준/변경 비교가 어긋나 "새 문제 104건"으로 오판됐다(tools/hooks/audit_kit_gate.py
의 _hook_finding_key() 는 2026-10-08 에 이미 경로:줄번호를 통째로 지우도록 고쳤는데 이쪽엔 누락되어 있었음).
이 시험은 그 오탐 재발을 막는다: (가) 이동만 → 새 문제 0, (나) 이동 + 진짜 새 위반 1건 추가 → 새 문제 1.

이름 주의: `excess_findings(head, base)`(이 모듈, PostToolUse hook 출력 줄 한 묶음에서 이번 편집이 만든 항목만
거르는 기존 `new_findings(stderr_text)`(90행)와 이름이 같아서 1b2fb0a1 이 그걸 덮어써 CI verify-static 이
깨졌었다 — 재발 방지로 이름을 분리했다(2026-10-10 15:00).
"""

from __future__ import annotations

from tools.hooks.audit_kit_gate import excess_findings, finding_key


def test_finding_key_strips_path_and_line_so_renamed_file_keys_match():
    old = "[표준 EFF-02] tests/test_foo.py:659 절대경로 하드코딩"
    new = "[표준 EFF-02] tests/app_contracts/test_foo.py:12 절대경로 하드코딩"
    assert finding_key(old) == finding_key(new) == "[표준 EFF-02] 절대경로 하드코딩"


def test_rename_only_yields_zero_new_findings():
    """(가) git mv 만 한 파일: 기준 트리의 옛 경로 문제가 변경 트리의 새 경로에 그대로 있을 뿐 — 새 문제 0건."""
    base = ["[표준 EFF-02] tests/test_foo.py:659 절대경로 하드코딩"]
    head = ["[표준 EFF-02] tests/app_contracts/test_foo.py:12 절대경로 하드코딩"]
    assert excess_findings(head, base) == []


def test_rename_plus_one_real_new_violation_yields_exactly_one_new_finding():
    """(나) 이동 + 진짜 새 위반 1줄 추가: 기존 문제는 여전히 0건, 새로 추가된 줄만 1건 잡혀야 한다."""
    base = ["[표준 EFF-02] tests/test_foo.py:659 절대경로 하드코딩"]
    head = [
        "[표준 EFF-02] tests/app_contracts/test_foo.py:12 절대경로 하드코딩",
        "[표준 STD-02] tests/app_contracts/test_foo.py:40 새로 추가된 하드코딩",
    ]
    out = excess_findings(head, base)
    assert len(out) == 1
    assert out[0] == "[표준 STD-02] tests/app_contracts/test_foo.py:40 새로 추가된 하드코딩"


def test_duplicate_same_message_two_lines_counts_only_the_excess_as_new():
    """Counter 비교: 같은 메시지가 기준 1건, 변경본 2건이면 1건만 새 문제로 잡혀야 한다(set 비교였으면 0건으로 놓쳤을 함정)."""
    base = ["[표준 EFF-02] a.py:1 절대경로 하드코딩"]
    head = [
        "[표준 EFF-02] a.py:1 절대경로 하드코딩",
        "[표준 EFF-02] a.py:99 절대경로 하드코딩",
    ]
    out = excess_findings(head, base)
    assert len(out) == 1
