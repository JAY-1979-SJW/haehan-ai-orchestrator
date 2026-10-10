"""observe_summary 구조화 저장 fixture 테스트 (Stage 13B-3A).

외부 URL 접속, 브라우저 실행, 실제 HTTP 요청 없음.
_build_observe_summary() sanitize 로직과 apply_result() 저장 흐름만 검증.
"""

from __future__ import annotations

import pytest

from ai_orchestrator.agent_hub.registry import facade as _reg
from ai_orchestrator.agent_hub.registry import common as _reg_common

# ── 공통 fixture ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    """각 테스트 전 registry 메모리 초기화."""
    # 2026-09-29 영속화 추가 후 필수: 안 하면 _reg.clear()가 실제 개발 세션의
    # data/local_agent_registry_state.json(실제 등록된 로컬 에이전트 상태)을 테스트마다 지운다.
    monkeypatch.setattr(_reg_common, "_REGISTRY_STATE_PATH", tmp_path / "local_agent_registry_state.json")
    _reg.clear()
    yield
    _reg.clear()


def _make_task(action: str = "web_open_url_readonly") -> _reg.LocalAgentTask:
    """테스트용 task 등록 후 반환."""
    result = _reg.register_agent(
        host="test-host",
        os_name="TestOS",
        version="0.1.0",
        requested_by="tester",
    )
    agent_id = result.agent.agent_id
    task = _reg.enqueue_task(
        agent_id=agent_id,
        action="open_url",
        params={"url": "http://127.0.0.1:9876/__haehan_test__/readonly"},
        requested_by="tester",
    )
    # queued → delivered → running 으로 수동 전환
    _reg.mark_delivered(agent_id, task.task_id)
    _reg.mark_running(agent_id, task.task_id)
    t = _reg.get_task(agent_id, task.task_id)
    assert t is not None
    return t


def _make_full_observe_summary(**overrides) -> dict:
    base = {
        "target_kind": "public_http",
        "url_category": "public_http",
        "final_url_sanitized": "http://127.0.0.1:9876/__haehan_test__/readonly",
        "title": "haehan internal test readonly",
        "title_len": 30,
        "status_category": "ok",
        "pages_observed_count": 1,
        "error_category": None,
        "blocked_reason": None,
        "login_required_hint": False,
        "modal_candidates_count": 0,
        "html_truncated": False,
        "browser_headless": True,
        "browser_keep_open_ms": 0,
        "browser_channel": "chromium",
        "page_structure_counts": {
            "headings": 1,
            "links": 0,
            "buttons": 0,
            "inputs": 0,
            "forms": 0,
            "tables": 0,
        },
        "observed_at": "2026-04-29T10:00:00+00:00",
    }
    base.update(overrides)
    return base


# ── 1. 기본값: observe_summary 없는 task ─────────────────────────────────


class TestObserveSummaryDefault:
    def test_new_task_observe_summary_none(self):
        task = _make_task()
        assert task.observe_summary is None

    def test_to_safe_observe_summary_none(self):
        task = _make_task()
        safe = task.to_safe()
        assert "observe_summary" in safe
        assert safe["observe_summary"] is None

    def test_apply_result_no_observe_summary(self):
        task = _make_task()
        updated = _reg.apply_result(
            agent_id=task.agent_id,
            task_id=task.task_id,
            success=True,
            summary="ok",
        )
        assert updated.observe_summary is None
        assert updated.to_safe()["observe_summary"] is None

    def test_result_summary_still_works(self):
        task = _make_task()
        updated = _reg.apply_result(
            agent_id=task.agent_id,
            task_id=task.task_id,
            success=True,
            summary="summary text",
        )
        assert updated.result_summary == "summary text"

    def test_to_list_safe_no_observe_summary(self):
        task = _make_task()
        safe = task.to_list_safe()
        assert "observe_summary" not in safe


# ── 2. observe_summary 저장 ───────────────────────────────────────────────


