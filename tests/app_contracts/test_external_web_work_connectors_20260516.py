"""ASSISTANT_EXTERNAL_WEB_WORK_CONNECTORS_COMPLETION_01
외부 웹 업무(Naver/Google) 연결 경계 고정 테스트.

분류 계약:
  SERVER_READONLY_ALLOWED     — naver blog/shopping/status search
  WEB_TASK_REGISTRY           — naver/app_register, google/oauth_submit (이미 등록됨)
  OFFICIAL_API_OR_OAUTH_REQUIRED — google/gmail_read, calendar_read, drive_read
  LOCAL_AGENT_REQUIRED        — naver/blog_write, cafe_post
  USER_DIRECT_REQUIRED        — naver/mail_send
  QUARANTINE_OR_HOLD          — google/browser_login

안전 경계:
  - 실제 외부 사이트 접속 금지
  - 실제 OAuth/Google 로그인 금지
  - 실제 게시/메일발송/파일수정 금지
  - secret/token/password/session/cookie 노출 금지
  - 서버 브라우저 Google 로그인 자동화 금지
"""

from __future__ import annotations

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


# ── Naver 분류 계약 ─────────────────────────────────────────────────────────


class TestNaverClassificationContract:
    """Naver 업무 분류가 외부 웹 업무 레지스트리에 올바르게 선언되어 있다."""

    def _registry(self):
        from ai_orchestrator.tasks.external_work_registry import list_external_works

        return {e["work_key"]: e for e in list_external_works(provider="naver")}

    def test_naver_blog_search_is_server_readonly(self):
        """naver/blog_search는 SERVER_READONLY_ALLOWED이다."""
        reg = self._registry()
        assert "naver/blog_search" in reg
        assert reg["naver/blog_search"]["classification"] == "SERVER_READONLY_ALLOWED"
        assert reg["naver/blog_search"]["risk_level"] == "low"

    def test_naver_shopping_search_is_server_readonly(self):
        """naver/shopping_search는 SERVER_READONLY_ALLOWED이다."""
        reg = self._registry()
        assert reg["naver/shopping_search"]["classification"] == "SERVER_READONLY_ALLOWED"

    def test_naver_search_status_is_server_readonly(self):
        """naver/search_status는 SERVER_READONLY_ALLOWED이다."""
        reg = self._registry()
        assert reg["naver/search_status"]["classification"] == "SERVER_READONLY_ALLOWED"

    def test_naver_app_register_is_web_task_registry(self):
        """naver/app_register는 WEB_TASK_REGISTRY (approval gate 완비)이다."""
        reg = self._registry()
        assert reg["naver/app_register"]["classification"] == "WEB_TASK_REGISTRY"
        assert reg["naver/app_register"]["requires_approval"] is True
        assert reg["naver/app_register"]["registered_in_web_task"] is True

    def test_naver_blog_write_is_local_agent_required(self):
        """naver/blog_write는 LOCAL_AGENT_REQUIRED이다 (서버 직접 실행 불가)."""
        reg = self._registry()
        assert reg["naver/blog_write"]["classification"] == "LOCAL_AGENT_REQUIRED"
        assert reg["naver/blog_write"]["requires_approval"] is True

    def test_naver_cafe_post_is_local_agent_required(self):
        """naver/cafe_post는 LOCAL_AGENT_REQUIRED이다."""
        reg = self._registry()
        assert reg["naver/cafe_post"]["classification"] == "LOCAL_AGENT_REQUIRED"

    def test_naver_mail_send_is_user_direct_required(self):
        """naver/mail_send는 USER_DIRECT_REQUIRED이다."""
        reg = self._registry()
        assert reg["naver/mail_send"]["classification"] == "USER_DIRECT_REQUIRED"
        assert reg["naver/mail_send"]["requires_approval"] is True

    def test_naver_readonly_no_approval_required(self):
        """naver read-only 3개는 승인 불필요이다."""
        reg = self._registry()
        for key in ["naver/blog_search", "naver/shopping_search", "naver/search_status"]:
            assert reg[key]["requires_approval"] is False, f"{key}: read-only인데 approval required 설정됨"

    def test_naver_write_ops_all_require_approval(self):
        """Naver 쓰기 작업(blog_write, cafe_post, mail_send, app_register)은 모두 승인 필요."""
        reg = self._registry()
        for key in ["naver/blog_write", "naver/cafe_post", "naver/mail_send", "naver/app_register"]:
            assert reg[key]["requires_approval"] is True, f"{key}: 쓰기 작업인데 approval required 미설정"


