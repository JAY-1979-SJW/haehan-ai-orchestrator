"""task_executor — CAD API 액션 (3단계 편입) 단위 테스트.

실 cad-backend / orchestrator 없이 동작하도록 httpx.Client 를 monkeypatch
로 통째로 stub 한다. 스펙 테이블 기반 dispatch / 경로 치환 / query 및 body
전달 / approval 헤더 / 오류 표준화 / approval_policy 통합까지 검증.
"""
from __future__ import annotations

import os
import sys
from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


# ───────────────────────────────────────────────────────────────────
# httpx.Client stub — .request() 인자 기록 + 지정 응답 반환
# ───────────────────────────────────────────────────────────────────
class _StubResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_body: Optional[Any] = None,
        content: bytes = b"",
        headers: Optional[dict] = None,
    ):
        self.status_code = status_code
        self._json = json_body
        self.content = content if content else (
            b"" if json_body is None else b'{"_":1}'
        )
        # httpx.Headers-like
        self.headers = httpx.Headers(headers or {"content-type": "application/json"})
        self.text = (self.content or b"").decode("utf-8", errors="replace")

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _StubClient:
    """httpx.Client 인터페이스를 최소 흉내내는 stub.

    ``calls`` 리스트에 (method, url, kwargs) 를 기록한다.
    """
    def __init__(self, *, response: _StubResponse = None, exc: Exception = None):
        self._resp = response or _StubResponse(json_body={"ok": True})
        self._exc = exc
        self.calls: List[dict] = []
        self._timeout = None
        self._auth = None

    def __call__(self, **kw):
        # httpx.Client(timeout=..., auth=...) 로 호출되는 시그니처 흉내
        self._timeout = kw.get("timeout")
        self._auth = kw.get("auth")
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def request(self, *, method, url, headers=None, params=None, json=None, files=None):
        self.calls.append({
            "method": method, "url": url,
            "headers": dict(headers or {}),
            "params": dict(params or {}) if params else {},
            "json": json,
            "files": files,
            "auth": self._auth,
        })
        if self._exc is not None:
            raise self._exc
        return self._resp


@pytest.fixture()
def stub_httpx(monkeypatch):
    """AGENT_CAD_PROXY_* env 주입 + httpx.Client 대체."""
    monkeypatch.setenv("AGENT_CAD_PROXY_URL", "http://orchestrator.test:8400")
    monkeypatch.setenv("AGENT_CAD_PROXY_USER", "agent_u")
    monkeypatch.setenv("AGENT_CAD_PROXY_PASSWORD", "agent_pw")
    # 기본 스텁: 200 with json body
    stub = _StubClient()
    from agent import task_executor as te
    monkeypatch.setattr(te.httpx, "Client", stub)
    return stub


# ═══════════════════════════════════════════════════════════════════
# 1) 스펙 테이블 등록/매핑
# ═══════════════════════════════════════════════════════════════════
def test_all_cad_api_actions_have_dispatch():
    from agent import task_executor as te
    from agent.cad_api_spec import CAD_API_ACTIONS
    supported = set(te.supported_actions())
    for spec in CAD_API_ACTIONS:
        assert spec.action in supported, f"{spec.action} missing dispatch"


def test_spec_table_has_42_entries():
    from agent.cad_api_spec import CAD_API_ACTIONS
    assert len(CAD_API_ACTIONS) == 42


# ═══════════════════════════════════════════════════════════════════
# 2) 읽기 dispatch — GET 경로 / query 전달
# ═══════════════════════════════════════════════════════════════════
def test_list_projects_basic(stub_httpx):
    stub_httpx._resp = _StubResponse(
        status_code=200,
        json_body={"items": [{"id": 1}, {"id": 2}]},
    )
    from agent import task_executor as te
    out = te.execute_task({
        "id": "t1", "action": "cad.list_projects",
    })
    assert out["ok"] is True
    assert out["data"]["items"] == [{"id": 1}, {"id": 2}]
    assert out["data"]["status_code"] == 200
    assert len(stub_httpx.calls) == 1
    c = stub_httpx.calls[0]
    assert c["method"] == "GET"
    assert c["url"] == "http://orchestrator.test:8400/api/v1/cad/projects"
    assert c["json"] is None
    # Basic auth 가 전달됨
    assert c["auth"] == ("agent_u", "agent_pw")