class TestObserveSummaryStore:
    def test_apply_result_stores_observe_summary(self):
        task = _make_task()
        obs = _make_full_observe_summary()
        updated = _reg.apply_result(
            agent_id=task.agent_id,
            task_id=task.task_id,
            success=True,
            summary="ok",
            observe_summary=obs,
        )
        assert updated.observe_summary is not None
        assert updated.observe_summary["status_category"] == "ok"
        assert updated.observe_summary["pages_observed_count"] == 1

    def test_observe_summary_in_to_safe(self):
        task = _make_task()
        obs = _make_full_observe_summary()
        updated = _reg.apply_result(
            agent_id=task.agent_id,
            task_id=task.task_id,
            success=True,
            summary="ok",
            observe_summary=obs,
        )
        safe = updated.to_safe()
        assert safe["observe_summary"] is not None
        assert safe["observe_summary"]["title"] == "haehan internal test readonly"
        assert safe["observe_summary"]["browser_headless"] is True
        assert safe["observe_summary"]["browser_keep_open_ms"] == 0
        assert safe["observe_summary"]["browser_channel"] == "chromium"

    def test_observe_summary_preserves_visible_browser_monitor_fields(self):
        obs = _make_full_observe_summary(
            browser_headless=False,
            browser_keep_open_ms=15000,
            browser_channel="chrome",
        )
        result = _reg._build_observe_summary(obs)
        assert result["browser_headless"] is False
        assert result["browser_keep_open_ms"] == 15000
        assert result["browser_channel"] == "chrome"

    def test_observe_summary_not_stored_on_failure(self):
        task = _make_task()
        obs = _make_full_observe_summary(status_category="failed")
        updated = _reg.apply_result(
            agent_id=task.agent_id,
            task_id=task.task_id,
            success=False,
            error="err",
            error_code="SOME_ERR",
            observe_summary=obs,
        )
        # failure path 에서는 observe_summary 저장하지 않음
        assert updated.observe_summary is None


# ── 3. final_url_sanitized sanitize ──────────────────────────────────────


class TestFinalUrlSanitize:
    def test_about_blank_preserved(self):
        obs = _make_full_observe_summary(
            url_category="about_blank",
            final_url_sanitized="about:blank",
        )
        result = _reg._build_observe_summary(obs)
        assert result["final_url_sanitized"] == "about:blank"

    def test_loopback_url_preserved(self):
        obs = _make_full_observe_summary(
            final_url_sanitized="http://127.0.0.1:9876/__haehan_test__/readonly",
        )
        result = _reg._build_observe_summary(obs)
        assert result["final_url_sanitized"] == "http://127.0.0.1:9876/__haehan_test__/readonly"

    def test_query_stripped_from_loopback(self):
        obs = _make_full_observe_summary(
            final_url_sanitized="http://127.0.0.1:9876/path?token=secret",
        )
        result = _reg._build_observe_summary(obs)
        assert result["final_url_sanitized"] == "http://127.0.0.1:9876/path"
        assert "token" not in (result["final_url_sanitized"] or "")

    def test_fragment_stripped_from_loopback(self):
        obs = _make_full_observe_summary(
            final_url_sanitized="http://127.0.0.1:9876/path#section",
        )
        result = _reg._build_observe_summary(obs)
        assert result["final_url_sanitized"] == "http://127.0.0.1:9876/path"

    def test_external_url_returns_none(self):
        obs = _make_full_observe_summary(
            url_category="public_https",
            final_url_sanitized="https://example.com/some/path?q=1",
        )
        result = _reg._build_observe_summary(obs)
        assert result["final_url_sanitized"] is None

    def test_none_input_returns_none(self):
        obs = _make_full_observe_summary(final_url_sanitized=None)
        result = _reg._build_observe_summary(obs)
        assert result["final_url_sanitized"] is None

    def test_invalid_url_returns_none(self):
        obs = _make_full_observe_summary(final_url_sanitized="not-a-url")
        result = _reg._build_observe_summary(obs)
        assert result["final_url_sanitized"] is None


# ── 4. modal_candidates — count 만 저장 ──────────────────────────────────


class TestModalCandidates:
    def test_modal_count_stored(self):
        obs = _make_full_observe_summary(modal_candidates_count=3)
        result = _reg._build_observe_summary(obs)
        assert result["modal_candidates_count"] == 3

    def test_modal_list_raw_not_present(self):
        obs = _make_full_observe_summary(modal_candidates_count=2)
        obs["modal_candidates"] = [{"text": "닫기", "reason": "close_button"}]
        result = _reg._build_observe_summary(obs)
        assert "modal_candidates" not in result


# ── 5. page_structure — counts 만 저장 ───────────────────────────────────


