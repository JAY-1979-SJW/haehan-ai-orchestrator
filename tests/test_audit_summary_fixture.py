"""Stage 13C-2: audit_summary sanitize 테스트 (43 tests).

PC local audit.jsonl 원문은 절대 저장/반환하지 않는다.
audit_summary는 allowlist 방식으로 필드를 필터링한다.
"""

from ai_orchestrator.agent_hub.registry import facade as reg


class TestAuditSummaryBasic:
    """기본 audit_summary 동작"""

    def setup_method(self):
        reg.clear()

    def _setup_running_task(self):
        """running 상태의 task 생성"""
        agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
        task = reg.enqueue_task(
            agent_id=agent.agent.agent_id,
            action="open_url",
            params={"url": "http://127.0.0.1:8000"},
            requested_by="test",
        )
        reg.mark_delivered(agent.agent.agent_id, task.task_id)
        reg.mark_running(agent.agent.agent_id, task.task_id)
        return agent.agent.agent_id, task.task_id

    def test_task_without_audit_summary_completes(self):
        """audit_summary가 없으면 task가 정상 완료"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(agent_id=agent_id, task_id=task_id, success=True, summary="ok", audit_summary=None)
        assert result is not None
        assert result.status == "completed"
        assert result.audit_summary is None

    def test_audit_summary_with_allowed_fields(self):
        """허용 필드만 저장"""
        agent_id, task_id = self._setup_running_task()
        audit_data = {
            "audit_event_count": 5,
            "blocked_event_count": 1,
            "allowed_event_count": 4,
        }
        result = reg.apply_result(
            agent_id=agent_id, task_id=task_id, success=True, summary="ok", audit_summary=audit_data
        )
        assert result is not None
        assert result.audit_summary is not None
        assert result.audit_summary["audit_event_count"] == 5
        assert result.audit_summary["blocked_event_count"] == 1
        assert result.audit_summary["allowed_event_count"] == 4

    def test_audit_summary_invalid_type_ignored(self):
        """audit_summary이 dict이 아니면 무시"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id, task_id=task_id, success=True, summary="ok", audit_summary="not_a_dict"
        )
        assert result is not None
        assert result.audit_summary is None

    def test_audit_summary_in_failed_task(self):
        """실패한 task에서도 audit_summary 저장 가능"""
        agent_id, task_id = self._setup_running_task()
        audit_data = {"audit_event_count": 3, "error_event_count": 1}
        result = reg.apply_result(
            agent_id=agent_id, task_id=task_id, success=False, error="timeout", audit_summary=audit_data
        )
        assert result is not None
        assert result.status == "failed"
        assert result.audit_summary is not None
        assert result.audit_summary["audit_event_count"] == 3


class TestAuditSummaryCountFields:
    """Count 필드 검증"""

    def setup_method(self):
        reg.clear()

    def _setup_running_task(self):
        agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
        task = reg.enqueue_task(
            agent_id=agent.agent.agent_id,
            action="open_url",
            params={"url": "http://127.0.0.1:8000"},
            requested_by="test",
        )
        reg.mark_delivered(agent.agent.agent_id, task.task_id)
        reg.mark_running(agent.agent.agent_id, task.task_id)
        return agent.agent.agent_id, task.task_id

    def test_count_accepts_int(self):
        """Count 필드는 int 허용"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id, task_id=task_id, success=True, summary="ok", audit_summary={"audit_event_count": 42}
        )
        assert result.audit_summary["audit_event_count"] == 42

    def test_count_converts_negative_to_zero(self):
        """음수 count는 0으로 변환"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id, task_id=task_id, success=True, summary="ok", audit_summary={"audit_event_count": -5}
        )
        assert result.audit_summary["audit_event_count"] == 0

    def test_count_converts_string_int(self):
        """문자열 int 변환"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id, task_id=task_id, success=True, summary="ok", audit_summary={"audit_event_count": "42"}
        )
        assert result.audit_summary["audit_event_count"] == 42

    def test_count_drops_invalid_string(self):
        """변환 불가능한 문자열은 drop"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_count": "invalid"},
        )
        # 모든 필드가 drop되면 audit_summary는 None
        assert result.audit_summary is None or "audit_event_count" not in result.audit_summary


