"""시험 코드가 `importlib.reload(tools.gates.auth)` 를 쓰지 않는지 고정한다.

이유는 `tests/conftest.py` 의 `apply_basic_auth_users` 문서 참고 — reload 가 `get_current_user` 를
새 객체로 만들어 이미 import 된 라우터의 `dependency_overrides` 를 무력화하고, `register_bearer_resolver`
로 등록된 Bearer 검증기를 `None` 으로 되돌려 이후 세션의 다른 시험까지 401 로 깨뜨린다(2026-10-08 B11
이동 중 발견·수정). AUTH_ENABLED·HTTP_USERS_PATH 토글은 `apply_basic_auth_users` 로 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_AUTH_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(?:ai_orchestrator|tools)\.gates\s+import\s+auth(?:\s+as\s+(\w+))?"
    r"|import\s+(?:ai_orchestrator|tools)\.gates\.auth(?:\s+as\s+(\w+))?)",
    re.MULTILINE,
)
_RELOAD_RE = re.compile(r"importlib\.reload\(\s*(\w+)\s*\)")

# B9(local_agent, W4 의 local_agent/browser_tool 이동과 합쳐서 나중에 처리)로 미뤄 둔 기존 부채.
# 새로 늘리지 않는다 — B9 에서 함께 고친다.
_BASELINE = {"ai_orchestrator/tests/test_local_agent.py"}


def _bound_names(text: str) -> set[str]:
    # gates_root_1 이동(3869fe5f) 이후 실제 경로는 tools.gates.auth — ai_orchestrator.gates.auth
    # 는 더 이상 실체가 없다(2026-10-10, 가드가 새 경로를 못 잡던 결함 수정).
    names = {"tools.gates.auth", "ai_orchestrator.gates.auth", "auth"}
    for m in _AUTH_IMPORT_RE.finditer(text):
        alias = m.group(1) or m.group(2)
        if alias:
            names.add(alias)
    return names


def test_no_reload_of_gates_auth_module():
    bad: list[str] = []
    for f in ROOT.glob("**/test_*.py"):
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        if "__pycache__" in rel:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        if "ai_orchestrator.gates" not in text and "gates import auth" not in text and "gates.auth" not in text:
            continue
        if rel in _BASELINE:
            continue
        bound = _bound_names(text)
        for m in _RELOAD_RE.finditer(text):
            if m.group(1) in bound:
                bad.append(f"{rel}: importlib.reload({m.group(1)})")
    assert not bad, (
        "시험 코드에 새로 생긴 importlib.reload(tools.gates.auth) 가 있으면 안 됩니다"
        "(tests/conftest.py 의 apply_basic_auth_users 를 쓰세요, 기존 부채는 _BASELINE 에 고정):\n" + "\n".join(bad)
    )


def test_baseline_entries_still_exist_and_still_reload():
    """_BASELINE 항목이 이미 지워졌거나 reload 를 안 쓰게 됐으면 목록에서 빼서 범위를 줄인다."""
    stale = []
    for rel in sorted(_BASELINE):
        f = ROOT / rel
        if not f.exists():
            stale.append(f"{rel}: 파일 없음(목록에서 제거)")
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        bound = _bound_names(text)
        if not any(m.group(1) in bound for m in _RELOAD_RE.finditer(text)):
            stale.append(f"{rel}: 더는 reload 안 함(목록에서 제거)")
    assert not stale, "\n".join(stale)
