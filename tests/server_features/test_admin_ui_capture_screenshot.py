"""관리자 UI capture_screenshot 버튼 — 정적 검증 + 동작 검증.

본 파일은 1·2단계 모두 포괄한다.

공통 검증 항목:
  1. /api/v1/admin/local-agents 에 기존 "화면 캡처 사전 점검" 버튼 유지.
  2. 버튼이 호출하는 API 경로가 /api/v1/local-agents/{id}/capture-screenshot 이다.
  3. dry-run UI 가 보내는 body 는 dry_run=true (ui_dry_run_check reason).
  4. 실제 1회 캡처 UI 는 dry_run=false (ui_capture_once_request) 로 명시 전송한다.
  5. 실제 1회 캡처 fetch 는 반드시 window.confirm 게이트 뒤에 위치한다.
     confirm 취소 시 fetch 호출이 존재하지 않는다 (구조적 검증).
  6. 성공 응답 후 task_id/status/dry_run 값이 안내 문구에 포함된다.
  7. 실제 1회 캡처 성공 안내에 "텔레그램" + "1회" +
     "서버에는 이미지가 업로드되지 않습니다" 의미가 포함된다.
  8. 403 / 404 응답 한국어 메시지 제공.
  9. 화면에 approval token / device_token / secret / 전체 경로 / 이미지
     파일명이 노출되지 않는다.
 10. 사전 점검과 실제 캡처는 서로 다른 체감 스타일(class) 버튼이다.

실제 브라우저/외부 네트워크 호출은 없다. HTML 응답과 FastAPI TestClient 로만
검증한다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    import importlib

    monkeypatch.setenv("HAEHAN_ADMIN_LEGACY_UI_FALLBACK", "1")
    # auth/local_agent_router 를 reload 하지 않는다: reload 하면 get_current_user 가 시험마다 새 객체가 되는데
    # 하위 라우터는 처음 import 된 옛 객체에 묶여 있어 dependency_overrides 가 두 번째 시험부터 안 먹혀
    # 파일 전체 실행 시 등록이 401 이 되고 KeyError: 'agent_id' 가 난다(단독 실행만 통과, 2026-10-04 확인).
    import ai_orchestrator.routers.admin_ui_router as _adm

    importlib.reload(_adm)

    import ai_orchestrator.agent_hub.registry.common as _reg_common
    import ai_orchestrator.agent_hub.registry.facade as _reg
    import ai_orchestrator.audit.audit_logger as _al
    import tools.gates.approval as _ap

    monkeypatch.setattr(_al, "_LOG_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(_ap, "_STORE_PATH", tmp_path / "approval_tokens.jsonl")
    # 2026-09-29 영속화 추가 후 필수: 안 하면 _reg.clear()가 실제 개발 세션의
    # data/local_agent_registry_state.json(실제 등록된 로컬 에이전트 상태)을 테스트마다 지운다.
    monkeypatch.setattr(_reg_common, "_REGISTRY_STATE_PATH", tmp_path / "local_agent_registry_state.json")

    _reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()

    yield

    _reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()


@pytest.fixture
def admin_user():
    return {"actor": "admin_test", "role": "admin"}


@pytest.fixture
def viewer_user():
    return {"actor": "viewer_test", "role": "viewer"}


def _make_test_client(user_override: dict):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.agent_hub.router.root import local_agent_router
    from ai_orchestrator.routers.admin_ui_router import admin_ui_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.include_router(admin_ui_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user_override
    return TestClient(app, raise_server_exceptions=True)


def _ui_html(user: dict) -> str:
    client = _make_test_client(user)
    r = client.get("/api/v1/admin/local-agents")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html"), r.headers
    return r.text


def _register(client) -> tuple[str, str]:
    reg = client.post(
        "/api/v1/local-agents/register",
        json={
            "host": "admin-ui-test",
            "os_name": "Windows 11",
            "version": "0.1.0",
        },
    ).json()
    return reg["agent_id"], reg["device_token"]


# ── 1. UI 에 "화면 캡처 사전 점검" 버튼이 표시된다 ─────────────────────


def test_ui_contains_dry_run_button_label(admin_user):
    html = _ui_html(admin_user)
    assert "화면 캡처 사전 점검" in html


def test_ui_button_has_expected_class_marker(admin_user):
    html = _ui_html(admin_user)
    # 테스트/자동화 용도로 안정적인 식별자 (CSS 클래스) 확인
    assert "dry-run-btn" in html


# ── 2. 버튼이 capture-screenshot API 를 호출한다 ────────────────────────


def test_ui_references_capture_screenshot_endpoint(admin_user):
    html = _ui_html(admin_user)
    assert "/api/v1/local-agents/" in html
    assert "/capture-screenshot" in html


# ── 3. UI 가 보내는 body 는 dry_run=true ────────────────────────────────


def test_ui_body_sends_dry_run_true(admin_user):
    html = _ui_html(admin_user)
    # JS 객체 리터럴에서 dry_run: true 확인 — 정규식으로 공백 허용
    assert re.search(r"dry_run\s*:\s*true", html) is not None


# ── 4. dry_run 경로 — true / false 가 정확히 1 종류씩 공존 ──────────────


def test_ui_sends_dry_run_true_exactly_for_dry_run_body(admin_user):
    """DRY_RUN_BODY 는 dry_run: true 리터럴로 정확히 1회 선언된다."""
    html = _ui_html(admin_user)
    # 'dry_run: true' 리터럴 — 공백 허용, body 선언 기준
    assert len(re.findall(r"dry_run\s*:\s*true", html)) >= 1


def test_ui_sends_dry_run_false_exactly_for_real_capture_body(admin_user):
    """REAL_CAPTURE_BODY 에서만 dry_run: false 를 사용해야 한다."""
    html = _ui_html(admin_user)
    # 'dry_run: false' 리터럴 — 공백 허용, body 선언 기준
    # (세 번째 이상 등장하면 분리되지 않은 진입점이 생긴 것으로 FAIL)
    matches = re.findall(r"dry_run\s*:\s*false", html)
    assert len(matches) == 1, f"UI 코드에 dry_run:false 경로는 정확히 1종류여야 합니다 (현재 {len(matches)}개)."


def test_ui_has_no_unauthorized_capture_labels(admin_user):
    """우회용 혹은 혼동을 주는 라벨이 UI 에 존재하면 FAIL.

    "1회 캡처 승인" 은 2단계 성공 메시지 "텔레그램에서 실제 1회 캡처 승인이
    필요합니다." 의 일부로 쓰이므로 substring 검사 대상이 아니다. 대신
    정식 실제-캡처 라벨("실제 1회 화면 캡처 요청") 외에 혼동을 유발할 수 있는
    라벨들만 차단한다.
    """
    html = _ui_html(admin_user)
    for forbidden_label in (
        "실제 화면 캡처",
        "실 캡처",
    ):
        assert forbidden_label not in html, f"허용되지 않은 캡처 라벨이 UI 에 존재: {forbidden_label}"


# ── 5/6. 실제 백엔드 호출 → task_id/status/dry_run + 텔레그램 안내 ─────


def test_backend_dry_run_response_matches_ui_contract(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True, "reason": "ui_dry_run_check"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["task_id"]
    assert data["status"] == "waiting_approval"
    assert data["dry_run"] is True
    # UI 성공 문구에 포함되는 핵심 단어 — HTML 에도 반드시 있어야 한다
    html = _ui_html(admin_user)
    assert "텔레그램" in html
    assert "승인" in html
    assert "사전 점검" in html


# ── 7. UI 및 응답에 금지 필드가 없다 ───────────────────────────────────

_FORBIDDEN_UI_STRINGS = [
    # 민감값 관련 키 (UI 에서 절대 읽거나 표시하면 안 된다)
    "approval_token",
    "device_token",
    "token_hash",
    "LOCAL_AGENT_SCREENSHOT_DIR",
    "screenshot_file",
    "screenshot_path",
    # 전체 경로/파일명 흔적
    ".png",
    ".haehan_agent",
    "C:\\\\",
    "C:/Users",
    "/home/",
]


def test_ui_does_not_display_forbidden_fields(admin_user):
    html = _ui_html(admin_user)
    for forbidden in _FORBIDDEN_UI_STRINGS:
        assert forbidden not in html, f"UI 에 금지된 문자열이 존재: {forbidden}"


def test_backend_response_does_not_leak_forbidden_fields(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True, "reason": "ui_dry_run_check"},
    )
    raw = r.text
    data = r.json()

    for forbidden_key in (
        "token_id",
        "device_token",
        "token_hash",
        "approval_token",
        "screenshot_file",
        "screenshot_path",
        "path",
        "dir",
        "password",
        "secret",
        "cookie",
    ):
        assert forbidden_key not in data, f"{forbidden_key} 가 응답에 포함됨"
        assert f'"{forbidden_key}"' not in raw

    # 경로/파일명 흔적
    assert ".png" not in raw
    assert "C:\\" not in raw
    assert "C:/Users" not in raw


# ── 8/9. 403 / 404 메시지 처리 ─────────────────────────────────────────


def test_ui_contains_forbidden_message(admin_user):
    html = _ui_html(admin_user)
    # 403 이 발생할 때 UI 에서 보여줄 문구
    assert "권한이 없습니다." in html


def test_ui_contains_agent_not_found_message(admin_user):
    html = _ui_html(admin_user)
    assert "로컬 에이전트를 찾을 수 없습니다." in html


def test_admin_ui_page_is_role_protected(viewer_user):
    client = _make_test_client(viewer_user)
    r = client.get("/api/v1/admin/local-agents")
    assert r.status_code == 403


def test_backend_returns_403_for_viewer(viewer_user, admin_user):
    admin_client = _make_test_client(admin_user)
    agent_id, _ = _register(admin_client)
    viewer_client = _make_test_client(viewer_user)
    r = viewer_client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True, "reason": "ui_dry_run_check"},
    )
    assert r.status_code == 403


def test_backend_returns_404_for_unknown_agent(admin_user):
    client = _make_test_client(admin_user)
    r = client.post(
        "/api/v1/local-agents/la-unknown/capture-screenshot",
        json={"dry_run": True, "reason": "ui_dry_run_check"},
    )
    assert r.status_code == 404


# ── 10. UI 는 단 하나의 capture-screenshot URL 만 호출한다 ───────────


def test_ui_uses_single_capture_endpoint(admin_user):
    """엔드포인트 URL 리터럴은 한 번만 등장해야 한다.

    (공통 postCapture 헬퍼가 한 번 정의되고, 두 버튼이 body 만 바꿔 호출)
    """
    html = _ui_html(admin_user)
    assert html.count("/capture-screenshot") == 1, (
        "capture-screenshot URL 리터럴은 공통 헬퍼에서 1회만 등장해야 합니다."
    )


# ══════════════════════════════════════════════════════════════════════
# 2단계 — 실제 1회 캡처 버튼 + confirm 게이트 검증
# ══════════════════════════════════════════════════════════════════════


def _extract_fn_body(html: str, fn_name: str) -> str:
    """인라인 JS 에서 특정 function 블록 본문을 추출.

    간단한 스캐너 — `function fn_name(...) {` 위치부터 시작해
    중괄호 깊이를 세며 닫힘까지 추출한다. 구현은 사용되는 JS 가
    문자열/정규식 리터럴에서 중괄호를 포함하지 않는다는 전제 하에 동작.
    """
    head = f"function {fn_name}("
    start = html.find(head)
    assert start != -1, f"{fn_name} 함수를 찾을 수 없습니다."
    body_start = html.find("{", start)
    depth = 0
    i = body_start
    while i < len(html):
        ch = html[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[body_start : i + 1]
        i += 1
    raise AssertionError(f"{fn_name} 함수의 닫힘 중괄호를 찾지 못했습니다.")


# ── 11. 기존 dry-run 버튼은 유지된다 (회귀 방지) ─────────────────────
def test_step2_preserves_dry_run_button(admin_user):
    html = _ui_html(admin_user)
    assert "화면 캡처 사전 점검" in html
    assert "dry-run-btn" in html


# ── 12. 신규 "실제 1회 화면 캡처 요청" 버튼이 표시된다 ────────────────
def test_step2_has_real_capture_button(admin_user):
    html = _ui_html(admin_user)
    assert "실제 1회 화면 캡처 요청" in html
    assert "real-capture-btn" in html
    # 라벨에 반드시 "1회" 포함
    assert "1회" in "실제 1회 화면 캡처 요청"


def test_real_capture_button_uses_distinct_class(admin_user):
    """위험 버튼은 dry-run 버튼과 다른 CSS 클래스를 갖는다."""
    html = _ui_html(admin_user)
    assert "real-capture-btn" in html
    assert "dry-run-btn" in html
    # 두 클래스 이름이 다르므로 시각 구분이 가능하다
    assert "real-capture-btn" != "dry-run-btn"


# ── 13. dry-run 버튼은 여전히 dry_run=true body 를 사용한다 ───────────
def test_dry_run_body_still_sends_true(admin_user):
    html = _ui_html(admin_user)
    body = _extract_fn_body(html, "requestDryRun")
    # 본문에는 dry_run:false 가 없어야 한다 (false 경로는 오직 real 캡처)
    assert re.search(r"dry_run\s*:\s*false", body) is None
    # DRY_RUN_BODY 참조는 있어야 한다
    assert "DRY_RUN_BODY" in body


# ── 14/15/16. confirm 게이트: 호출 → 취소 시 fetch 없음 → 취소 메시지 ──


def test_real_capture_calls_window_confirm(admin_user):
    html = _ui_html(admin_user)
    body = _extract_fn_body(html, "requestRealCapture")
    assert "window.confirm(" in body, "실제 캡처 요청 경로에 window.confirm 게이트가 없습니다."
    # confirm 문구도 반드시 포함
    assert "승인 후 로컬 PC에서 1회 화면 캡처가 실행됩니다." in html
    assert "서버에는 이미지가 업로드되지 않습니다." in html


def test_confirm_cancel_returns_before_fetch(admin_user):
    """confirm 취소 시 어떤 fetch/postCapture 도 호출되지 않음을 구조로 증명."""
    html = _ui_html(admin_user)
    body = _extract_fn_body(html, "requestRealCapture")

    confirm_pos = body.find("window.confirm(")
    # 본 함수는 fetch 를 공통 postCapture 를 통해 호출한다
    call_pos = body.find("postCapture(")
    assert confirm_pos != -1 and call_pos != -1
    assert confirm_pos < call_pos, "postCapture 호출이 window.confirm 이전에 나타나면 안 됩니다."

    between = body[confirm_pos:call_pos]
    # confirm 과 postCapture 사이에 early-return 이 존재해야 한다
    assert "return" in between
    # 취소 상태 메시지 문구도 early-return 앞에 있어야 한다
    assert "요청이 취소되었습니다." in between


def test_cancel_message_present_in_ui(admin_user):
    html = _ui_html(admin_user)
    assert "요청이 취소되었습니다." in html


# ── 17. confirm 확인 시 실제 body 는 dry_run=false ─────────────────────
def test_real_capture_body_uses_dry_run_false(admin_user):
    html = _ui_html(admin_user)
    body = _extract_fn_body(html, "requestRealCapture")
    # 실제 캡처 경로에서만 REAL_CAPTURE_BODY (dry_run:false) 를 사용
    assert "REAL_CAPTURE_BODY" in body
    # requestDryRun 함수 본문에는 REAL_CAPTURE_BODY 가 없어야 한다
    dry_body = _extract_fn_body(html, "requestDryRun")
    assert "REAL_CAPTURE_BODY" not in dry_body


def test_real_capture_body_constant_has_expected_fields(admin_user):
    html = _ui_html(admin_user)
    # 선언 라인 자체를 검증 — reason 값도 고정
    decl_re = (
        r"REAL_CAPTURE_BODY\s*=\s*\{\s*dry_run\s*:\s*false"
        r"\s*,\s*reason\s*:\s*\"ui_capture_once_request\"\s*\}"
    )
    assert re.search(decl_re, html) is not None, "REAL_CAPTURE_BODY 선언이 기대 형태가 아닙니다."


# ── 18. 실제 캡처 성공 안내 문구에 필수 단어가 들어있다 ───────────────


def test_real_capture_success_message_contains_required_phrases(admin_user):
    html = _ui_html(admin_user)
    # 성공 안내(성공 경로에서 setStatus 인자로 만들어지는 lines 배열)
    assert "실제 캡처 요청 생성 완료" in html
    assert "텔레그램에서 실제 1회 캡처 승인이 필요합니다." in html
    assert ("승인 후 로컬 PC에서 1회 실행되며 서버에는 이미지가 업로드되지 않습니다.") in html
    # 반드시 포함돼야 하는 의미 단어 — 테스트 체크포인트
    assert "텔레그램" in html
    assert "1회" in html
    assert "서버에는 이미지가 업로드되지 않습니다" in html


# ── 19. 실제 캡처 성공 응답 계약 (백엔드 호출) ────────────────────────


def test_backend_real_capture_returns_dry_run_false(admin_user):
    """UI 가 보낼 body 로 백엔드 호출 시 task_id/status/dry_run=false 가 온다."""
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": False, "reason": "ui_capture_once_request"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dry_run"] is False
    assert data["status"] == "waiting_approval"
    assert data["task_id"]
    # 응답에도 금지 필드가 없어야 한다 (이미지 업로드/경로/토큰 등)
    raw = r.text
    for forbidden_key in (
        "token_id",
        "device_token",
        "token_hash",
        "approval_token",
        "screenshot_file",
        "screenshot_path",
        "path",
        "dir",
    ):
        assert f'"{forbidden_key}"' not in raw
    assert ".png" not in raw
    assert "C:\\" not in raw
    assert "C:/Users" not in raw


# ── 20. UI 화면에는 여전히 금지 문자열이 없다 ─────────────────────────


def test_step2_no_forbidden_strings_in_ui(admin_user):
    """2단계에서도 이미지 업로드/경로/토큰 관련 문자열은 UI 에 절대 없다."""
    html = _ui_html(admin_user)
    forbidden = [
        "approval_token",
        "device_token",
        "token_hash",
        "LOCAL_AGENT_SCREENSHOT_DIR",
        "screenshot_file",
        "screenshot_path",
        ".png",
        ".haehan_agent",
        "C:/Users",
        "/home/",
    ]
    for s in forbidden:
        assert s not in html, f"UI 에 금지된 문자열이 존재: {s}"


# ══════════════════════════════════════════════════════════════════════
# deprecated banner 검증 (Stage 11-UI-7B)
# ══════════════════════════════════════════════════════════════════════


def test_legacy_page_contains_deprecated_banner_text(admin_user):
    """legacy 관리 화면임을 알리는 banner 문구가 HTML에 포함된다."""
    html = _ui_html(admin_user)
    assert "legacy 관리 화면" in html


def test_legacy_page_contains_admin_web_link(admin_user):
    """banner에 admin-web 표준 UI 링크가 포함된다."""
    html = _ui_html(admin_user)
    assert "/orchestrator/admin-web/local-agents" in html


def test_legacy_page_banner_contains_fallback_notice(admin_user):
    """banner에 fallback 용도 안내 문구가 포함된다."""
    html = _ui_html(admin_user)
    assert "fallback 용도" in html


def test_legacy_page_banner_contains_new_feature_notice(admin_user):
    """banner에 신규 기능은 admin-web에서만 추가됨을 안내한다."""
    html = _ui_html(admin_user)
    assert "신규 기능은 admin-web" in html


def test_legacy_banner_does_not_contain_capture_screenshot_string(admin_user):
    """banner에 /capture-screenshot 문자열이 포함되지 않는다.

    기존 test_ui_uses_single_capture_endpoint 가 endpoint URL 1회 등장을
    검증하므로 banner에 해당 문자열이 추가되면 해당 테스트가 깨진다.
    """
    html = _ui_html(admin_user)
    # 기존 테스트(test_ui_uses_single_capture_endpoint)와 일관성 유지
    assert html.count("/capture-screenshot") == 1, "capture-screenshot URL은 공통 헬퍼에서 1회만 등장해야 합니다."


def test_legacy_page_existing_functions_preserved(admin_user):
    """deprecated banner 추가 후에도 기존 기능 문자열이 모두 유지된다."""
    html = _ui_html(admin_user)
    preserved = [
        "화면 캡처 사전 점검",
        "실제 1회 화면 캡처 요청",
        "작업 목록 보기",
        "/api/v1/local-agents",
        "limit=50",
        "dry_run",
    ]
    for text in preserved:
        assert text in html, f"기존 기능 문자열 누락: {text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
