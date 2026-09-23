"""MCP write 게이트 + upstream 헬퍼 검증.

검증 포인트:
A. read tool
   - cad-backend 직통 조회 성공 (mock)
   - approval 없이 허용
   - MCP_ALLOW_DIRECT_READ=false 시 즉시 RuntimeError

B. write tool
   - cad-backend direct URL 사용 시 즉시 실패 (allow_direct_write=True 시뮬레이션)
   - orchestrator URL 없으면 실패 → mcp_write_requires_orchestrator
   - actor 없으면 실패 → mcp_write_missing_actor
   - task_id 없으면 실패 → mcp_write_requires_task_id
   - approval_token 없으면 실패 → mcp_write_requires_approval
   - 모두 있으면 성공 → 실제 상류 대상이 orchestrator 임을 검증
   - write 호출 URL 에 cad-backend 주소 없음 검증

C. 보안
   - MCP_ALLOW_DIRECT_WRITE 가 코드 레벨에서 항상 False

mcp 패키지 불필요 — write_guard 와 upstream 만 테스트.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ── 공용 async 실행 헬퍼 ─────────────────────────────────────────────


def _run(coro):
    """Python 3.10+ 호환 async 실행."""
    return asyncio.run(coro)


# ── 픽스처: 공통 환경 ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_config(monkeypatch):
    """각 테스트 전 config 재로드."""
    monkeypatch.setenv("CAD_BACKEND_URL", "http://cad-backend:8000")
    monkeypatch.setenv("ORCHESTRATOR_URL", "http://orchestrator:8400")
    monkeypatch.setenv("MCP_ALLOW_DIRECT_READ", "true")
    monkeypatch.setenv("MCP_ORCHESTRATOR_USER", "svc-mcp")
    monkeypatch.setenv("MCP_ORCHESTRATOR_PASS", "svc-pass")
    import mcp_server.config as cfg

    importlib.reload(cfg)
    yield
    importlib.reload(cfg)


# ═════════════════════════════════════════════════════════════════════
# write_guard — check_write_prerequisites
# ═════════════════════════════════════════════════════════════════════


class TestCheckWritePrerequisites:
    """write_guard.check_write_prerequisites 단위 테스트."""

    def _ok(self, **override):
        from mcp_server.write_guard import check_write_prerequisites

        defaults = dict(
            orchestrator_url="http://orchestrator:8400",
            actor="jay",
            task_id="task-123",
            approval_token="tok-abc",  # noqa: S106
            allow_direct_write=False,
        )
        defaults.update(override)
        return check_write_prerequisites(**defaults)

    def _fail_code(self, **override) -> str:
        from mcp_server.write_guard import McpWriteError

        with pytest.raises(McpWriteError) as exc_info:
            self._ok(**override)
        return exc_info.value.error_code

    # ── 성공 경로 ──────────────────────────────────────────────────────

    def test_all_present_returns_write_context(self):
        from mcp_server.write_guard import WriteContext

        ctx = self._ok()
        assert isinstance(ctx, WriteContext)
        assert ctx.actor == "jay"
        assert ctx.task_id == "task-123"
        assert ctx.approval_token == "tok-abc"  # noqa: S105
        assert ctx.orchestrator_url == "http://orchestrator:8400"

    def test_trailing_slash_stripped_from_orchestrator_url(self):
        ctx = self._ok(orchestrator_url="http://orchestrator:8400/")
        assert not ctx.orchestrator_url.endswith("/")

    def test_whitespace_stripped_from_params(self):
        ctx = self._ok(actor="  jay  ", task_id=" task-123 ", approval_token=" tok ")  # noqa: S106
        assert ctx.actor == "jay"
        assert ctx.task_id == "task-123"
        assert ctx.approval_token == "tok"  # noqa: S105

    # ── 실패: allow_direct_write=True ─────────────────────────────────

    def test_direct_write_flag_raises_forbidden(self):
        assert self._fail_code(allow_direct_write=True) == "mcp_write_direct_forbidden"

    # ── 실패: orchestrator_url 없음 ───────────────────────────────────

    def test_empty_orchestrator_url_raises(self):
        assert self._fail_code(orchestrator_url="") == "mcp_write_requires_orchestrator"

    def test_none_orchestrator_url_raises(self):
        assert self._fail_code(orchestrator_url=None) == "mcp_write_requires_orchestrator"

    # ── 실패: actor 없음 ──────────────────────────────────────────────

    def test_empty_actor_raises(self):
        assert self._fail_code(actor="") == "mcp_write_missing_actor"

    def test_whitespace_actor_raises(self):
        assert self._fail_code(actor="   ") == "mcp_write_missing_actor"

    def test_none_actor_raises(self):
        assert self._fail_code(actor=None) == "mcp_write_missing_actor"

    # ── 실패: task_id 없음 ────────────────────────────────────────────

    def test_empty_task_id_raises(self):
        assert self._fail_code(task_id="") == "mcp_write_requires_task_id"

    def test_none_task_id_raises(self):
        assert self._fail_code(task_id=None) == "mcp_write_requires_task_id"

    # ── 실패: approval_token 없음 ─────────────────────────────────────

    def test_empty_approval_token_raises(self):
        assert self._fail_code(approval_token="") == "mcp_write_requires_approval"

    def test_none_approval_token_raises(self):
        assert self._fail_code(approval_token=None) == "mcp_write_requires_approval"

    # ── 에러 순서 (allow_direct_write 가 가장 먼저) ────────────────────

    def test_direct_forbidden_checked_before_other_conditions(self):
        """allow_direct_write=True 면 다른 조건 이전에 차단."""
        code = self._fail_code(
            allow_direct_write=True,
            orchestrator_url="",
            actor="",
        )
        assert code == "mcp_write_direct_forbidden"

    # ── McpWriteError 속성 ────────────────────────────────────────────

    def test_error_has_error_code_and_detail(self):
        from mcp_server.write_guard import McpWriteError

        with pytest.raises(McpWriteError) as exc_info:
            self._ok(actor="")
        err = exc_info.value
        assert hasattr(err, "error_code")
        assert hasattr(err, "detail")
        assert err.detail


# ═════════════════════════════════════════════════════════════════════
# config — MCP_ALLOW_DIRECT_WRITE 하드락
# ═════════════════════════════════════════════════════════════════════


class TestConfigHardLock:
    """MCP_ALLOW_DIRECT_WRITE 는 env 로 변경 불가."""

    def test_direct_write_is_always_false(self):
        import mcp_server.config as cfg

        assert cfg.MCP_ALLOW_DIRECT_WRITE is False

    def test_env_cannot_set_direct_write_to_true(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOW_DIRECT_WRITE", "true")
        import mcp_server.config as cfg

        importlib.reload(cfg)
        assert cfg.MCP_ALLOW_DIRECT_WRITE is False, "MCP_ALLOW_DIRECT_WRITE must always be False regardless of env"

    def test_require_approval_is_always_true(self):
        import mcp_server.config as cfg

        assert cfg.MCP_REQUIRE_APPROVAL_FOR_WRITE is True

    def test_orchestrator_url_default(self):
        import mcp_server.config as cfg

        assert "8400" in cfg.ORCHESTRATOR_URL or "orchestrator" in cfg.ORCHESTRATOR_URL

    def test_cad_backend_url_no_trailing_slash(self):
        import mcp_server.config as cfg

        assert not cfg.CAD_BACKEND_URL.endswith("/")

    def test_orchestrator_url_no_trailing_slash(self):
        import mcp_server.config as cfg

        assert not cfg.ORCHESTRATOR_URL.endswith("/")


# ═════════════════════════════════════════════════════════════════════
# upstream — call_cad_read
# ═════════════════════════════════════════════════════════════════════


class TestCallCadRead:
    """call_cad_read: cad-backend 직통 조회."""

    def _make_mock_response(self, status=200, data=None):
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = data or {"items": []}
        return mock_resp

    def test_read_calls_cad_backend_url(self, monkeypatch):
        import mcp_server.config as cfg

        importlib.reload(cfg)

        captured_urls = []

        mock_resp = self._make_mock_response()
        mock_get = AsyncMock(
            return_value=mock_resp, side_effect=lambda url, **kw: captured_urls.append(url) or mock_resp
        )

        with patch("httpx.AsyncClient.get", mock_get):
            import mcp_server.upstream as up

            importlib.reload(up)
            _run(up.call_cad_read("projects"))

        assert any("cad-backend:8000" in u for u in captured_urls), (
            f"read 는 cad-backend 로 가야 함. captured={captured_urls}"
        )
        assert not any("orchestrator" in u for u in captured_urls), "read 는 orchestrator 를 거치지 않아야 함"

    def test_read_blocked_when_direct_read_disabled(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOW_DIRECT_READ", "false")
        import mcp_server.config as cfg

        importlib.reload(cfg)
        import mcp_server.upstream as up

        importlib.reload(up)

        with pytest.raises(RuntimeError, match="MCP_ALLOW_DIRECT_READ"):
            _run(up.call_cad_read("projects"))

    def test_read_does_not_require_approval(self):
        """read 는 approval 없이 호출 가능 — 파라미터 자체가 없음."""
        from mcp_server.upstream import call_cad_read

        sig = inspect.signature(call_cad_read)
        param_names = list(sig.parameters.keys())
        assert "approval_token" not in param_names, "read 도구는 approval_token 파라미터를 가지면 안 됨"
        assert "actor" not in param_names, "read 도구는 actor 파라미터를 가지면 안 됨"

    def test_read_success_returns_dict(self, monkeypatch):
        import mcp_server.config as cfg

        importlib.reload(cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"projects": ["p1"]}
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient.get", mock_get):
            import mcp_server.upstream as up

            importlib.reload(up)
            result = _run(up.call_cad_read("projects"))

        assert result == {"projects": ["p1"]}


# ═════════════════════════════════════════════════════════════════════
# upstream — call_cad_write_via_orchestrator
# ═════════════════════════════════════════════════════════════════════


class TestCallCadWriteViaOrchestrator:
    """call_cad_write_via_orchestrator: orchestrator 경유 write."""

    _VALID_KWARGS = dict(
        actor="jay",
        task_id="task-abc",
        approval_token="tok-xyz",  # noqa: S106
        body={"name": "test-proj"},
    )

    def _make_mock_response(self, status=201, data=None):
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.is_success = True
        mock_resp.content = b'{"id": "new"}'
        mock_resp.json.return_value = data or {"id": "new"}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_write_uses_orchestrator_url_not_cad_backend(self, monkeypatch):
        monkeypatch.setenv("CAD_BACKEND_URL", "http://cad-backend:8000")
        monkeypatch.setenv("ORCHESTRATOR_URL", "http://orchestrator:8400")
        import mcp_server.config as cfg

        importlib.reload(cfg)

        captured_urls = []
        mock_resp = self._make_mock_response()

        async def capture_request(self, method, url, **kwargs):
            captured_urls.append(url)
            return mock_resp

        with patch("httpx.AsyncClient.request", capture_request):
            import mcp_server.upstream as up

            importlib.reload(up)
            _run(up.call_cad_write_via_orchestrator("projects", "POST", **self._VALID_KWARGS))

        assert captured_urls, "HTTP 호출이 발생해야 함"
        assert all("orchestrator:8400" in u for u in captured_urls), (
            f"write 는 반드시 orchestrator 로 가야 함. got={captured_urls}"
        )
        assert not any("cad-backend" in u for u in captured_urls), "write 에서 cad-backend URL 참조 금지"

    def test_write_sends_approval_headers(self, monkeypatch):
        import mcp_server.config as cfg

        importlib.reload(cfg)

        captured_headers = []
        mock_resp = self._make_mock_response()

        async def capture_request(self, method, url, headers=None, **kwargs):
            captured_headers.append(dict(headers or {}))
            return mock_resp

        with patch("httpx.AsyncClient.request", capture_request):
            import mcp_server.upstream as up

            importlib.reload(up)
            _run(up.call_cad_write_via_orchestrator("projects", "POST", **self._VALID_KWARGS))

        assert captured_headers, "HTTP 호출이 발생해야 함"
        h = captured_headers[0]
        assert h.get("X-Task-Id") == "task-abc", f"X-Task-Id 헤더 필요. got={h}"
        assert h.get("X-Approval-Token-Id") == "tok-xyz", f"X-Approval-Token-Id 헤더 필요. got={h}"

    def test_write_blocked_without_orchestrator_url(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRATOR_URL", "")
        import mcp_server.config as cfg

        importlib.reload(cfg)
        import mcp_server.upstream as up

        importlib.reload(up)
        from mcp_server.write_guard import McpWriteError

        with pytest.raises(McpWriteError) as exc:
            _run(up.call_cad_write_via_orchestrator("projects", "POST", **self._VALID_KWARGS))
        assert exc.value.error_code == "mcp_write_requires_orchestrator"

    def test_write_blocked_without_actor(self, monkeypatch):
        import mcp_server.config as cfg

        importlib.reload(cfg)
        import mcp_server.upstream as up

        importlib.reload(up)
        from mcp_server.write_guard import McpWriteError

        kw = {**self._VALID_KWARGS, "actor": ""}
        with pytest.raises(McpWriteError) as exc:
            _run(up.call_cad_write_via_orchestrator("projects", "POST", **kw))
        assert exc.value.error_code == "mcp_write_missing_actor"

    def test_write_blocked_without_task_id(self, monkeypatch):
        import mcp_server.config as cfg

        importlib.reload(cfg)
        import mcp_server.upstream as up

        importlib.reload(up)
        from mcp_server.write_guard import McpWriteError

        kw = {**self._VALID_KWARGS, "task_id": ""}
        with pytest.raises(McpWriteError) as exc:
            _run(up.call_cad_write_via_orchestrator("projects", "POST", **kw))
        assert exc.value.error_code == "mcp_write_requires_task_id"

    def test_write_blocked_without_approval_token(self, monkeypatch):
        import mcp_server.config as cfg

        importlib.reload(cfg)
        import mcp_server.upstream as up

        importlib.reload(up)
        from mcp_server.write_guard import McpWriteError

        kw = {**self._VALID_KWARGS, "approval_token": ""}
        with pytest.raises(McpWriteError) as exc:
            _run(up.call_cad_write_via_orchestrator("projects", "POST", **kw))
        assert exc.value.error_code == "mcp_write_requires_approval"

    def test_write_upstream_path_constructed_correctly(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRATOR_URL", "http://orch:8400")
        import mcp_server.config as cfg

        importlib.reload(cfg)

        captured_urls = []
        mock_resp = self._make_mock_response()

        async def capture_request(self, method, url, **kwargs):
            captured_urls.append(url)
            return mock_resp

        with patch("httpx.AsyncClient.request", capture_request):
            import mcp_server.upstream as up

            importlib.reload(up)
            _run(up.call_cad_write_via_orchestrator("projects/proj-1", "PATCH", **self._VALID_KWARGS))

        assert captured_urls
        assert captured_urls[0] == "http://orch:8400/api/v1/cad/projects/proj-1", f"URL 구조 불일치: {captured_urls[0]}"

    def test_write_success_with_all_params(self, monkeypatch):
        """모든 조건 충족 시 성공 반환 + orchestrator 로 전달."""
        import mcp_server.config as cfg

        importlib.reload(cfg)

        mock_resp = self._make_mock_response(data={"id": "proj-999"})

        async def mock_request(self, method, url, **kwargs):
            return mock_resp

        with patch("httpx.AsyncClient.request", mock_request):
            import mcp_server.upstream as up

            importlib.reload(up)
            result = _run(up.call_cad_write_via_orchestrator("projects", "POST", **self._VALID_KWARGS))

        assert result == {"id": "proj-999"}


# ═════════════════════════════════════════════════════════════════════
# 보안: 구조적 가드
# ═════════════════════════════════════════════════════════════════════


class TestSecurityGuards:
    """코드 구조 수준의 보안 불변 검증."""

    def test_upstream_write_function_never_references_cad_backend_config(self):
        """write 헬퍼 소스코드에 CAD_BACKEND_URL config 참조 없음."""
        from mcp_server import upstream

        source = inspect.getsource(upstream.call_cad_write_via_orchestrator)
        assert "CAD_BACKEND_URL" not in source, "write 헬퍼 내부에 CAD_BACKEND_URL config 참조 금지"

    def test_upstream_write_function_uses_orchestrator_url(self):
        """write 헬퍼 소스코드에 orchestrator_url 참조 확인."""
        from mcp_server import upstream

        source = inspect.getsource(upstream.call_cad_write_via_orchestrator)
        assert "ORCHESTRATOR_URL" in source or "orchestrator_url" in source, (
            "write 헬퍼는 orchestrator_url 을 참조해야 함"
        )

    def test_mcp_allow_direct_write_hardcoded_false_in_config_source(self):
        """config.py 소스에 False 하드코딩 확인."""
        from mcp_server import config

        source = inspect.getsource(config)
        assert "MCP_ALLOW_DIRECT_WRITE: bool = False" in source, (
            "MCP_ALLOW_DIRECT_WRITE 는 소스에 False 로 하드코딩되어야 함"
        )

    def test_write_guard_has_allow_direct_write_check(self):
        """write_guard.py 에서 allow_direct_write 검사 로직 존재."""
        from mcp_server import write_guard

        source = inspect.getsource(write_guard.check_write_prerequisites)
        assert "allow_direct_write" in source
        assert "mcp_write_direct_forbidden" in source

    def test_cad_backend_port_not_in_mcp_actor_header(self):
        """MCP_ACTOR_HEADER 가 cad-backend 포트 주소를 포함하지 않음."""
        from mcp_server import config

        assert "8000" not in config.MCP_ACTOR_HEADER
        assert "cad-backend" not in config.MCP_ACTOR_HEADER


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