class TestAuditSummaryStringFields:
    """String enum 필드 검증"""

    def setup_method(self):
        reg.clear()

    def _setup_running_task(self):
        agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
        task = reg.enqueue_task(
            agent_id=agent.agent.agent_id,
            action="open_url",
            params={"url": "http://127.0.0.1:8000"},
            requested_by="test",
        )
        reg.mark_delivered(agent.agent.agent_id, task.task_id)
        reg.mark_running(agent.agent.agent_id, task.task_id)
        return agent.agent.agent_id, task.task_id

    def test_string_length_limited(self):
        """String 필드 최대 길이 제한"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"last_event_category": "a" * 200},
        )
        assert len(result.audit_summary["last_event_category"]) == 80

    def test_string_enum_stored(self):
        """Enum 문자열 저장"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id, task_id=task_id, success=True, summary="ok", audit_summary={"last_event_status": "ok"}
        )
        assert result.audit_summary["last_event_status"] == "ok"


class TestAuditSummaryListFields:
    """List 필드 검증"""

    def setup_method(self):
        reg.clear()

    def _setup_running_task(self):
        agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
        task = reg.enqueue_task(
            agent_id=agent.agent.agent_id,
            action="open_url",
            params={"url": "http://127.0.0.1:8000"},
            requested_by="test",
        )
        reg.mark_delivered(agent.agent.agent_id, task.task_id)
        reg.mark_running(agent.agent.agent_id, task.task_id)
        return agent.agent.agent_id, task.task_id

    def test_event_categories_list_stored(self):
        """audit_event_categories list 저장"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_categories": ["browser_open_requested", "browser_open_observed"]},
        )
        assert len(result.audit_summary["audit_event_categories"]) == 2

    def test_event_categories_duplicate_removed(self):
        """중복 카테고리 제거"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_categories": ["browser_open_requested", "browser_open_requested"]},
        )
        assert len(result.audit_summary["audit_event_categories"]) == 1

    def test_event_categories_invalid_type_dropped(self):
        """list가 아니면 drop"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_categories": "not_a_list"},
        )
        assert result.audit_summary is None or "audit_event_categories" not in result.audit_summary


class TestAuditSummaryDictFields:
    """Dict count 필드 검증"""

    def setup_method(self):
        reg.clear()

    def _setup_running_task(self):
        agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
        task = reg.enqueue_task(
            agent_id=agent.agent.agent_id,
            action="open_url",
            params={"url": "http://127.0.0.1:8000"},
            requested_by="test",
        )
        reg.mark_delivered(agent.agent.agent_id, task.task_id)
        reg.mark_running(agent.agent.agent_id, task.task_id)
        return agent.agent.agent_id, task.task_id

    def test_count_dict_stored(self):
        """Count dict 저장"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"policy_decision_counts": {"blocked": 2, "allowed": 3}},
        )
        assert result.audit_summary["policy_decision_counts"]["blocked"] == 2

    def test_count_dict_invalid_type_dropped(self):
        """dict가 아니면 drop"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"policy_decision_counts": "not_a_dict"},
        )
        assert result.audit_summary is None or "policy_decision_counts" not in result.audit_summary

    def test_count_dict_nested_invalid(self):
        """Nested dict는 허용 안 함"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"policy_decision_counts": {"category": {"nested": 1}}},
        )
        assert result.audit_summary is None or "category" not in result.audit_summary.get("policy_decision_counts", {})


