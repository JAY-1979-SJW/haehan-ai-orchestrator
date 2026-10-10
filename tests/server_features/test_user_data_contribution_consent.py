"""Consent-gated development material export contract."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ai_orchestrator.asgi import app
from ai_orchestrator.user_data import user_data_contribution_store as store


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_CONSENT_LOG_PATH", tmp_path / "consents.jsonl")
    store.clear_store()
    yield
    store.clear_store()


def _safe_record() -> dict[str, str]:
    return {
        "task_category": "browser_readonly",
        "tool_id_or_module": "browser.inspect",
        "safe_user_intent_summary": "inspect a public notice page",
        "safe_result_summary": "page title extracted",
        "error_code": "",
        "state_transition": "queued->completed",
        "verification_reference": "tests/server_features/test_user_data_contribution_consent.py",
        "user_feedback": "useful",
        "masked_user_reference": "user_***",
    }


def test_grant_consent_records_server_source_of_truth() -> None:
    consent = store.grant_consent(
        user_reference="user-1",
        purposes=[store.PURPOSE_PRODUCT_IMPROVEMENT],
        data_categories=["task_category", "safe_result_summary"],
        retention_days=30,
    )

    assert consent["status"] == store.STATUS_ACTIVE
    assert consent["user_reference"] == "user-1"
    assert consent["consent_id"]
    fetched = store.get_consent(consent["consent_id"])
    assert fetched is not None
    assert fetched["status"] == store.STATUS_ACTIVE


def test_consent_persists_to_jsonl_and_reloads() -> None:
    consent = store.grant_consent(
        user_reference="user-1",
        purposes=[store.PURPOSE_PRODUCT_IMPROVEMENT],
        data_categories=["task_category", "safe_result_summary"],
        retention_days=30,
    )

    store.clear_store()
    loaded_count = store.reload_store_from_disk()
    loaded = store.get_consent(consent["consent_id"])

    assert loaded_count == 1
    assert loaded is not None
    assert loaded["status"] == store.STATUS_ACTIVE
    assert loaded["user_reference"] == "user-1"


def test_revoke_persists_to_jsonl_and_reloads() -> None:
    consent = store.grant_consent(
        user_reference="user-1",
        purposes=[store.PURPOSE_PRODUCT_IMPROVEMENT],
        data_categories=["task_category", "safe_result_summary"],
        retention_days=30,
    )
    store.revoke_consent(consent["consent_id"])

    store.clear_store()
    store.reload_store_from_disk()
    loaded = store.get_consent(consent["consent_id"])

    assert loaded is not None
    assert loaded["status"] == store.STATUS_REVOKED
    assert loaded["revoked_at"]


def test_consent_jsonl_contains_no_raw_material() -> None:
    store.grant_consent(
        user_reference="user-1",
        purposes=[store.PURPOSE_PRODUCT_IMPROVEMENT],
        data_categories=["task_category", "safe_result_summary"],
        retention_days=30,
    )

    lines = store._CONSENT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    serialized = json.dumps(event)

    assert event["_type"] == "consent_granted"
    assert "raw_user_prompt" not in serialized
    assert "password" not in serialized


def test_export_blocks_without_active_consent() -> None:
    result = store.export_development_material(
        user_reference="user-1",
        purpose=store.PURPOSE_PRODUCT_IMPROVEMENT,
        records=[_safe_record()],
    )

    assert result["accepted"] is False
    assert "missing active consent" in result["blocked_reason"][0]
    assert result["materials"] == []


def test_export_allows_only_consented_safe_categories() -> None:
    categories = list(_safe_record().keys())
    consent = store.grant_consent(
        user_reference="user-1",
        purposes=[store.PURPOSE_PRODUCT_IMPROVEMENT],
        data_categories=categories,
    )

    result = store.export_development_material(
        user_reference="user-1",
        purpose=store.PURPOSE_PRODUCT_IMPROVEMENT,
        records=[_safe_record()],
    )

    assert result["accepted"] is True
    assert result["consent_id"] == consent["consent_id"]
    assert result["record_count"] == 1
    assert result["materials"][0]["safe_result_summary"] == "page title extracted"


def test_export_blocks_raw_prompt_even_with_consent() -> None:
    categories = list(_safe_record().keys())
    store.grant_consent(
        user_reference="user-1",
        purposes=[store.PURPOSE_PRODUCT_IMPROVEMENT],
        data_categories=categories,
    )
    unsafe = {**_safe_record(), "raw_user_prompt": "send this whole private email"}

    result = store.export_development_material(
        user_reference="user-1",
        purpose=store.PURPOSE_PRODUCT_IMPROVEMENT,
        records=[unsafe],
    )

    assert result["accepted"] is False
    assert any("raw_user_prompt" in item for item in result["blocked_reason"])
    assert result["materials"] == []


def test_export_blocks_after_revoke() -> None:
    categories = list(_safe_record().keys())
    consent = store.grant_consent(
        user_reference="user-1",
        purposes=[store.PURPOSE_PRODUCT_IMPROVEMENT],
        data_categories=categories,
    )
    store.revoke_consent(consent["consent_id"])

    result = store.export_development_material(
        user_reference="user-1",
        purpose=store.PURPOSE_PRODUCT_IMPROVEMENT,
        records=[_safe_record()],
    )

    assert result["accepted"] is False
    assert result["consent_id"] is None


def test_router_is_included_under_api_v1() -> None:
    from tests.app_routes import route_paths
    paths = route_paths()

    assert "/api/v1/data-contribution/consents" in paths
    assert "/api/v1/data-contribution/development-material/export" in paths


def test_api_export_blocks_missing_consent(monkeypatch) -> None:
    from ai_orchestrator.core import config

    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    client = TestClient(app)

    response = client.post(
        "/api/v1/data-contribution/development-material/export",
        json={
            "user_reference": "user-1",
            "purpose": store.PURPOSE_PRODUCT_IMPROVEMENT,
            "records": [_safe_record()],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["data"]["materials"] == []
