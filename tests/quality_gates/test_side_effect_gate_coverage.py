"""R2 커버리지 — 외부 발행·발송을 하는 함수가 공통 장치(scripts.common.gate)를 거치는지 정적 검사한다.

발행·발송 호출(sink)을 가진 함수가 게이트 호출(`require_side_effect` / `gate_check` / `check_send` / `@gated`)을
하지 않으면 '미적용 경로'다. 기존 미적용 경로는 tests/data/side_effect_gate_baseline.json 에 고정해 두고,
**새로운 미적용 경로가 생기면 실패**한다. 기존 경로에 게이트를 달면 기준선에서 빼도 된다(안 빼도 실패하지 않고 알려 준다).
기준선 재생성: REGEN_SIDE_EFFECT_BASELINE=1 py -3.14 -m pytest tests/quality_gates/test_side_effect_gate_coverage.py
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tests" / "data" / "side_effect_gate_baseline.json"

SCAN_DIRS = ("scripts", "ai_orchestrator", "browser_api", "orchestrator_v1")
SKIP_PARTS = {"__pycache__", "node_modules", ".venv", "archive", "ops", "tests"}  # scripts/ops 는 점검 스크립트
# 발행·발송 sink 함수 목록 — `.publish()` 같은 호출명 패턴이 아니라 실제 외부 효과를 내는 함수를 명시한다.
# (BlogWriter.write_post 호출은 호출명 패턴에 안 걸려 발행 경로가 처음부터 안 잡혔다 — W2 가 찾은 사각지대)
SINK_CALLS = {  # 이름이 곧 외부 발송·게시·공유
    "write_post",  # BlogWriter/카페 글 작성(+즉시 발행). 예약 실행의 write_post(require_approval=False) 도 여기에 걸린다
    "edit_post",  # 발행된 글 수정
    "confirm_publish",  # 승인 대기 중인 글 발행
    "send_mail",
    "sendmail",
    "send_draft",
    "media_publish",
    "send_reply",
    "send_fax",
    "send_private_reply",
    "share_link",
    "submit_reply",
}
SINK_STRINGS = ("media_publish", "Send ⌘Enter", "공유하기")  # Graph API 경로·Gmail 보내기 버튼 셀렉터 문자열
PUBLISH_RECEIVERS = ("bw", "writer")  # bw.publish() / self.writer.publish() — BlogWriter 계열 발행 호출
# gates.check_send(force=True) 는 항상 통과시킬 수 있어 게이트로 인정하지 않는다(R2b). require_send 는 승인 문구를 대조한다.
GUARDS = {
    "require_side_effect",
    "require_send",
    "require_send_approval",
    "_require_send_approval",
    "require_approved",
    "gate_check",
    "gated",
    "check_send",
    # 인스타 DM 웹훅은 자동 실행이라 승인 문구를 받을 수 없다 — 수신거부 대조만 한다(정책: 환경 플래그 기본 꺼짐).
    "is_opted_out",
}
WEAK_GUARD_RECEIVERS = {"gates"}  # gates.check_send(force=...) 는 불리언으로 통과 가능 — policy.check_send 같은 별도 정책만 인정
# 정의 자체가 발송 구현이라 호출이 아닌 것(예: smtplib 래퍼 정의)은 SINK 호출이 없으므로 자동 제외된다.
REQUIRED_GUARDED = {
    "ai_orchestrator/connectors/naver_blog/naver_blog_router.py::write_to_naver._do",  # 게이트는 바깥 write_to_naver 에 있다
    "ai_orchestrator/marketing/marketing_ops_router.py::publish_blog._do",  # 게이트는 바깥 publish_blog 에 있다
    "scripts/hiworks/mail_batch.py::execute_send_batch",
    "ai_orchestrator/connectors/google/gmail_router.py::api_reply",
    "ai_orchestrator/connectors/google/gmail_router.py::api_send",
    "ai_orchestrator/connectors/eum/router.py::send_one._compose_and_send",
    "ai_orchestrator/connectors/hiworks/mail_router.py::api_send",
    "scripts/eum/send_mail_batch.py::send_one",
    "scripts/naver/blog/core/ai_writer.py::BlogAIWriter.draft_and_save",
    "scripts/naver/blog/core/writer_pro.py::BlogWriterPro._publish_by_mode",
    "scripts/naver/blog/management/schedule.py::BlogSchedule.process_due",
    "scripts/naver/blog/marketing/publish.py::publish_one",  # write_post 호출(사각지대였던 sink)
    "scripts/instagram/publish.py::publish_case",
    "scripts/hanafax/router.py::_cmd_send",
    "ai_orchestrator/connectors/instagram/instagram_dm_service.py::process_comment_event",
}


def _py_files() -> list[Path]:
    files = [p for p in ROOT.glob("*.py")]
    for d in SCAN_DIRS:
        files += [p for p in (ROOT / d).rglob("*.py") if not SKIP_PARTS & set(p.relative_to(ROOT).parts)]
    return sorted(files)


def _call_name(node: ast.Call) -> tuple[str | None, bool]:
    """(호출 이름, 속성 호출 여부)"""
    f = node.func
    if isinstance(f, ast.Name):
        return f.id, False
    if isinstance(f, ast.Attribute):
        return f.attr, True
    return None, False


def _is_sink(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return any(t in node.value for t in SINK_STRINGS)
    if not isinstance(node, ast.Call):
        return False
    name, is_attr = _call_name(node)
    if name in SINK_CALLS:
        return True
    if name == "publish" and is_attr and ast.unparse(node.func.value).endswith(PUBLISH_RECEIVERS):  # type: ignore[attr-defined]
        return True
    # YouTube Data API: youtube.videos().insert(...)
    return name == "insert" and is_attr and "videos" in ast.dump(node.func)


def _is_guard(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        name, is_attr = _call_name(node)
        if name == "check_send" and is_attr and ast.unparse(node.func.value) in WEAK_GUARD_RECEIVERS:  # type: ignore[attr-defined]
            return False
        return name in GUARDS
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return any(
            (isinstance(d, ast.Call) and _call_name(d)[0] in GUARDS) or (isinstance(d, ast.Name) and d.id in GUARDS)
            for d in node.decorator_list
        )
    return False


def scan() -> tuple[set[str], set[str]]:
    """(싱크를 가진 함수 전체, 그중 게이트 없는 함수) — 키는 'relpath::qualname'."""
    sinks: set[str] = set()
    unguarded: set[str] = set()

    def visit(node: ast.AST, rel: str, scope: list[str], outer_guarded: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                key = f"{rel}::{'.'.join([*scope, child.name])}"
                own = list(_walk_own(child))
                guarded = outer_guarded or _is_guard(child) or any(_is_guard(n) for n in own)
                if any(_is_sink(n) for n in own):
                    sinks.add(key)
                    if not guarded:
                        unguarded.add(key)
                visit(child, rel, [*scope, child.name], guarded)  # 중첩 함수는 바깥 함수의 게이트를 상속한다
            elif isinstance(child, ast.ClassDef):
                visit(child, rel, [*scope, child.name], outer_guarded)
            else:
                visit(child, rel, scope, outer_guarded)

    for path in _py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        visit(tree, path.relative_to(ROOT).as_posix(), [], False)
    return sinks, unguarded


def _walk_own(fn: ast.AST):
    """중첩 def 본문은 제외하고 함수 자신의 노드를 훑는다. lambda 는 함수 자신의 일부로 본다."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
            stack.extend(ast.iter_child_nodes(n))


