"""사이트 카탈로그 테스트 — external_work_registry.list_site_catalog().

L11 Tests. provider 그룹핑·필드 구조·민감정보 미포함을 검증.
"""

from __future__ import annotations

from ai_orchestrator.tasks.external_work_registry import list_site_catalog


def test_catalog_groups_by_provider():
    cat = list_site_catalog()
    site_ids = {s["site_id"] for s in cat}
    # 등록된 provider(naver/google/gabia)가 사이트로 노출
    assert {"naver", "google", "gabia"} <= site_ids


def test_catalog_entry_shape():
    cat = list_site_catalog()
    for s in cat:
        assert set(s) >= {"site_id", "name", "category", "needs_local_agent", "work_count", "works"}
        assert isinstance(s["needs_local_agent"], bool)
        assert s["work_count"] == len(s["works"])
        for w in s["works"]:
            assert set(w) >= {
                "work_key",
                "work_type",
                "description",
                "risk_level",
                "requires_approval",
                "execution_location",
            }


def test_catalog_has_known_labels():
    cat = {s["site_id"]: s for s in list_site_catalog()}
    assert cat["naver"]["name"] == "네이버"
    assert cat["naver"]["needs_local_agent"] is True  # blog_write 등 LOCAL_AGENT 포함


def test_catalog_no_sensitive_fields():
    """카탈로그에 secret/token/password/notes 등 민감·내부 필드 미노출."""
    cat = list_site_catalog()
    flat = repr(cat).lower()
    for bad in ("password", "secret", "token", "cookie"):
        assert bad not in flat
    # 내부 운영 메모(notes)는 카탈로그에 포함하지 않음
    for s in cat:
        for w in s["works"]:
            assert "notes" not in w
