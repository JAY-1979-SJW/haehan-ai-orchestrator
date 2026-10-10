"""mypy B3: 권한/정책 판정 None 입력 fail-closed 가드 시험 (H2-4, H1-6).

browser_policy_integration 은 browser 계열이라 import/실행하지 않고 ast 로 구조만 확인한다.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from core.agent_runtime.runtime.permission import delegated_permission_store as store
from core.agent_runtime.runtime.permission.delegated_permission_policy import (
    CHECK_ALLOWED,
    CHECK_PERMISSION_REQUIRED,
    check_permission,
)

_ROOT = Path(__file__).resolve().parent.parent
_BPI = _ROOT / "core" / "agent_runtime" / "runtime" / "site_profile" / "browser_policy_integration.py"


def setup_function() -> None:
    store.clear_all()


def test_check_permission_none_is_denied() -> None:
    r = check_permission(None, "blog_publish", "blog.naver.com")
    assert r["result"] == CHECK_PERMISSION_REQUIRED


def test_use_permission_unknown_id_denied_and_no_permission() -> None:
    r = store.use_permission("no-such-id", "blog_publish", "blog.naver.com")
    assert r["result"] == CHECK_PERMISSION_REQUIRED
    assert r["permission"] is None


def test_use_permission_none_id_denied() -> None:
    bad_id: Any = None
    r = store.use_permission(bad_id, "blog_publish", "blog.naver.com")
    assert r["result"] == CHECK_PERMISSION_REQUIRED
    assert r["permission"] is None


def test_use_permission_allowed_path_unchanged() -> None:
    perm = store.grant_permission("blog_publish", "blog.naver.com", max_executions=2)
    before = perm["execution_count"]
    r = store.use_permission(perm["permission_id"], "blog_publish", "blog.naver.com")
    assert r["result"] == CHECK_ALLOWED
    assert r["permission"] is perm
    assert perm["execution_count"] == before + 1


def test_use_permission_signature_guard_present() -> None:
    src = Path(store.__file__).read_text(encoding="utf-8")
    assert "perm is not None" in src


def test_browser_policy_site_id_none_guard_blocks() -> None:
    tree = ast.parse(_BPI.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "open_with_policy")
    # `site_id = url_check["site_id"]` 직후에 site_id 부재 시 BLOCKED 반환 가드가 있어야 한다.
    found = False
    for n in ast.walk(fn):
        if isinstance(n, ast.If) and ast.unparse(n.test) == "not site_id":
            body = ast.unparse(n)
            if "BLOCKED" in body and "return" in body and "get_site" not in body:
                found = True
    assert found