def test_no_new_unguarded_publish_or_send_paths():
    _sinks, unguarded = scan()
    if os.environ.get("REGEN_SIDE_EFFECT_BASELINE") == "1":
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(sorted(unguarded), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    baseline = set(json.loads(BASELINE.read_text(encoding="utf-8")))
    new = sorted(unguarded - baseline)
    assert not new, (
        "공통 장치(scripts.common.gate.require_side_effect)를 거치지 않는 새 발행·발송 경로:\n  "
        + "\n  ".join(new)
        + "\n→ 함수 안쪽에서 require_side_effect 를 호출하거나, 불가피하면 기준선에 사유와 함께 추가하세요."
    )


def test_wired_paths_stay_guarded():
    sinks, unguarded = scan()
    assert REQUIRED_GUARDED <= sinks, f"스캐너가 연결된 경로를 못 찾음: {sorted(REQUIRED_GUARDED - sinks)}"
    assert not (REQUIRED_GUARDED & unguarded), f"게이트가 빠진 연결 경로: {sorted(REQUIRED_GUARDED & unguarded)}"
    assert not (REQUIRED_GUARDED & set(json.loads(BASELINE.read_text(encoding="utf-8"))))


def test_stale_baseline_entries_are_reported_not_failed():
    """기준선에 있지만 이제 게이트가 있거나 없어진 항목 — 정리 대상일 뿐 실패시키지 않는다."""
    _sinks, unguarded = scan()
    stale = sorted(set(json.loads(BASELINE.read_text(encoding="utf-8"))) - unguarded)
    if stale:
        print("기준선에서 뺄 수 있는 항목:", stale)
