"""훅 스크립트는 stdout/stderr 를 UTF-8 로 고정해야 한다 (2026-10-01).

하네스는 훅 출력을 UTF-8 로 읽는다. 파이프로 연결되면 파이썬 기본 인코딩이 cp949 라, 고정하지 않으면
한글이 깨져 사용자가 안내 문구(예: 세션 한도 도달 시 `/clear` 안내)를 읽지 못한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# 평문(한글) 출력을 내는 훅 스크립트. JSON 으로만 출력하는 가드(ensure_ascii)는 대상이 아니다.
PLAIN_TEXT_HOOKS = (
    "tools/hooks/session_guard.py",
    "tools/hooks/post_edit_fast_gate.py",
    "tools/hooks/stop_fast_verify.py",
    "tools/hooks/prewrite_capability_check.py",
    "tools/hooks/pre_edit_dup_check.py",
    "tools/hooks/behavior_gate.py",
)


def _calls_reconfigure_utf8(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "reconfigure"
            and any(
                kw.arg == "encoding" and isinstance(kw.value, ast.Constant) and kw.value.value == "utf-8"
                for kw in node.keywords
            )
        ):
            return True
    return False


@pytest.mark.parametrize("rel", PLAIN_TEXT_HOOKS)
def test_plain_text_hook_forces_utf8_stdio(rel):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    assert _calls_reconfigure_utf8(tree), f"{rel}: 훅 출력 인코딩을 UTF-8 로 고정하지 않으면 한글이 깨진다"