class TestAuditSummaryForbiddenFields:
    """금지 필드 차단"""

    def setup_method(self):
        reg.clear()

    def _setup_running_task(self):
        agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
        task = reg.enqueue_task(
            agent_id=agent.agent.agent_id,
            action="open_url",
            params={"url": "http://127.0.0.1:8000"},
            requested_by="test",
        )
        reg.mark_delivered(agent.agent.agent_id, task.task_id)
        reg.mark_running(agent.agent.agent_id, task.task_id)
        return agent.agent.agent_id, task.task_id

    def test_raw_events_dropped(self):
        """raw_events 필드 차단"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_count": 5, "raw_events": [{"event_type": "test"}]},
        )
        assert "raw_events" not in result.audit_summary

    def test_current_url_dropped(self):
        """current_url 필드 차단"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_count": 5, "current_url": "http://example.com"},
        )
        assert "current_url" not in result.audit_summary

    def test_url_query_fragment_dropped(self):
        """url/query/fragment 필드 차단"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={
                "audit_event_count": 5,
                "url": "http://example.com",
                "query": "key=value",
                "fragment": "section",
            },
        )
        assert "url" not in result.audit_summary
        assert "query" not in result.audit_summary
        assert "fragment" not in result.audit_summary

    def test_html_body_dropped(self):
        """html/body 필드 차단"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_count": 5, "html": "<html>content</html>", "body": "page content"},
        )
        assert "html" not in result.audit_summary
        assert "body" not in result.audit_summary

    def test_text_dropped(self):
        """text/page_text 필드 차단"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_count": 5, "text": "page text", "page_text": "full content"},
        )
        assert "text" not in result.audit_summary
        assert "page_text" not in result.audit_summary

    def test_selector_dropped(self):
        """selector 필드 차단"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_count": 5, "selector": ".button.submit"},
        )
        assert "selector" not in result.audit_summary

    def test_cookie_session_token_dropped(self):
        """cookie/session/token 필드 차단"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_count": 5, "cookie": "session=abc", "session": "xyz789", "token": "auth_token"},
        )
        assert "cookie" not in result.audit_summary
        assert "session" not in result.audit_summary
        assert "token" not in result.audit_summary

    def test_password_authorization_dropped(self):
        """password/authorization 필드 차단"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_count": 5, "password": "secret123", "authorization": "Bearer xyz"},
        )
        assert "password" not in result.audit_summary
        assert "authorization" not in result.audit_summary

    def test_path_local_file_path_dropped(self):
        """path/local_file_path 필드 차단"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={
                "audit_event_count": 5,
                "path": "/home/user/file.txt",
                "local_file_path": "C:\\Users\\test\\audit.jsonl",
            },
        )
        assert "path" not in result.audit_summary
        assert "local_file_path" not in result.audit_summary

    def test_headers_body_dropped(self):
        """headers/request_body/response_body 필드 차단"""
        agent_id, task_id = self._setup_running_task()
        result = reg.apply_result(
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            summary="ok",
            audit_summary={
                "audit_event_count": 5,
                "headers": {"Authorization": "Bearer token"},
                "request_body": '{"key": "value"}',
                "response_body": "response content",
            },
        )
        assert "headers" not in result.audit_summary
        assert "request_body" not in result.audit_summary
        assert "response_body" not in result.audit_summary


class TestAuditSummaryTaskDetail:
    """Task detail API에서 audit_summary 반환"""

    def setup_method(self):
        reg.clear()

    def test_task_detail_includes_audit_summary(self):
        """task detail to_safe()에 audit_summary 포함"""
        agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
        task = reg.enqueue_task(
            agent_id=agent.agent.agent_id,
            action="open_url",
            params={"url": "http://127.0.0.1:8000"},
            requested_by="test",
        )
        reg.mark_delivered(agent.agent.agent_id, task.task_id)
        reg.mark_running(agent.agent.agent_id, task.task_id)

        result = reg.apply_result(
            agent_id=agent.agent.agent_id,
            task_id=task.task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_count": 5},
        )

        safe_dict = result.to_safe()
        assert "audit_summary" in safe_dict
        assert safe_dict["audit_summary"] is not None

    def test_task_detail_audit_summary_optional(self):
        """audit_summary 없으면 null 반환"""
        agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
        task = reg.enqueue_task(
            agent_id=agent.agent.agent_id,
            action="open_url",
            params={"url": "http://127.0.0.1:8000"},
            requested_by="test",
        )
        reg.mark_delivered(agent.agent.agent_id, task.task_id)
        reg.mark_running(agent.agent.agent_id, task.task_id)

        result = reg.apply_result(
            agent_id=agent.agent.agent_id, task_id=task.task_id, success=True, summary="ok", audit_summary=None
        )

        safe_dict = result.to_safe()
        assert safe_dict["audit_summary"] is None

    def test_task_list_does_not_include_audit_summary(self):
        """task list to_list_safe()에 audit_summary 미포함"""
        agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
        task = reg.enqueue_task(
            agent_id=agent.agent.agent_id,
            action="open_url",
            params={"url": "http://127.0.0.1:8000"},
            requested_by="test",
        )
        reg.mark_delivered(agent.agent.agent_id, task.task_id)
        reg.mark_running(agent.agent.agent_id, task.task_id)

        result = reg.apply_result(
            agent_id=agent.agent.agent_id,
            task_id=task.task_id,
            success=True,
            summary="ok",
            audit_summary={"audit_event_count": 5},
        )

        list_dict = result.to_list_safe()
        assert "audit_summary" not in list_dict


class TestAuditSummaryObserveSummaryCoexistence:
    """audit_summary와 observe_summary 동시 저장"""

    def setup_method(self):
        reg.clear()

    def test_both_audit_and_observe_stored(self):
        """audit_summary와 observe_summary 모두 저장 가능"""
        agent = reg.register_agent(host="test", os_name="Windows", version="1.0", requested_by="test")
        task = reg.enqueue_task(
            agent_id=agent.agent.agent_id,
            action="open_url",
            params={"url": "http://127.0.0.1:8000"},
            requested_by="test",
        )
        reg.mark_delivered(agent.agent.agent_id, task.task_id)
        reg.mark_running(agent.agent.agent_id, task.task_id)

        observe_data = {
            "url_category": "internal_test",
            "status_category": "ok",
            "pages_observed_count": 1,
        }
        audit_data = {
            "audit_event_count": 5,
            "blocked_event_count": 0,
        }

        result = reg.apply_result(
            agent_id=agent.agent.agent_id,
            task_id=task.task_id,
            success=True,
            summary="ok",
            observe_summary=observe_data,
            audit_summary=audit_data,
        )

        assert result.observe_summary is not None
        assert result.audit_summary is not None
        assert result.observe_summary["url_category"] == "internal_test"
        assert result.audit_summary["audit_event_count"] == 5


class TestLocalAgentAuditSummaryBuilder:
    """Local-agent _build_audit_summary() helper 테스트"""

    def test_audit_summary_ok_status(self):
        """OK 상태 audit_summary 생성"""
        from core.agent_runtime.connection import actions

        result = actions._build_audit_summary("about_blank", "ok")

        assert result["audit_event_count"] == 1
        assert result["allowed_event_count"] == 1
        assert result["blocked_event_count"] == 0
        assert result["last_event_status"] == "ok"
        assert result["policy_decision_counts"]["allowed"] == 1

    def test_audit_summary_blocked_status(self):
        """Blocked 상태 audit_summary 생성"""
        from core.agent_runtime.connection import actions

        result = actions._build_audit_summary("public_https", "blocked")

        assert result["audit_event_count"] == 1
        assert result["blocked_event_count"] == 1
        assert result["allowed_event_count"] == 0
        assert result["last_event_status"] == "blocked"
        assert result["policy_decision_counts"]["blocked"] == 1

    def test_audit_summary_error_status(self):
        """Error 상태 audit_summary 생성"""
        from core.agent_runtime.connection import actions

        result = actions._build_audit_summary("internal_test", "error", "TIMEOUT")

        assert result["audit_event_count"] == 1
        assert result["error_event_count"] == 1
        assert result["last_event_status"].startswith("error:")
        assert "TIMEOUT" in result["last_event_status"]

    def test_audit_summary_denied_status(self):
        """Denied 상태 audit_summary 생성"""
        from core.agent_runtime.connection import actions

        result = actions._build_audit_summary("about_blank", "denied")

        assert result["denied_event_count"] == 1
        assert result["policy_decision_counts"]["denied"] == 1

    def test_audit_summary_has_required_fields(self):
        """Required 필드 포함 확인"""
        from core.agent_runtime.connection import actions

        result = actions._build_audit_summary("about_blank", "ok")

        assert "audit_schema_version" in result
        assert "local_audit_source" in result
        assert "audit_summary_generated_at" in result
        assert "audit_event_count" in result
        assert "last_event_category" in result
        assert "audit_event_categories" in result
        assert "target_kind_counts" in result
        assert "action_kind_counts" in result

    def test_audit_summary_no_forbidden_fields(self):
        """금지 필드 미포함 확인"""
        from core.agent_runtime.connection import actions

        result = actions._build_audit_summary("about_blank", "ok")

        forbidden = [
            "raw_events",
            "events",
            "current_url",
            "url",
            "query",
            "html",
            "text",
            "selector",
            "cookie",
            "session",
            "token",
            "password",
            "authorization",
            "path",
        ]

        for field in forbidden:
            assert field not in result

    def test_audit_summary_target_kind_counts(self):
        """Target kind counts 반영"""
        from core.agent_runtime.connection import actions

        result = actions._build_audit_summary("public_http", "ok")

        assert "target_kind_counts" in result
        assert result["target_kind_counts"]["public_http"] == 1

    def test_audit_summary_timestamp_format(self):
        """Timestamp ISO 형식 확인"""
        from core.agent_runtime.connection import actions

        result = actions._build_audit_summary("about_blank", "ok")
        timestamp = result["audit_summary_generated_at"]

        # ISO 8601 형식 (간단한 검증)
        assert "T" in timestamp
        assert "+" in timestamp or "Z" in timestamp


class TestActionWebOpenUrlReadonlyAuditSummary:
    """action_web_open_url_readonly에서 audit_summary 포함 확인"""

    def test_action_result_includes_audit_summary(self):
        """ActionResult data에 audit_summary 포함"""
        from unittest.mock import patch

        from core.agent_runtime.connection import actions

        with patch("core.agent_runtime.browser.browser_reader.open_url_readonly") as mock_open:
            mock_open.return_value = {
                "ok": True,
                "url": "http://127.0.0.1:8000",
                "current_url": "http://127.0.0.1:8000",
                "title": "Test Page",
                "url_category": "internal_test",
                "html_truncated": False,
                "login_required_hint": False,
                "login_reason": [],
                "modal_candidates": [],
                "page_structure": {"counts": {}},
                "summary": "ok",
            }

            result = actions.action_web_open_url_readonly({"url": "http://127.0.0.1:8000"})

            assert result.success is True
            assert "audit_summary" in result.data
            assert result.data["audit_summary"] is not None

    def test_audit_summary_and_observe_summary_separate(self):
        """audit_summary와 observe_summary 분리 확인"""
        from unittest.mock import patch

        from core.agent_runtime.connection import actions

        with patch("core.agent_runtime.browser.browser_reader.open_url_readonly") as mock_open:
            mock_open.return_value = {
                "ok": True,
                "url": "http://127.0.0.1:8000",
                "current_url": "http://127.0.0.1:8000",
                "title": "Test Page",
                "url_category": "internal_test",
                "html_truncated": False,
                "login_required_hint": False,
                "login_reason": [],
                "modal_candidates": [],
                "page_structure": {"counts": {}},
                "summary": "ok",
            }

            result = actions.action_web_open_url_readonly({"url": "http://127.0.0.1:8000"})

            assert "observe_summary" in result.data
            assert "audit_summary" in result.data
            assert result.data["observe_summary"] != result.data["audit_summary"]
            # observe_summary는 page 정보 포함
            assert "title" in result.data["observe_summary"]
            # audit_summary는 counts만 포함
            assert "audit_event_count" in result.data["audit_summary"]
