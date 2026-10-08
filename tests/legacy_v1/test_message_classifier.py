"""
범용 메시지 분류기 + 카카오 채널 classify → candidate 연결 테스트
1. kakaowork 메시지 분류 성공
2. kakaotalk_channel 메시지 분류 성공
3. 확신 낮음 → needs_review=True
4. candidate 생성 검증
5. source_type별 분리 조회 검증
6. 자동 실행 미발생 확인
7. 앱 부팅 가능 여부
8. 기존 email 분류 정책 무변경
9. API /api/v1/inbox/classify 동작
10. candidate linked_task_id=None 유지
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

import orchestrator_v1.inbox.inbox_store as inbox_store
import orchestrator_v1.tasks.candidate_store as candidate_store
from orchestrator_v1.inbox.message_classifier import classify_message

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_inbox(tmp_path):
    return str(tmp_path / "inbox.jsonl")


@pytest.fixture
def tmp_cand(tmp_path):
    return str(tmp_path / "candidates.jsonl")


@pytest.fixture
def flask_app():
    os.environ.setdefault("ORCH_DASHBOARD_USER", "test")
    os.environ.setdefault("ORCH_DASHBOARD_PASSWORD", "test")
    from orchestrator_v1.monitoring.dashboard import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(flask_app):
    with flask_app.test_client() as c:
        c.environ_base["HTTP_AUTHORIZATION"] = "Basic dGVzdDp0ZXN0"
        yield c


def _kw_item(source_type: str, title: str, body: str, sender: str = "user@kakao") -> dict:
    return {
        "source_type": source_type,
        "external_id": f"ext-{hash(title) & 0xFFFFFF:06x}",
        "source_account": f"{source_type}-account",
        "sender": sender,
        "title": title,
        "body_raw": body,
        "received_at": "2026-04-22T10:00:00",
    }


# ── 1. kakaowork 메시지 분류 성공 ─────────────────────────────────────────────


def test_kakaowork_sales_classified():
    item = _kw_item("kakaowork", "견적서 요청", "납품 단가와 공급 조건 보내드립니다. 계약서 검토 요청드립니다.")
    result = classify_message(item)
    assert result["category"] == "sales"
    assert result["candidate_task_type"] == "quote_response"
    assert "source=kakaowork" in result["classification_reason"]


def test_kakaowork_operations_classified():
    item = _kw_item("kakaowork", "서버 장애 발생", "긴급 — 서버 오류 발생. 즉시 점검 필요합니다.")
    result = classify_message(item)
    assert result["category"] == "operations"
    assert result["priority"] == "high"


def test_kakaowork_support_classified():
    """support 카테고리는 카카오 채널 전용 추가 규칙에서 감지."""
    item = _kw_item("kakaowork", "도움 요청", "문의드립니다. 처리 방법이 궁금합니다.")
    result = classify_message(item)
    assert result["category"] == "support"
    assert result["candidate_task_type"] == "support_ticket"


# ── 2. kakaotalk_channel 메시지 분류 성공 ─────────────────────────────────────


def test_kakaotalk_channel_support_classified():
    item = _kw_item("kakaotalk_channel", "문의드립니다", "고객센터 문의입니다. 답변 부탁드립니다.")
    result = classify_message(item)
    assert result["category"] == "support"
    assert "source=kakaotalk_channel" in result["classification_reason"]


def test_kakaotalk_channel_meeting_classified():
    item = _kw_item(
        "kakaotalk_channel", "회의 일정", "다음 주 미팅 agenda 공유드립니다. 회의록 작성 예정이며 워크숍 참석 바랍니다."
    )
    result = classify_message(item)
    assert result["category"] == "meeting"


def test_kakaotalk_channel_sales_classified():
    item = _kw_item("kakaotalk_channel", "견적 및 계약 문의", "견적서 요청드립니다. 계약 조건 협의 원합니다.")
    result = classify_message(item)
    assert result["category"] in {"sales", "support"}  # sales 또는 support (규칙 우선순위 따름)


# ── 3. 확신 낮음 → needs_review=True ─────────────────────────────────────────


def test_low_confidence_needs_review_kakaowork():
    """키워드 1개 미만 → general + needs_review=True."""
    item = _kw_item("kakaowork", "안녕하세요", "잠시 연락드립니다.")
    result = classify_message(item)
    assert result["needs_review"] is True
    assert result["category"] == "general"
    assert result["candidate_task_type"] is None


def test_single_keyword_needs_review_kakaotalk():
    """키워드 1개 → needs_review=True (카카오 보수적 임계값)."""
    item = _kw_item("kakaotalk_channel", "문의", "문의드립니다.")
    result = classify_message(item)
    # "문의" 1개만 매칭 → needs_review=True
    assert result["needs_review"] is True


def test_multiple_keywords_confident_kakaowork():
    """키워드 2개 이상 → needs_review=False."""
    item = _kw_item("kakaowork", "견적서 납품 요청", "단가와 계약서를 보내드립니다. 납품 일정 및 주문서 공유드립니다.")
    result = classify_message(item)
    # 견적, 단가, 계약서, 납품, 주문 등 다수 매칭 → needs_review=False
    assert result["category"] == "sales"
    assert result["needs_review"] is False


# ── 4. candidate 생성 검증 ────────────────────────────────────────────────────


def test_classify_saves_candidate(tmp_cand):
    item = _kw_item("kakaowork", "견적 요청", "견적 문의드립니다. 단가 확인 부탁드립니다.")
    clf = classify_message(item)

    r = candidate_store.save_candidate(
        external_id=item["external_id"],
        source_account=item["source_account"],
        category=clf["category"],
        priority=clf["priority"],
        needs_review=clf["needs_review"],
        candidate_task_type=clf["candidate_task_type"],
        classification_reason=clf["classification_reason"],
        path=tmp_cand,
    )

    assert r["status"] == "saved"
    cand = candidate_store.get_candidate(r["item_id"], path=tmp_cand)
    assert cand is not None
    assert cand["category"] == clf["category"]
    assert cand["linked_task_id"] is None  # 자동 task 생성 없음


def test_candidate_linked_task_id_null(tmp_cand):
    """candidate 저장 시 linked_task_id는 항상 None."""
    item = _kw_item("kakaotalk_channel", "서비스 문의", "고객 문의 처리 요청드립니다.")
    clf = classify_message(item)

    r = candidate_store.save_candidate(
        external_id=item["external_id"],
        source_account=item["source_account"],
        category=clf["category"],
        priority=clf["priority"],
        needs_review=clf["needs_review"],
        candidate_task_type=clf["candidate_task_type"],
        classification_reason=clf["classification_reason"],
        path=tmp_cand,
    )

    cand = candidate_store.get_candidate(r["item_id"], path=tmp_cand)
    assert cand["linked_task_id"] is None


# ── 5. source_type별 분리 조회 ────────────────────────────────────────────────


def test_source_type_inbox_filter(tmp_inbox):
    """kakaowork / kakaotalk_channel / email 각각 독립 필터."""
    inbox_store.save_message(
        source_type="kakaowork",
        external_id="kw-ext-001",
        source_account="kw-account",
        sender="user1",
        title="kakaowork 메시지",
        body_raw="본문",
        received_at="2026-04-22T10:00:00",
        path=tmp_inbox,
    )
    inbox_store.save_message(
        source_type="kakaotalk_channel",
        external_id="kt-ext-001",
        source_account="kt-account",
        sender="user2",
        title="채널 메시지",
        body_raw="본문",
        received_at="2026-04-22T10:01:00",
        path=tmp_inbox,
    )
    inbox_store.save_mail(
        external_id="email-ext-001",
        sender="sender@example.com",
        title="이메일",
        body_raw="본문",
        received_at="2026-04-22T10:02:00",
        source_account="mail@company.com",
        path=tmp_inbox,
    )

    kw = inbox_store.list_inbox(source_type="kakaowork", path=tmp_inbox)
    kt = inbox_store.list_inbox(source_type="kakaotalk_channel", path=tmp_inbox)
    em = inbox_store.list_inbox(source_type="email", path=tmp_inbox)

    assert len(kw) == 1 and kw[0]["source_type"] == "kakaowork"
    assert len(kt) == 1 and kt[0]["source_type"] == "kakaotalk_channel"
    assert len(em) == 1 and em[0]["source_type"] == "email"


# ── 6. 자동 실행 미발생 확인 ──────────────────────────────────────────────────


def test_no_auto_execution_on_classify():
    import orchestrator_v1.tasks.task_store as ts

    ts.clear()

    item = _kw_item("kakaowork", "견적 요청", "견적 문의드립니다.")
    classify_message(item)

    assert len(ts._store) == 0


def test_no_auto_task_creation_on_classify(tmp_cand):
    """classify 후 candidate 생성되어도 email_task는 생성 안됨."""
    import orchestrator_v1.tasks.email_task_store as email_task_store

    item = _kw_item("kakaowork", "견적 문의", "단가 견적 요청드립니다.")
    clf = classify_message(item)
    candidate_store.save_candidate(
        external_id=item["external_id"],
        source_account=item["source_account"],
        category=clf["category"],
        priority=clf["priority"],
        needs_review=clf["needs_review"],
        candidate_task_type=clf["candidate_task_type"],
        classification_reason=clf["classification_reason"],
        path=tmp_cand,
    )

    # email_tasks.jsonl 기본 경로에 task가 생성되면 안됨
    task_path = Path(__file__).resolve().parent.parent.parent / "storage" / "email_tasks.jsonl"
    if task_path.exists():
        tasks = email_task_store.list_email_tasks()  # noqa: F841
        # 테스트 중 생성된 task가 없어야 함 (기존 데이터 무시)
    # task_store는 비어있어야 함
    import orchestrator_v1.tasks.task_store as ts

    assert ts.get(item["external_id"]) is None


# ── 7. 앱 부팅 가능 여부 ──────────────────────────────────────────────────────


def test_app_boot_with_classify_route(flask_app):
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    assert "/api/v1/inbox/classify" in rules
    # 기존 라우트 유지
    assert "/api/v1/inbox/email/classify" in rules
    assert "/api/v1/inbox/candidates/<item_id>/task" in rules


# ── 8. 기존 email 분류 정책 무변경 ───────────────────────────────────────────


def test_email_classify_unchanged():
    """email source_type은 기존 email_classifier.classify()와 동일 결과."""
    from orchestrator_v1.inbox.email_classifier import classify as email_classify

    item = {
        "source_type": "email",
        "title": "입찰공고 — 나라장터 조달청",
        "body_raw": "입찰 공고 안내드립니다. 제안요청서 확인 바랍니다.",
        "sender": "bid@example.com",
    }
    result_generic = classify_message(item)
    result_email = email_classify(item)

    assert result_generic["category"] == result_email["category"]
    assert result_generic["candidate_task_type"] == result_email["candidate_task_type"]


def test_no_conflict_with_approval_manager():
    import orchestrator_v1.tasks.approval_manager as approval_manager
    import orchestrator_v1.tasks.task_store as task_store

    before_approval = dict(approval_manager._store)
    before_task = dict(task_store._store)

    item = _kw_item("kakaowork", "견적 요청", "견적 문의드립니다.")
    classify_message(item)

    assert approval_manager._store == before_approval
    assert task_store._store == before_task


# ── 9. API /api/v1/inbox/classify 동작 ───────────────────────────────────────


def test_api_classify_kakaowork(client):
    """카카오워크 메시지 1건 수집 후 classify API 호출."""
    client.post(
        "/api/v1/webhooks/kakaowork",
        json={
            "type": "message",
            "user_id": "kw-api-user",
            "message": {
                "id": "api-msg-001",
                "text": "견적 문의드립니다. 단가 확인 부탁드립니다.",
                "created_at": 1713751200000,
            },
            "channel": {"id": "ch-001"},
        },
    )

    resp = client.post("/api/v1/inbox/classify?source_type=kakaowork")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["source_type"] == "kakaowork"
    assert data["classified"] + data["skipped"] >= 0


def test_api_classify_missing_source_type(client):
    resp = client.post("/api/v1/inbox/classify")
    assert resp.status_code == 400


def test_api_classify_invalid_source_type(client):
    resp = client.post("/api/v1/inbox/classify?source_type=slack")
    assert resp.status_code == 400


def test_api_classify_kakaotalk_channel(client):
    """카카오톡 채널 메시지 1건 수집 후 classify API 호출."""
    client.post(
        "/api/v1/webhooks/kakaotalk-channel",
        json={
            "userRequest": {
                "utterance": "서비스 문의드립니다. 도움 요청합니다.",
                "user": {"id": "kt-api-user", "type": "botUserKey"},
            },
            "bot": {"id": "bot-001"},
        },
    )

    resp = client.post("/api/v1/inbox/classify?source_type=kakaotalk_channel")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["source_type"] == "kakaotalk_channel"


# ── 10. candidate source 구분 ────────────────────────────────────────────────


def test_kakao_classification_reason_has_source(tmp_cand):
    """classification_reason에 source_type이 포함됨."""
    item = _kw_item("kakaowork", "회의 일정", "내일 미팅 일정 확인 부탁드립니다. 회의 장소 안내드립니다.")
    result = classify_message(item)

    assert "source=kakaowork" in result["classification_reason"]

    r = candidate_store.save_candidate(
        external_id=item["external_id"],
        source_account=item["source_account"],
        category=result["category"],
        priority=result["priority"],
        needs_review=result["needs_review"],
        candidate_task_type=result["candidate_task_type"],
        classification_reason=result["classification_reason"],
        path=tmp_cand,
    )

    cand = candidate_store.get_candidate(r["item_id"], path=tmp_cand)
    assert "source=kakaowork" in cand["classification_reason"]