def test_list_projects_with_query(stub_httpx):
    from agent import task_executor as te
    out = te.execute_task({
        "id": "t1", "action": "cad.list_projects",
        "status": "active", "trade_type": "소방기계", "limit": 5,
    })
    assert out["ok"] is True
    c = stub_httpx.calls[0]
    assert c["params"] == {"status": "active", "trade_type": "소방기계", "limit": 5}


def test_get_project_path_substitution(stub_httpx):
    from agent import task_executor as te
    out = te.execute_task({
        "id": "t1", "action": "cad.get_project", "project_id": 42,
    })
    assert out["ok"] is True
    c = stub_httpx.calls[0]
    assert c["url"].endswith("/api/v1/cad/projects/42")
    assert c["method"] == "GET"


def test_missing_path_param_returns_standard_error(stub_httpx):
    from agent import task_executor as te
    from agent import errors
    out = te.execute_task({
        "id": "t1", "action": "cad.get_project",  # project_id 누락
    })
    assert out["ok"] is False
    assert out["error"] == errors.CAD_MISSING_PARAM
    assert stub_httpx.calls == []  # 상류 호출 없음


# ═══════════════════════════════════════════════════════════════════
# 3) 쓰기 dispatch — body + approval 헤더
# ═══════════════════════════════════════════════════════════════════
def test_create_project_body_and_approval_headers(stub_httpx):
    stub_httpx._resp = _StubResponse(
        status_code=201, json_body={"id": 99, "name": "new"},
    )
    from agent import task_executor as te
    out = te.execute_task({
        "id": "task-007",
        "action": "cad.create_project",
        "body": {"name": "new", "trade_type": "소방기계"},
        "approval_token": "tok-deadbeef",
    })
    assert out["ok"] is True
    assert out["data"]["status_code"] == 201
    c = stub_httpx.calls[0]
    assert c["method"] == "POST"
    assert c["url"].endswith("/api/v1/cad/projects")
    assert c["json"] == {"name": "new", "trade_type": "소방기계"}
    # approval 헤더 forwarding
    assert c["headers"]["X-Task-Id"] == "task-007"
    assert c["headers"]["X-Approval-Token-Id"] == "tok-deadbeef"


def test_patch_update_project(stub_httpx):
    from agent import task_executor as te
    out = te.execute_task({
        "id": "t2", "action": "cad.update_project",
        "project_id": 3, "body": {"status": "done"},
        "approval_token": "tok",
    })
    assert out["ok"] is True
    c = stub_httpx.calls[0]
    assert c["method"] == "PATCH"
    assert c["url"].endswith("/api/v1/cad/projects/3")
    assert c["json"] == {"status": "done"}


def test_delete_project_has_no_body(stub_httpx):
    from agent import task_executor as te
    out = te.execute_task({
        "id": "t3", "action": "cad.delete_project",
        "project_id": 9,
        "approval_token": "tok",
    })
    assert out["ok"] is True
    c = stub_httpx.calls[0]
    assert c["method"] == "DELETE"
    assert c["url"].endswith("/api/v1/cad/projects/9")
    assert c["json"] is None


def test_post_no_body_action_parse_drawing(stub_httpx):
    from agent import task_executor as te
    out = te.execute_task({
        "id": "t4", "action": "cad.parse_drawing",
        "drawing_id": 77,
        "approval_token": "tok",
    })
    assert out["ok"] is True
    c = stub_httpx.calls[0]
    assert c["method"] == "POST"
    assert c["url"].endswith("/api/v1/cad/drawings/77/parse")
    # parse 는 body=None spec
    assert c["json"] is None


# ═══════════════════════════════════════════════════════════════════
# 4) 바이너리 응답 (download_export)
# ═══════════════════════════════════════════════════════════════════
def test_download_export_binary_meta_only(stub_httpx):
    stub_httpx._resp = _StubResponse(
        status_code=200,
        content=b"X" * 4096,
        headers={"content-type": "application/octet-stream"},
    )
    from agent import task_executor as te
    out = te.execute_task({
        "id": "t5", "action": "cad.download_export",
        "export_job_id": 11,
    })
    assert out["ok"] is True
    # 바이너리 본문을 data 에 싣지 않고 메타만 기록
    assert out["data"]["content_type"] == "application/octet-stream"
    assert out["data"]["size"] == 4096
    assert "raw_text_preview" not in out["data"]