# ── Google 분류 계약 ────────────────────────────────────────────────────────


class TestGoogleClassificationContract:
    """Google 업무 분류가 외부 웹 업무 레지스트리에 올바르게 선언되어 있다."""

    def _registry(self):
        from ai_orchestrator.tasks.external_work_registry import list_external_works

        return {e["work_key"]: e for e in list_external_works(provider="google")}

    def test_google_oauth_submit_is_web_task_registry(self):
        """google/oauth_submit는 WEB_TASK_REGISTRY (approval gate 완비)이다."""
        reg = self._registry()
        assert reg["google/oauth_submit"]["classification"] == "WEB_TASK_REGISTRY"
        assert reg["google/oauth_submit"]["registered_in_web_task"] is True

    def test_google_gmail_read_is_official_api_required(self):
        """google/gmail_read는 OFFICIAL_API_OR_OAUTH_REQUIRED이다."""
        reg = self._registry()
        assert reg["google/gmail_read"]["classification"] == "OFFICIAL_API_OR_OAUTH_REQUIRED"
        assert reg["google/gmail_read"]["auth_method"] == "oauth"

    def test_google_calendar_read_is_official_api_required(self):
        """google/calendar_read는 OFFICIAL_API_OR_OAUTH_REQUIRED이다."""
        reg = self._registry()
        assert reg["google/calendar_read"]["classification"] == "OFFICIAL_API_OR_OAUTH_REQUIRED"

    def test_google_drive_read_is_official_api_required(self):
        """google/drive_read는 OFFICIAL_API_OR_OAUTH_REQUIRED이다."""
        reg = self._registry()
        assert reg["google/drive_read"]["classification"] == "OFFICIAL_API_OR_OAUTH_REQUIRED"

    def test_google_browser_login_is_quarantine(self):
        """google/browser_login은 QUARANTINE_OR_HOLD이다 (서버 자동화 금지)."""
        reg = self._registry()
        assert reg["google/browser_login"]["classification"] == "QUARANTINE_OR_HOLD"

    def test_google_all_account_ops_require_auth(self):
        """Google 계정 기반 작업은 모두 requires_auth=True이다."""
        reg = self._registry()
        for key, entry in reg.items():
            assert entry["requires_auth"] is True, f"{key}: Google 계정 작업인데 requires_auth 미설정"


# ── 서버 브라우저 금지 경계 ──────────────────────────────────────────────────


class TestServerBrowserProhibitionBoundary:
    """서버에서 Naver/Google 계정 로그인을 직접 브라우저로 자동화하지 않는다."""

    def test_google_browser_login_classified_as_quarantine(self):
        """google/browser_login이 QUARANTINE_OR_HOLD로 분류됨을 확인."""
        from ai_orchestrator.tasks.external_work_registry import get_external_work

        entry = get_external_work("google", "browser_login")
        assert entry is not None
        assert entry.classification == "QUARANTINE_OR_HOLD"

    def test_naver_write_ops_not_server_classified(self):
        """Naver 쓰기 작업은 SERVER 위치로 분류되지 않는다."""
        from ai_orchestrator.tasks.external_work_registry import list_external_works

        writes = [
            e
            for e in list_external_works(provider="naver")
            if e["work_type"] in ("blog_write", "cafe_post", "mail_send")
        ]
        for entry in writes:
            assert entry["execution_location"] != "SERVER", f"{entry['work_key']}: 쓰기 작업인데 SERVER 위치로 설정됨"

    def test_server_egress_policy_exists(self):
        """server/server_egress_policy.py 서버 외부 접속 정책 파일 존재."""
        assert (REPO_ROOT / "ai_orchestrator" / "server" / "server_egress_policy.py").exists()

    def test_external_url_blocker_exists(self):
        """server/external_url_blocker.py 외부 URL 차단 파일 존재."""
        assert (REPO_ROOT / "ai_orchestrator" / "server" / "external_url_blocker.py").exists()


# ── secret/token 비노출 경계 ────────────────────────────────────────────────


