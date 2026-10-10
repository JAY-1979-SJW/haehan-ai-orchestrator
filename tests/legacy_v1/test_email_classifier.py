"""
이메일 분류기 및 candidate 저장 테스트
- 운영/영업/회계/입찰/회의/일반 분류
- 확신 낮음 → needs_review=True
- task 후보 생성 검증
- 기존 inbox 구조 호환 검증
- 앱 부팅 가능 여부
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import orchestrator_v1.inbox.inbox_store as inbox_store
import orchestrator_v1.tasks.candidate_store as candidate_store
from orchestrator_v1.inbox.email_classifier import classify

# ── 공통 inbox item 팩토리 ────────────────────────────────────────────────────


def _item(title: str, body: str = "", sender: str = "test@example.com") -> dict:
    return {
        "source_type": "email",
        "source_account": "jay@haehan-ai.kr",
        "external_id": f"<{title[:10]}@test>",
        "sender": sender,
        "title": title,
        "body_raw": body,
        "received_at": "2026-04-22T10:00:00",
        "saved_at": "2026-04-22T10:01:00",
        "status": "new",
        "linked_task_id": None,
    }


# ── 1. 카테고리 분류 케이스 ────────────────────────────────────────────────────


def test_classify_bidding():
    result = classify(_item("입찰공고 안내 - 나라장터 2026-04-22"))
    assert result["category"] == "bidding"
    assert result["candidate_task_type"] == "bid_review"
    assert result["needs_review"] is False


def test_classify_sales_quote():
    result = classify(_item("견적 요청드립니다", body="단가 및 납품 조건 문의합니다."))
    assert result["category"] == "sales"
    assert result["candidate_task_type"] == "quote_response"


def test_classify_accounting():
    result = classify(_item("세금계산서 발행 요청", body="청구서 첨부드립니다."))
    assert result["category"] == "accounting"
    assert result["candidate_task_type"] == "accounting_review"


def test_classify_operations():
    result = classify(_item("서버 장애 발생", body="긴급 조치 필요합니다."))
    assert result["category"] == "operations"
    assert result["candidate_task_type"] == "ops_check"


def test_classify_meeting():
    result = classify(_item("4월 정기 회의 일정 안내"))
    assert result["category"] == "meeting"
    assert result["candidate_task_type"] == "meeting_prep"


def test_classify_development():
    result = classify(_item("GitHub PR 리뷰 요청", body="버그 수정 PR입니다."))
    assert result["category"] == "development"
    assert result["candidate_task_type"] == "dev_review"


def test_classify_general_no_keywords():
    result = classify(_item("안녕하세요", body="잘 지내시나요?"))
    assert result["category"] == "general"
    assert result["needs_review"] is True
    assert result["candidate_task_type"] is None


# ── 2. 확신 낮음 → needs_review=True ─────────────────────────────────────────


def test_low_confidence_needs_review():
    """키워드 1개 이하면 needs_review=True."""
    result = classify(_item("입찰"))  # 키워드 1개 정확히 매칭
    assert result["needs_review"] is True


def test_newsletter_sender_needs_review():
    result = classify(_item("4월 뉴스레터", sender="newsletter@stibee.com"))
    assert result["needs_review"] is True
    assert result["candidate_task_type"] is None


# ── 3. 우선순위 판정 ──────────────────────────────────────────────────────────


def test_priority_high_urgent():
    result = classify(_item("긴급 - 서버 장애 발생"))
    assert result["priority"] == "high"


def test_priority_low_newsletter():
    result = classify(_item("이번 달 이벤트 안내", sender="noreply@marketing.com"))
    assert result["priority"] == "low"


def test_priority_medium_sales():
    result = classify(_item("견적 요청 드립니다", body="납품 조건 협의 부탁드립니다."))
    assert result["priority"] == "medium"


# ── 4. task 후보 생성 검증 ────────────────────────────────────────────────────


def test_candidate_save_and_list(tmp_path):
    cand_path = str(tmp_path / "candidates.jsonl")
    item = _item("나라장터 입찰공고 긴급 확인", body="입찰 마감 오늘까지")

    clf = classify(item)
    result = candidate_store.save_candidate(
        external_id=item["external_id"],
        source_account=item["source_account"],
        category=clf["category"],
        priority=clf["priority"],
        needs_review=clf["needs_review"],
        candidate_task_type=clf["candidate_task_type"],
        classification_reason=clf["classification_reason"],
        path=cand_path,
    )
    assert result["status"] == "saved"
    assert "item_id" in result

    candidates = candidate_store.list_candidates(path=cand_path)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["category"] == "bidding"
    assert c["candidate_task_type"] == "bid_review"
    assert c["linked_task_id"] is None
    assert "classified_at" in c


def test_candidate_duplicate_skip(tmp_path):
    cand_path = str(tmp_path / "candidates.jsonl")
    item = _item("입찰공고 안내")
    clf = classify(item)
    kwargs = {
        "external_id": item["external_id"],
        "source_account": item["source_account"],
        "category": clf["category"],
        "priority": clf["priority"],
        "needs_review": clf["needs_review"],
        "candidate_task_type": clf["candidate_task_type"],
        "classification_reason": clf["classification_reason"],
        "path": cand_path,
    }
    r1 = candidate_store.save_candidate(**kwargs)
    r2 = candidate_store.save_candidate(**kwargs)
    assert r1["status"] == "saved"
    assert r2["status"] == "skipped"
    assert len(candidate_store.list_candidates(path=cand_path)) == 1


def test_candidate_filter_by_category(tmp_path):
    cand_path = str(tmp_path / "candidates.jsonl")
    for title, body in [
        ("세금계산서 청구", "회계 처리"),
        ("나라장터 입찰 공고", "발주 관련"),
    ]:
        item = _item(title, body)
        clf = classify(item)
        candidate_store.save_candidate(
            external_id=item["external_id"],
            source_account=item["source_account"],
            category=clf["category"],
            priority=clf["priority"],
            needs_review=clf["needs_review"],
            candidate_task_type=clf["candidate_task_type"],
            classification_reason=clf["classification_reason"],
            path=cand_path,
        )

    bidding = candidate_store.list_candidates(category="bidding", path=cand_path)
    accounting = candidate_store.list_candidates(category="accounting", path=cand_path)
    assert len(bidding) == 1
    assert len(accounting) == 1


# ── 5. 기존 inbox 구조 호환 검증 ─────────────────────────────────────────────


def test_inbox_and_candidate_compatible(tmp_path):
    """inbox.save_mail → classify → candidate_store.save_candidate 흐름 검증."""
    inbox_path = str(tmp_path / "inbox.jsonl")
    cand_path = str(tmp_path / "candidates.jsonl")

    inbox_store.save_mail(
        external_id="<compat-001@test>",
        sender="client@partner.com",
        title="견적 요청의 건",
        body_raw="납품 단가 문의드립니다.",
        received_at="2026-04-22T09:00:00",
        source_account="jay@haehan-ai.kr",
        path=inbox_path,
    )

    items = inbox_store.list_inbox(source_type="email", path=inbox_path)
    assert len(items) == 1

    clf = classify(items[0])
    r = candidate_store.save_candidate(
        external_id=items[0]["external_id"],
        source_account=items[0]["source_account"],
        category=clf["category"],
        priority=clf["priority"],
        needs_review=clf["needs_review"],
        candidate_task_type=clf["candidate_task_type"],
        classification_reason=clf["classification_reason"],
        path=cand_path,
    )
    assert r["status"] == "saved"

    candidates = candidate_store.list_candidates(path=cand_path)
    assert candidates[0]["category"] == "sales"
    assert candidates[0]["candidate_task_type"] == "quote_response"


# ── 6. JSONL 파일 포맷 검증 ──────────────────────────────────────────────────


def test_candidate_jsonl_format(tmp_path):
    cand_path = str(tmp_path / "candidates.jsonl")
    item = _item("세금계산서 발행 요청")
    clf = classify(item)
    candidate_store.save_candidate(
        external_id=item["external_id"],
        source_account=item["source_account"],
        category=clf["category"],
        priority=clf["priority"],
        needs_review=clf["needs_review"],
        candidate_task_type=clf["candidate_task_type"],
        classification_reason=clf["classification_reason"],
        path=cand_path,
    )
    with Path(cand_path).open(encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]  # noqa: E741
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    required = {
        "item_id",
        "category",
        "priority",
        "needs_review",
        "candidate_task_type",
        "classified_at",
        "linked_task_id",
    }
    assert required.issubset(parsed.keys())
    assert parsed["linked_task_id"] is None


# ── 7. 앱 부팅 + 새 엔드포인트 등록 확인 ─────────────────────────────────────


def test_app_boot_with_classify_routes():
    import os as _os

    _os.environ.setdefault("ORCH_DASHBOARD_USER", "test")
    _os.environ.setdefault("ORCH_DASHBOARD_PASSWORD", "test")

    from orchestrator_v1.monitoring.dashboard import create_app

    app = create_app()
    assert "inbox" in app.blueprints

    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/v1/inbox/email/classify" in rules
    assert "/api/v1/inbox/candidates" in rules
