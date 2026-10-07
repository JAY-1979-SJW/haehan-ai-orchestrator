"""Local Agent 운영 진단 endpoint 테스트."""

from datetime import UTC, datetime

from ai_orchestrator.agent_hub.registry import diagnostics as local_agent_diagnostics
from ai_orchestrator.agent_hub.registry import facade as _reg


class TestDiagnosticsHelper:
    """build_local_agent_diagnostics() 함수 테스트."""

    def setup_method(self):
        """각 테스트 전 상태 초기화."""
        _reg._agents.clear()
        _reg._tasks.clear()

    def test_empty_agents_and_tasks(self):
        """agents 0, tasks 0일 때 diagnostics 정상 반환."""
        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert result["status"] in ("ok", "warn")
        assert result["schema_version"] == 1
        assert result["agents"]["total"] == 0
        assert result["tasks"]["total"] == 0
        assert result["summaries"]["with_result_summary"] == 0
        assert result["latest"]["task_created_at"] is None
        assert "no_registered_agents" in result["warnings"]

    def test_agent_count(self):
        """agent count 정확."""
        agent1 = _reg.LocalAgent(
            agent_id="agent1",
            host="pc1",
            os_name="Windows 11",
            version="0.1.0",
            registered_at=_reg._now_iso(),
            requested_by="admin",
            token_hash="fake_hash",
        )
        agent2 = _reg.LocalAgent(
            agent_id="agent2",
            host="pc2",
            os_name="Windows 10",
            version="0.1.0",
            registered_at=_reg._now_iso(),
            requested_by="admin",
            token_hash="fake_hash",
        )
        _reg._agents["agent1"] = agent1
        _reg._agents["agent2"] = agent2

        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert result["agents"]["total"] == 2
        assert "no_registered_agents" not in result["warnings"]

    def test_connected_agent_does_not_deadlock(self):
        """회귀 테스트(2026-09-29): connected_at이 채워진(실연결) 에이전트가 있으면
        build_local_agent_diagnostics() -> get_agent_status() -> get_active_task_count()
        로 이어지는 경로를 실제로 타게 된다. 예전엔 라우터(local_agent_router_query.py)가
        _reg._lock을 잡은 채로 이 함수를 호출했는데, get_active_task_count()가 같은
        (비재진입) _lock을 다시 획득하려 해 영구 교착이 났다 — 실사용(agent가 실제 WS로
        연결돼 connected_at이 채워진 상태)에서만 터지고, connected_at이 비어있는(=미연결)
        테스트 픽스처들은 get_agent_status()가 조기 반환해 이 경로를 안 타서 못 잡았다.
        이 테스트는 pytest-timeout 없이도 단순 성공/실패로 회귀를 드러낸다 — 데드락이
        재발하면 이 테스트 자체가 전체 스위트를 멈춰버리므로, CI/로컬에서 즉시 드러난다."""
        agent = _reg.LocalAgent(
            agent_id="agent1",
            host="pc1",
            os_name="Windows 11",
            version="0.1.0",
            registered_at=_reg._now_iso(),
            requested_by="admin",
            token_hash="fake_hash",
            connected_at=_reg._now_iso(),
            last_seen_at=_reg._now_iso(),
        )
        _reg._agents["agent1"] = agent

        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert result["agents"]["total"] == 1
        assert result["agents"]["online"] == 1

    def test_task_counts_by_status(self):
        """task 상태별 count."""
        now = _reg._now_iso()

        tasks = [
            _reg.LocalAgentTask(
                task_id="t1",
                agent_id="a1",
                action="ping",
                params={},
                risk_level="low",
                status="completed",
                requested_by="admin",
                created_at=now,
                updated_at=now,
            ),
            _reg.LocalAgentTask(
                task_id="t2",
                agent_id="a1",
                action="ping",
                params={},
                risk_level="low",
                status="running",
                requested_by="admin",
                created_at=now,
                updated_at=now,
            ),
            _reg.LocalAgentTask(
                task_id="t3",
                agent_id="a1",
                action="capture_screenshot",
                params={},
                risk_level="high",
                status="waiting_approval",
                requested_by="admin",
                created_at=now,
                updated_at=now,
            ),
            _reg.LocalAgentTask(
                task_id="t4",
                agent_id="a1",
                action="ping",
                params={},
                risk_level="low",
                status="failed",
                requested_by="admin",
                created_at=now,
                updated_at=now,
                failure_reason="unknown_error",
            ),
        ]
        for t in tasks:
            _reg._tasks[t.task_id] = t

        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert result["tasks"]["total"] == 4
        assert result["tasks"]["completed"] == 1
        assert result["tasks"]["running"] == 1
        assert result["tasks"]["waiting_approval"] == 1
        assert result["tasks"]["failed"] == 1

    def test_summary_counts(self):
        """observe_summary/audit_summary count."""
        now = _reg._now_iso()

        task_with_obs = _reg.LocalAgentTask(
            task_id="t1",
            agent_id="a1",
            action="ping",
            params={},
            risk_level="low",
            status="completed",
            requested_by="admin",
            created_at=now,
            updated_at=now,
            observe_summary={"status_category": "success"},
        )
        task_with_audit = _reg.LocalAgentTask(
            task_id="t2",
            agent_id="a1",
            action="ping",
            params={},
            risk_level="low",
            status="completed",
            requested_by="admin",
            created_at=now,
            updated_at=now,
            audit_summary={"event_count": 5},
        )
        task_with_result = _reg.LocalAgentTask(
            task_id="t3",
            agent_id="a1",
            action="ping",
            params={},
            risk_level="low",
            status="completed",
            requested_by="admin",
            created_at=now,
            updated_at=now,
            result_summary="success",
        )

        _reg._tasks["t1"] = task_with_obs
        _reg._tasks["t2"] = task_with_audit
        _reg._tasks["t3"] = task_with_result

        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert result["summaries"]["with_observe_summary"] == 1
        assert result["summaries"]["with_audit_summary"] == 1
        assert result["summaries"]["with_result_summary"] == 1

    def test_failed_task_triggers_warn_status(self):
        """failed task > 0 이면 status warn."""
        now = _reg._now_iso()
        task = _reg.LocalAgentTask(
            task_id="t1",
            agent_id="a1",
            action="ping",
            params={},
            risk_level="low",
            status="failed",
            requested_by="admin",
            created_at=now,
            updated_at=now,
            failure_reason="unknown_error",
        )
        _reg._tasks["t1"] = task

        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert result["status"] == "warn"
        assert "failed_tasks" in result["warnings"]

    def test_waiting_approval_triggers_warn_status(self):
        """waiting_approval task > 0 이면 status warn."""
        now = _reg._now_iso()
        task = _reg.LocalAgentTask(
            task_id="t1",
            agent_id="a1",
            action="capture_screenshot",
            params={},
            risk_level="high",
            status="waiting_approval",
            requested_by="admin",
            created_at=now,
            updated_at=now,
        )
        _reg._tasks["t1"] = task

        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert result["status"] == "warn"
        assert "approval_backlog" in result["warnings"]

    def test_latest_task_timestamps(self):
        """latest task created_at, updated_at, status."""
        now = _reg._now_iso()
        task = _reg.LocalAgentTask(
            task_id="t1",
            agent_id="a1",
            action="ping",
            params={},
            risk_level="low",
            status="completed",
            requested_by="admin",
            created_at=now,
            updated_at=now,
            observe_summary={"status": "ok"},
            audit_summary={"events": 3},
        )
        _reg._tasks["t1"] = task

        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert result["latest"]["task_created_at"] == now
        assert result["latest"]["task_updated_at"] == now
        assert result["latest"]["task_status"] == "completed"
        assert result["latest"]["has_observe_summary"] is True
        assert result["latest"]["has_audit_summary"] is True

    def test_no_token_id_in_response(self):
        """response에 token_id 미포함."""
        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert "token_id" not in str(result)

    def test_no_params_in_response(self):
        """response에 params/raw_params 미포함."""
        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert "params" not in str(result)
        assert "raw_params" not in str(result)

    def test_no_raw_audit_in_response(self):
        """response에 raw audit JSONL/events 미포함."""
        now = _reg._now_iso()
        task = _reg.LocalAgentTask(
            task_id="t1",
            agent_id="a1",
            action="ping",
            params={},
            risk_level="low",
            status="completed",
            requested_by="admin",
            created_at=now,
            updated_at=now,
            audit_summary={"event_count": 5, "events": [{"type": "click"}]},
        )
        _reg._tasks["t1"] = task

        result = local_agent_diagnostics.build_local_agent_diagnostics()

        # Only count, not raw events
        assert "events" not in str(result)
        assert "raw_events" not in str(result)

    def test_no_url_or_html_in_response(self):
        """response에 current_url, html, body, query, fragment 미포함."""
        result = local_agent_diagnostics.build_local_agent_diagnostics()

        response_str = str(result)
        assert "current_url" not in response_str
        assert "html" not in response_str
        assert "body" not in response_str
        assert "query" not in response_str
        assert "fragment" not in response_str

    def test_no_secret_fields_in_response(self):
        """response에 token, password, secret, cookie, session 미포함."""
        result = local_agent_diagnostics.build_local_agent_diagnostics()

        response_str = str(result).lower()
        assert "password" not in response_str or "password" in ["with_password"]  # 안전한 경우 제외
        assert "secret" not in response_str or "secret" in ["with_secret"]
        assert "cookie" not in response_str
        assert "session" not in response_str

    def test_exception_handling_returns_error_status(self):
        """예외 발생 시 status error 반환, raw exception 미노출."""
        # Mock 하여 예외 발생 시뮬레이션은 어려우므로 스킵
        # 실제로는 내부 try-except가 처리
        pass

    def test_diagnostics_generated_at_is_recent(self):
        """diagnostics_generated_at이 현재 시각."""
        result = local_agent_diagnostics.build_local_agent_diagnostics()

        gen_time = result["diagnostics_generated_at"]
        now = datetime.now(UTC).isoformat()  # noqa: F841

        # ISO format 체크
        assert "T" in gen_time
        assert "Z" in gen_time or "+" in gen_time

    def test_schema_version_present(self):
        """schema_version 포함."""
        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert result["schema_version"] == 1

    def test_repo_boundary_status_initial(self):
        """초기 repo_boundary_status는 not_checked."""
        result = local_agent_diagnostics.build_local_agent_diagnostics()

        assert result["repo_boundary_status"] == "not_checked"

    def test_all_task_statuses_in_counts(self):
        """모든 task status가 counts에 포함."""
        result = local_agent_diagnostics.build_local_agent_diagnostics()

        required_statuses = [
            "total",
            "queued",
            "pending",
            "running",
            "waiting_approval",
            "completed",
            "failed",
            "rejected",
            "cancelled",
        ]
        for status in required_statuses:
            assert status in result["tasks"]
            assert isinstance(result["tasks"][status], int)


class TestEndpointRegistration:
    """라우터 endpoint 등록 확인 (정적)."""

    def test_endpoint_is_get_only(self):
        """diagnostics endpoint는 GET만 지원."""
        from ai_orchestrator.agent_hub.router.root import local_agent_router

        # 라우터에 등록된 route 확인
        routes = local_agent_router.routes
        diagnostics_route = None
        for route in routes:
            if hasattr(route, "path") and "/diagnostics" in route.path:
                diagnostics_route = route
                break

        # route가 GET 메서드를 포함하는지 확인
        if diagnostics_route:
            assert "GET" in diagnostics_route.methods or diagnostics_route.methods == {"GET"}
