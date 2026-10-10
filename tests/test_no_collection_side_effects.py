"""tests/**/test_*.py 의 모듈 최상단에 pytest 수집(import) 시점에 실행되는 부작용이 없는지.

재발 방지 — run38015451820: tests/integration/manual/test_wait_login.py 가 `if __name__ ==
"__main__":` 가드 없이 최상단에 `sys.exit(_main())` 를 둬서, pytest 가 그 파일을 import 하는
순간(수집 단계, 실제 실행 아님) sys.exit 가 그대로 실행돼 xdist 워커가 죽었다(INTERNALERROR,
결정론적 재현). 전수조사(W1, 2026-10-10)로 같은 종류 2건(test_browser_state.py — 수집시 실제
CDP 브라우저 세션을 열었음, test_popup_modules.py — 수집시 실제 DB 에 썼음) 추가 발견, 전부
`if __name__ == "__main__":` 가드로 수정(288320dc 등) — 이 시험은 그 재발을 막는다.

허용하는 모듈 최상단 문: import·def/class·docstring(문자열 리터럴만 있는 Expr)·
`if __name__ == "__main__":` 가드·`if TYPE_CHECKING:` 가드·대입문(우변이 함수 호출이
아니면 전부 허용 — 리터럴·연산·비교 등). 대입문·단독 표현식의 우변이 함수 호출이면
`_ALLOWED_TOP_LEVEL_CALLS` 허용목록(결정론적·순수 — 네트워크·브라우저·DB·sleep·sys.exit
등 부작용이 없다고 이미 확인된 호출)에 있어야 하고, 없으면 FAIL(새 호출은 함수 안으로
옮기거나 이 파일의 허용목록에 사유와 함께 추가). `while True:` 같은 무한루프는 최상단에서
항상 FAIL.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 결정론적·순수(네트워크·브라우저·DB·파일쓰기·sleep·프로세스 종료 등 부작용 없음) — 이미 저장소
# 전체를 조사해 확인된 호출만 올린다(2026-10-10). 새 호출이 필요하면 여기 사유를 적어 추가하거나,
# 부작용이 있을 수 있으면 함수/`if __name__` 가드 안으로 옮긴다.
_ALLOWED_TOP_LEVEL_CALLS = {
    # sys.path 부트스트랩 — G5, 이 저장소 전체의 표준 패턴(수백 곳)
    "sys.path.insert",
    "sys.path.append",
    # 순수 문자열/경로/시간 계산
    "Path",
    "pathlib.Path",
    "re.compile",
    "json.loads",
    "json.dumps",
    "datetime",
    "date",
    "timezone",
    "astimezone",
    "textwrap.dedent",
    # 환경변수 읽기/설정(테스트 격리 목적, 네트워크·프로세스 부작용 없음)
    "os.environ.setdefault",
    "os.environ.pop",
    "os.environ.get",
    "os.getenv",
    "warnings.filterwarnings",
    # 로컬 저장소 파일을 읽기만 하는 결정론적 헬퍼(네트워크·쓰기 없음)
    "importlib.util.spec_from_file_location",
    "importlib.util.module_from_spec",
    "importlib.reload",
    "ast.parse",
    "shutil.which",
    "tempfile.gettempdir",
    "repo_root",
    "gate.load_config",
    "find_shims",
    "assistant_route",
    "p.merged_settings",
    # 순수 빌트인 타입 생성자/함수(부작용 없음)
    "str",
    "int",
    "list",
    "tuple",
    "set",
    "frozenset",
    "dict",
    "bytes",
    "bytes.fromhex",
    "chr",
    "next",
    # FastAPI TestClient — 실제 네트워크 없이 인메모리로만 ASGI 앱을 감싼다
    "TestClient",
    # Scope 값객체 생성자(순수, ai_orchestrator.site_work.work_record_store)
    "Scope.owner_only",
    "Scope.tenant_wide",
}

# 어떤 객체에 붙든(소유자가 Name 이 아니어도) 그 자체로 부작용 없는 메서드 — 예:
# `Path("x").read_text()`(owner 가 Path(...) 호출 결과라 dotted 이름을 못 만듦) · 체이닝된
# `"...".replace(...).replace(...)` · `_spec.loader.exec_module(mod)`(로컬 저장소 소스를
# 메모리에 올리는 표준 동적 로드 패턴, test_shim_contract.py 등에서 이미 쓰는 이디엄).
_ALLOWED_TRAILING_METHODS = {
    "read_text",
    "decode",
    "replace",
    "exec_module",
}

# 이름이 무엇이든 그 자체로 위험해서 허용목록에 올려도 항상 막는다(가장 먼저 확인).
_ALWAYS_DANGEROUS = {
    ("sys", "exit"),
    ("os", "_exit"),
    ("os", "abort"),
    ("time", "sleep"),
}
_DANGEROUS_MODULE_PREFIXES = ("requests", "urllib", "httpx", "socket", "playwright", "selenium", "webdriver")


def _dotted_call_name(call: ast.Call) -> tuple[str | None, str | None, str]:
    """(소유자, 메서드이름, 전체 dotted 이름) — Name 호출이면 소유자는 None."""
    func = call.func
    if isinstance(func, ast.Name):
        return None, func.id, func.id
    if isinstance(func, ast.Attribute):
        parts = [func.attr]
        cur = func.value
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        owner = cur.id if isinstance(cur, ast.Name) else None
        if owner:
            parts.append(owner)
        return owner, func.attr, ".".join(reversed(parts))
    return None, None, "<복잡한 호출식>"


def _is_main_or_type_checking_guard(node: ast.If) -> bool:
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id in ("__name__", "TYPE_CHECKING")
    ) or (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")


def _violations_in(tree: ast.Module) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in tree.body:
        if isinstance(
            node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Pass)
        ):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue  # docstring
        if isinstance(node, ast.If) and _is_main_or_type_checking_guard(node):
            continue
        if isinstance(node, ast.While):
            out.append((node.lineno, "top-level while 루프(무한루프 가능성) — 함수 안으로 옮기세요"))
            continue

        rhs = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            # pytestmark = pytest.mark.skip(...) / pytest.importorskip(...) — pytest 자체의
            # 수집단계 제어 이디엄은 항상 허용.
            if isinstance(node.value, ast.Call):
                owner, attr, dotted = _dotted_call_name(node.value)
                if dotted.startswith("pytest."):
                    continue
            rhs = node.value
        elif isinstance(node, ast.AnnAssign):
            rhs = node.value
        elif isinstance(node, ast.Expr):
            rhs = node.value

        if rhs is None or not isinstance(rhs, ast.Call):
            continue  # 호출이 아니면(리터럴·연산 등) 부작용 없음으로 간주

        owner, attr, dotted = _dotted_call_name(rhs)
        if (owner, attr) in _ALWAYS_DANGEROUS:
            out.append((node.lineno, f"top-level {dotted}() — 수집시 프로세스를 끝내거나 멈출 수 있음"))
            continue
        if owner and owner.split(".")[0] in _DANGEROUS_MODULE_PREFIXES:
            out.append((node.lineno, f"top-level {dotted}() — 네트워크/브라우저 호출로 보임"))
            continue
        if dotted.startswith("pytest."):
            continue
        if attr in _ALLOWED_TRAILING_METHODS:
            continue
        if dotted not in _ALLOWED_TOP_LEVEL_CALLS:
            out.append(
                (
                    node.lineno,
                    f"top-level {dotted}() — 허용목록에 없음(부작용 없음을 확인해 추가하거나 함수/`if __name__` 안으로 옮기세요)",
                )
            )
    return out


def test_no_module_level_side_effects_in_test_files():
    violations: list[str] = []
    for path in sorted(ROOT.glob("tests/**/test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            violations.append(f"{path.relative_to(ROOT).as_posix()}: 파싱 실패({exc})")
            continue
        for lineno, msg in _violations_in(tree):
            violations.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}: {msg}")
    assert not violations, "pytest 수집시 실행되는 최상단 부작용 발견:\n" + "\n".join(violations)