# ═══════════════════════════════════════════════════════════════════
# 5) 상류 오류 표준화
# ═══════════════════════════════════════════════════════════════════
def test_upstream_4xx_marks_failure_with_standard_code(stub_httpx):
    stub_httpx._resp = _StubResponse(
        status_code=404,
        json_body={"detail": "not found"},
    )
    from agent import task_executor as te
    from agent import errors
    out = te.execute_task({
        "id": "t6", "action": "cad.get_project",
        "project_id": 9999,
    })
    assert out["ok"] is False
    assert out["error"].startswith(errors.CAD_PROXY_UPSTREAM_ERROR)
    assert out["error"].endswith(":404")
    assert out["data"]["status_code"] == 404


def test_connect_error_marks_unreachable(stub_httpx, monkeypatch):
    stub_httpx._exc = httpx.ConnectError("no route")
    from agent import task_executor as te
    from agent import errors
    out = te.execute_task({
        "id": "t7", "action": "cad.list_projects",
    })
    assert out["ok"] is False
    assert out["error"] == errors.CAD_PROXY_UNREACHABLE


def test_timeout_marks_timeout(stub_httpx):
    stub_httpx._exc = httpx.ReadTimeout("slow")
    from agent import task_executor as te
    from agent import errors
    out = te.execute_task({
        "id": "t8", "action": "cad.list_projects",
    })
    assert out["ok"] is False
    assert out["error"] == errors.CAD_PROXY_TIMEOUT


def test_missing_auth_env_refuses(monkeypatch):
    """AGENT_CAD_PROXY_USER 미설정 → 네트워크 호출 전에 standard error."""
    from agent import task_executor as te, errors
    monkeypatch.delenv("AGENT_CAD_PROXY_USER", raising=False)
    monkeypatch.delenv("AGENT_CAD_PROXY_PASSWORD", raising=False)
    # httpx 를 호출하면 실제 네트워크를 탈 수 있으므로 지레 대체
    called = {"n": 0}
    class _Never:
        def __call__(self, **kw):
            called["n"] += 1
            raise AssertionError("should not reach httpx")
    monkeypatch.setattr(te.httpx, "Client", _Never())
    out = te.execute_task({"id": "t9", "action": "cad.list_projects"})
    assert out["ok"] is False
    assert out["error"] == errors.CAD_PROXY_AUTH_MISSING
    assert called["n"] == 0


# ═══════════════════════════════════════════════════════════════════
# 6) multipart 업로드 — cad.upload_drawing
# ═══════════════════════════════════════════════════════════════════
def test_upload_drawing_reads_local_and_sends_multipart(stub_httpx, tmp_path):
    f = tmp_path / "sample.dwg"
    f.write_bytes(b"DWGBYTES" * 128)  # 1KB 더미
    from agent import task_executor as te
    out = te.execute_task({
        "id": "t-up", "action": "cad.upload_drawing",
        "project_id": 5, "file_path": str(f),
        "approval_token": "tok",
    })
    assert out["ok"] is True
    c = stub_httpx.calls[0]
    assert c["method"] == "POST"
    assert c["url"].endswith("/api/v1/cad/projects/5/drawings/upload")
    # multipart files 인자로 전달됨, json 은 None
    assert c["json"] is None
    assert c["files"] is not None


def test_upload_drawing_missing_file_returns_standard_error(stub_httpx, tmp_path):
    from agent import task_executor as te
    out = te.execute_task({
        "id": "t-up2", "action": "cad.upload_drawing",
        "project_id": 5, "file_path": str(tmp_path / "nope.dwg"),
        "approval_token": "tok",
    })
    assert out["ok"] is False
    assert out["error"] in ("file_not_found", "file_not_allowed")


def test_upload_drawing_missing_project_id(stub_httpx, tmp_path):
    f = tmp_path / "sample.dwg"
    f.write_bytes(b"X")
    from agent import task_executor as te
    from agent import errors
    out = te.execute_task({
        "id": "t-up3", "action": "cad.upload_drawing",
        "file_path": str(f),
        "approval_token": "tok",
    })
    assert out["ok"] is False
    assert out["error"] == errors.CAD_MISSING_PARAM