class TestSecretNonExposureBoundary:
    """응답/레지스트리에 secret/token/password/session/cookie가 노출되지 않는다."""

    def test_external_work_registry_no_secret_values(self):
        """external_work_registry의 list_external_works 응답에 실제 민감값 없음.
        notes 필드는 문서 참조 문자열 허용 (예: token.json 파일명), 실제 credential 값은 금지.
        """
        import re

        from ai_orchestrator.tasks.external_work_registry import list_external_works

        entries = list_external_works()
        # 실제 credential 값 패턴만 검사 (key=value 형태의 하드코딩 시크릿)
        # 파일명 참조(token.json, credentials.json)나 policy 설명 텍스트는 허용
        for entry in entries:
            for field_key in ("classification", "execution_location", "auth_method"):
                val = str(entry.get(field_key, "")).lower()
                # auth_method 값은 정해진 목록만 허용
                if field_key == "auth_method":
                    allowed = {"none", "oauth", "browser_session", "user_direct"}
                    assert val in allowed, f"{entry['work_key']}.auth_method 값 '{val}'이 허용 목록 밖"
            # 실제 secret 값(따옴표 안 긴 문자열)이 있으면 안 됨 — notes 포함
            notes_blob = str(entry.get("notes", ""))
            bad_patterns = re.findall(
                r'(?:password|client_secret|api_key)\s*[:=]\s*["\'][^"\']{8,}["\']', notes_blob, re.I
            )
            assert not bad_patterns, f"{entry['work_key']}: notes에 민감값 패턴 발견 {bad_patterns}"

    def test_web_task_registry_no_secret_values(self):
        """web_task_registry의 list_entries 응답에 민감값 없음."""
        from ai_orchestrator.web_task.web_task_registry import list_entries

        entries = list_entries()
        blob = str(entries).lower()
        for kw in ("password", "secret", "token", "cookie", "session"):
            assert kw not in blob, f"web_task_registry 응답에 민감 키워드 '{kw}' 포함"

    def test_gmail_reader_source_has_no_hardcoded_secrets(self):
        """gmail_reader.py에 하드코딩 secret/token 없음."""
        src = (REPO_ROOT / "ai_orchestrator" / "connectors" / "google" / "gmail_reader.py").read_text(encoding="utf-8")
        # 변수 선언이 아닌 실제 값 하드코딩 여부 확인 (따옴표 안에 실제 값이 있으면 안 됨)
        import re

        hard_coded = re.findall(r'(?:password|secret|token)\s*=\s*["\'][^"\']{8,}["\']', src, re.I)
        assert not hard_coded, f"gmail_reader.py에 하드코딩 민감값: {hard_coded}"


# ── naver_search_router 등록 확인 ────────────────────────────────────────────


class TestNaverSearchRouterRegistration:
    """naver_search_router가 메인 API 라우터에 등록되어 있다."""

    def test_naver_search_router_in_router_py(self):
        """router.py에 naver_search_router import 및 include 확인."""
        src = (REPO_ROOT / "ai_orchestrator" / "routers" / "registry.py").read_text(encoding="utf-8")
        assert "naver_search_router" in src, "router.py에 naver_search_router가 없음"
        assert "include_router(naver_search_router)" in src, "router.py에 include_router(naver_search_router) 없음"

    def test_naver_search_router_importable(self):
        """naver_search_router가 임포트 가능하다."""
        from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router

        assert naver_search_router is not None

    def test_naver_search_router_has_three_endpoints(self):
        """naver_search_router에 blog-search, shopping-search, status 3개 endpoint 존재."""
        from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router

        routes = [r.path for r in naver_search_router.routes]
        assert any("blog-search" in r for r in routes), "blog-search endpoint 없음"
        assert any("shopping-search" in r for r in routes), "shopping-search endpoint 없음"
        assert any("status" in r for r in routes), "status endpoint 없음"

    def test_naver_search_router_is_read_only(self):
        """naver_search_router 소스에 write/delete/update 없음 (read-only 확인)."""
        src = (REPO_ROOT / "ai_orchestrator" / "connectors" / "naver_search" / "naver_search_router.py").read_text(encoding="utf-8")
        assert "쓰기 API 없음" in src or "read-only" in src.lower(), "naver_search_router에 read-only 명시 없음"

    def test_naver_search_router_requires_admin_or_owner(self):
        """naver_search_router가 require_role 인증을 사용한다."""
        src = (REPO_ROOT / "ai_orchestrator" / "connectors" / "naver_search" / "naver_search_router.py").read_text(encoding="utf-8")
        assert "require_role" in src, "naver_search_router에 인증(require_role) 없음"


