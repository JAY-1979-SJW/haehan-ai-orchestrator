"""naver_search_router.py 의 api_run_blog_search / api_run_shopping_search — G12 중복정리
(2026-10-09)로 공통 헬퍼 _run_search_job() 으로 합친 뒤, 두 래퍼가 여전히 각자 맞는
event 이름·job 함수로 똑같은 응답 모양을 내는지 확인한다."""

from __future__ import annotations

from dataclasses import dataclass

from ai_orchestrator.connectors.naver_search import naver_search_router as r


@dataclass
class _FakeOutcome:
    status: str
    inserted_count: int
    db_status: str


def _fake_job(*, query: str, max_pages: int) -> _FakeOutcome:
    return _FakeOutcome(status="ok", inserted_count=3, db_status="saved")


def test_run_search_job_shapes_response_and_logs_event(monkeypatch):
    logged = {}
    monkeypatch.setattr(r, "log_event", lambda event, **kw: logged.update(event=event, **kw))

    result = r._run_search_job("FAKE_EVENT", _fake_job, "query1", 2, {"actor": "u1", "role": "admin"})

    assert result["status"] == "ok"
    assert result["query"] == "query1"
    assert result["collected"] == 3
    assert result["db_status"] == "saved"
    assert "duration_ms" in result
    assert logged["event"] == "FAKE_EVENT"
    assert logged["actor"] == "u1"
    assert logged["decision"] == "ok"


def test_api_run_blog_search_uses_blog_job_and_event(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        r,
        "_run_search_job",
        lambda event, job_fn, query, max_pages, user: (
            seen.update(
                event=event,
                job_fn=job_fn,
                query=query,
                max_pages=max_pages,
            )
            or {"status": "ok"}
        ),
    )

    r.api_run_blog_search(query="q", max_pages=5, user={"actor": "a", "role": "admin"})

    assert seen["event"] == "NAVER_BLOG_SEARCH_RUN"
    assert seen["job_fn"] is r.run_naver_blog_search_job
    assert seen["query"] == "q"
    assert seen["max_pages"] == 5


def test_api_run_shopping_search_uses_shopping_job_and_event(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        r,
        "_run_search_job",
        lambda event, job_fn, query, max_pages, user: (
            seen.update(
                event=event,
                job_fn=job_fn,
                query=query,
                max_pages=max_pages,
            )
            or {"status": "ok"}
        ),
    )

    r.api_run_shopping_search(query="q2", max_pages=1, user={"actor": "a", "role": "owner"})

    assert seen["event"] == "NAVER_SHOPPING_SEARCH_RUN"
    assert seen["job_fn"] is r.run_naver_shopping_search_job