# ═══════════════════════════════════════════════════════════════════
# 7) approval_policy 연동 — write action 은 approval_token 필수
# ═══════════════════════════════════════════════════════════════════
def test_approval_policy_blocks_cad_write_without_token(monkeypatch, tmp_path):
    from agent import approval_policy, config as _cfg
    # work/out 디렉토리는 unused (requires_file_path=False) 지만 설정 필수.
    monkeypatch.setattr(_cfg, "AGENT_WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(_cfg, "AGENT_OUTPUT_DIR", tmp_path / "out")
    decision = approval_policy.evaluate({
        "id": "t-x", "action": "cad.create_project",
        "body": {"name": "x"},
    })
    assert decision.allowed is False
    # 기존 정책대로 approval_required
    assert decision.error == approval_policy.APPROVAL_REQUIRED
    assert decision.risk_level == "medium"
    assert decision.category == "cad"


def test_approval_policy_allows_cad_write_with_token(monkeypatch, tmp_path):
    from agent import approval_policy, config as _cfg
    monkeypatch.setattr(_cfg, "AGENT_WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(_cfg, "AGENT_OUTPUT_DIR", tmp_path / "out")
    decision = approval_policy.evaluate({
        "id": "t-ok", "action": "cad.create_project",
        "body": {"name": "x"},
        "approval_token": "tok",
        "approved_by": "alice",
    })
    assert decision.allowed is True
    assert decision.approved is True
    assert decision.approved_by == "alice"


def test_approval_policy_allows_cad_read_without_token(monkeypatch, tmp_path):
    from agent import approval_policy, config as _cfg
    monkeypatch.setattr(_cfg, "AGENT_WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(_cfg, "AGENT_OUTPUT_DIR", tmp_path / "out")
    decision = approval_policy.evaluate({
        "id": "t-ro", "action": "cad.list_projects",
    })
    assert decision.allowed is True
    assert decision.error is None


def test_approval_policy_skips_save_as_for_cad_api_write(monkeypatch, tmp_path):
    """cad.create_project 는 read_only=False 지만 requires_save_as=False 라
    save_as 없이도 통과되어야 한다."""
    from agent import approval_policy, config as _cfg
    monkeypatch.setattr(_cfg, "AGENT_WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(_cfg, "AGENT_OUTPUT_DIR", tmp_path / "out")
    d = approval_policy.evaluate({
        "id": "t-nosave", "action": "cad.update_project",
        "project_id": 1, "body": {"name": "x"},
        "approval_token": "tok",
    })
    assert d.allowed is True
    # save_as 누락이 FAIL 아님을 확인
    assert d.error is None


def test_approval_policy_still_requires_save_as_for_legacy_cad_com(monkeypatch, tmp_path):
    """cad.add_text_save_as 는 기존처럼 save_as 필수 (regression 방지)."""
    from agent import approval_policy, config as _cfg
    work = tmp_path / "work"
    out_dir = tmp_path / "out"
    work.mkdir(); out_dir.mkdir()
    f = work / "sample.dwg"
    f.write_bytes(b"dummy")
    monkeypatch.setattr(_cfg, "AGENT_WORK_DIR", work)
    monkeypatch.setattr(_cfg, "AGENT_OUTPUT_DIR", out_dir)
    d = approval_policy.evaluate({
        "id": "t-legacy", "action": "cad.add_text_save_as",
        "file_path": str(f),
        "approval_token": "tok",
    })
    assert d.allowed is False
    assert d.error == approval_policy.SAVE_AS_REQUIRED


# ═══════════════════════════════════════════════════════════════════
# 8) policy whitelist 와의 sync
# ═══════════════════════════════════════════════════════════════════
def test_cad_api_actions_in_policy_whitelist():
    from agent import policy
    from agent.cad_api_spec import action_names
    for name in action_names():
        assert name in policy.ALLOWED_ACTIONS, f"{name} not whitelisted"


# ═══════════════════════════════════════════════════════════════════
# 9) 에러 코드 표준 등록
# ═══════════════════════════════════════════════════════════════════
def test_new_cad_proxy_error_codes_registered():
    from agent import errors
    for name in (
        "CAD_PROXY_UNREACHABLE",
        "CAD_PROXY_TIMEOUT",
        "CAD_PROXY_AUTH_MISSING",
        "CAD_PROXY_UPSTREAM_ERROR",
        "CAD_MISSING_PARAM",
    ):
        assert hasattr(errors, name), f"errors.{name} missing"
        assert getattr(errors, name) in errors.ALL_CODES, name
        assert errors.is_standard_code(getattr(errors, name))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
