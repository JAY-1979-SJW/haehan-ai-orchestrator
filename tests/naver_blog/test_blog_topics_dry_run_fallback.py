"""회귀 시험: 리서치 파일이 없는 상태(신규 설치)에서 dry-run 이 real-run 과
같은 주제-선정 경로(고정 폴백 FALLBACK_TOPIC_SEED)를 타는지 확인한다.

결함: topics.generate_topics() 의 dry-run 조기 return(이전 코드)이 researched
기반 result 만 반환해서, RESEARCH_FILE 이 없으면 dry-run 은 항상 빈 리스트를
반환했다(FALLBACK_TOPIC_SEED 는 real-run 전용 경로에만 있었음) — "주제 선정
실패. 종료." (blog_ai_batch_20.py) 로 끝나지만 real-run 이었다면 폴백이 작동
했을 상황. dry-run 이 리허설로서 의미가 있으려면 같은 경로를 타야 한다.
"""

from __future__ import annotations

from scripts.naver.blog.marketing import topics as T


def test_dry_run_uses_fallback_seed_when_research_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "RESEARCH_FILE", tmp_path / "no_such_research_file.json")
    cache = {"posted": []}

    result = T.generate_topics(cache, count=3, dry_run=True)

    assert len(result) > 0
    assert len(result) <= 3
    for t in result:
        assert t["topic"] in T.FALLBACK_TOPIC_SEED


def test_dry_run_skips_already_used_fallback_titles(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "RESEARCH_FILE", tmp_path / "no_such_research_file.json")
    used_title = T.FALLBACK_TOPIC_SEED[0]
    cache = {"posted": [{"title": used_title, "key": T.topic_key(used_title)}]}

    result = T.generate_topics(cache, count=len(T.FALLBACK_TOPIC_SEED), dry_run=True)

    assert used_title not in [t["topic"] for t in result]


def test_real_run_falls_back_to_seed_when_ai_call_fails(tmp_path, monkeypatch):
    """회귀 시험: AI 보충 호출이 실패해도(ok=False) real-run 이 dry-run 과 같은
    고정/리서치 폴백으로 주제를 보충해야 한다 — 그러지 않으면 dry-run 은
    성공(폴백으로 count개 채움)하는데 real-run 만 "주제 선정 실패"로 끝나는
    비대칭이 생긴다(AI 호출 실패 시 조기 return 하던 이전 코드의 결함).
    AI 호출 자체는 모킹해서 외부 호출 없이 검증한다.
    """
    monkeypatch.setattr(T, "RESEARCH_FILE", tmp_path / "no_such_research_file.json")

    class _FakeAIResponder:
        def _call(self, *args, **kwargs):
            return {"ok": False, "error": "simulated API failure"}

    monkeypatch.setattr(T, "AIResponder", _FakeAIResponder)
    cache = {"posted": []}

    result = T.generate_topics(cache, count=3, dry_run=False)

    assert len(result) > 0
    assert len(result) <= 3
    for t in result:
        assert t["topic"] in T.FALLBACK_TOPIC_SEED


def test_real_run_falls_back_to_seed_when_ai_json_unparseable(tmp_path, monkeypatch):
    """AI 호출은 성공(ok=True)했지만 응답이 JSON 배열로 파싱되지 않는 경우에도
    같은 폴백 경로로 보충해야 한다."""
    monkeypatch.setattr(T, "RESEARCH_FILE", tmp_path / "no_such_research_file.json")

    class _FakeAIResponder:
        def _call(self, *args, **kwargs):
            return {"ok": True, "text": "이것은 JSON이 아닌 응답입니다."}

    monkeypatch.setattr(T, "AIResponder", _FakeAIResponder)
    cache = {"posted": []}

    result = T.generate_topics(cache, count=3, dry_run=False)

    assert len(result) > 0
    assert len(result) <= 3
    for t in result:
        assert t["topic"] in T.FALLBACK_TOPIC_SEED