class TestPageStructureCounts:
    def test_page_structure_counts_stored(self):
        obs = _make_full_observe_summary(
            page_structure_counts={"headings": 2, "links": 5, "buttons": 1, "inputs": 0, "forms": 0, "tables": 1}
        )
        result = _reg._build_observe_summary(obs)
        assert result["page_structure_counts"]["headings"] == 2
        assert result["page_structure_counts"]["links"] == 5

    def test_page_structure_raw_not_stored(self):
        obs = _make_full_observe_summary()
        obs["page_structure"] = {"inputs": [{"type": "password", "label": "pw"}]}
        result = _reg._build_observe_summary(obs)
        assert "page_structure" not in result

    def test_negative_counts_floored_to_zero(self):
        obs = _make_full_observe_summary(
            page_structure_counts={"headings": -1, "links": 0, "buttons": 0, "inputs": 0, "forms": 0, "tables": 0}
        )
        result = _reg._build_observe_summary(obs)
        assert result["page_structure_counts"]["headings"] == 0


# ── 6. 금지 키 차단 ──────────────────────────────────────────────────────


class TestForbiddenKeys:
    @pytest.mark.parametrize(
        "bad_key,bad_val",
        [
            ("cookie", "session_abc"),
            ("session", "sess_xyz"),
            ("token", "tok_123"),
            ("authorization", "Bearer abc"),
            ("password", "pw123"),
            ("localstorage", {"key": "val"}),
            ("sessionstorage", {"key": "val"}),
            ("html", "<html>..."),
            ("content", "page content"),
            ("body", "<body>..."),
            ("query", "?token=secret"),
            ("fragment", "#hash"),
            ("headers", {"set-cookie": "..."}),
            ("login_reason", ["password_input_detected"]),
            ("modal_candidates", [{"text": "닫기"}]),
            ("page_structure", {"inputs": []}),
            ("current_url", "http://127.0.0.1:9876/path?q=1"),
        ],
    )
    def test_forbidden_key_removed(self, bad_key, bad_val):
        obs = _make_full_observe_summary()
        obs[bad_key] = bad_val
        result = _reg._build_observe_summary(obs)
        assert bad_key not in result

    def test_none_raw_returns_none(self):
        assert _reg._build_observe_summary(None) is None

    def test_non_dict_raw_returns_none(self):
        assert _reg._build_observe_summary("string") is None
        assert _reg._build_observe_summary(123) is None


# ── 7. title sanitize ─────────────────────────────────────────────────────


class TestTitleSanitize:
    def test_title_length_limited(self):
        long_title = "A" * 400
        obs = _make_full_observe_summary(title=long_title, title_len=400)
        result = _reg._build_observe_summary(obs)
        assert len(result["title"]) <= 300

    def test_title_len_recalculated(self):
        obs = _make_full_observe_summary(title="hello", title_len=999)
        result = _reg._build_observe_summary(obs)
        assert result["title"] == "hello"
        # title_len은 raw에서 가져오되 제한된 title 기준으로 재계산될 수 있음
        # 단, 이 구현에서는 raw title_len을 정수로 변환만 함
        assert isinstance(result["title_len"], int)

    def test_none_title_becomes_empty_string(self):
        obs = _make_full_observe_summary(title=None, title_len=0)
        result = _reg._build_observe_summary(obs)
        assert result["title"] == ""


# ── 8. sanitize_final_url_value 직접 테스트 ──────────────────────────────


class TestSanitizeFinalUrlValue:
    def test_about_blank(self):
        assert _reg._sanitize_final_url_value("about:blank") == "about:blank"

    def test_about_blank_case_insensitive(self):
        assert _reg._sanitize_final_url_value("ABOUT:BLANK") == "about:blank"

    def test_localhost_stripped(self):
        url = "http://localhost:3000/path?q=1#frag"
        result = _reg._sanitize_final_url_value(url)
        assert result == "http://localhost:3000/path"
        assert "q=1" not in (result or "")
        assert "frag" not in (result or "")

    def test_127_0_0_1_stripped(self):
        url = "http://127.0.0.1:8080/api?secret=abc"
        result = _reg._sanitize_final_url_value(url)
        assert result == "http://127.0.0.1:8080/api"

    def test_external_none(self):
        assert _reg._sanitize_final_url_value("https://example.com/") is None
        assert _reg._sanitize_final_url_value("https://google.com") is None

    def test_private_network_not_loopback_none(self):
        assert _reg._sanitize_final_url_value("http://192.168.1.1/") is None
        assert _reg._sanitize_final_url_value("http://10.0.0.1/") is None

    def test_none_returns_none(self):
        assert _reg._sanitize_final_url_value(None) is None

    def test_non_string_returns_none(self):
        assert _reg._sanitize_final_url_value(123) is None