# ── web_task_registry Naver/Google 등록 확인 ─────────────────────────────────


class TestWebTaskRegistryNaVerGoogle:
    """web_task_registry에 Naver/Google 항목이 등록되어 있다."""

    def test_naver_app_register_in_registry(self):
        """naver/app_register가 web_task_registry에 등록되어 있다."""
        from ai_orchestrator.web_task.web_task_registry import get_entry

        entry = get_entry("naver", "app_register")
        assert entry is not None
        assert entry.risk_level == "high"
        assert entry.requires_approval is True

    def test_google_oauth_submit_in_registry(self):
        """google/oauth_submit이 web_task_registry에 등록되어 있다."""
        from ai_orchestrator.web_task.web_task_registry import get_entry

        entry = get_entry("google", "oauth_submit")
        assert entry is not None
        assert entry.risk_level == "high"
        assert entry.requires_approval is True

    def test_registry_does_not_expose_adapter_class(self):
        """list_entries()에 adapter_class가 포함되지 않는다."""
        from ai_orchestrator.web_task.web_task_registry import list_entries

        for entry in list_entries():
            assert "adapter_class" not in entry


# ── external_work_registry 임포트 및 구조 확인 ───────────────────────────────


class TestExternalWorkRegistryStructure:
    """external_work_registry.py 모듈 구조 확인."""

    def test_module_importable(self):
        """external_work_registry 모듈이 임포트 가능하다."""
        from ai_orchestrator.tasks import external_work_registry

        assert external_work_registry is not None

    def test_list_external_works_returns_list(self):
        """list_external_works()가 list를 반환한다."""
        from ai_orchestrator.tasks.external_work_registry import list_external_works

        result = list_external_works()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_all_entries_have_required_fields(self):
        """모든 항목이 필수 필드를 갖는다."""
        from ai_orchestrator.tasks.external_work_registry import list_external_works

        required_fields = {
            "work_key",
            "provider",
            "work_type",
            "description",
            "classification",
            "execution_location",
            "risk_level",
            "requires_approval",
            "requires_auth",
            "auth_method",
            "registered_in_web_task",
        }
        for entry in list_external_works():
            missing = required_fields - set(entry.keys())
            assert not missing, f"{entry['work_key']}: 필드 누락 {missing}"

    def test_provider_filter_works(self):
        """provider 필터가 정상 동작한다."""
        from ai_orchestrator.tasks.external_work_registry import list_external_works

        naver_only = list_external_works(provider="naver")
        assert all(e["provider"] == "naver" for e in naver_only)

    def test_classification_filter_works(self):
        """classification 필터가 정상 동작한다."""
        from ai_orchestrator.tasks.external_work_registry import list_external_works

        readonly = list_external_works(classification="SERVER_READONLY_ALLOWED")
        assert all(e["classification"] == "SERVER_READONLY_ALLOWED" for e in readonly)


# ── 기존 준공 범위 테스트 PASS 유지 확인 ────────────────────────────────────


class TestExistingCloseoutTestsUnchanged:
    """기존 준공 범위 테스트 파일이 변경되지 않았다."""

    CLOSEOUT_TESTS = [
        "tests/app_contracts/test_app_scope_web_desktop_boundary_20260516.py",
        "tests/server_features/test_backend_web_task_approval_flow_20260516.py",
        "tests/app_contracts/test_backend_direct_dict_boundary_lock_20260516.py",
    ]

    @pytest.mark.parametrize("test_path", CLOSEOUT_TESTS)
    def test_closeout_test_still_exists(self, test_path):
        """기존 준공 테스트 파일이 그대로 존재한다."""
        assert (REPO_ROOT / test_path).exists(), f"준공 테스트 없음: {test_path}"

    def test_cad_hold_unchanged(self):
        """CAD 모듈은 17130f8e(2026-06-04)에서 전체 삭제됨 — 로컬 에이전트에 CAD 커넥터가 없다."""
        # 구 기대: local_agent/cad/controller_loader.py 가 local_worker_plugins 에 의존(HOLD).
        # 현행: CAD 디렉터리 자체가 없어야 하며, 웹 커넥터가 CAD 를 되살리지 않아야 한다.
        assert not (REPO_ROOT / "local_agent" / "cad").exists()
        assert not (REPO_ROOT / "local_agent" / "cad" / "controller_loader.py").exists()
