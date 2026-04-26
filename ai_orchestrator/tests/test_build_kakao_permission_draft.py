"""KAKAO-DEV-4 테스트 — build_kakao_permission_draft.py 검증.

- 최신 app_details.json 자동 선택
- draft.json / draft.md / required_documents.md / next_actions.md 생성
- submit_ready=False, review_required=True
- account_email 자동 필수화 안 됨 (경고만)
- draft에 secret 패턴 없음
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

_MODULE_PATH = REPO_ROOT / "scripts" / "build_kakao_permission_draft.py"

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("build_kakao_permission_draft", _MODULE_PATH)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_SECRET_PATTERN = re.compile(r"[0-9a-f]{32,}|[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_details_json(tmp_path: Path, app_id: str = "1413624") -> Path:
    run_dir = tmp_path / "kakao_app_details_20260426_111834"
    run_dir.mkdir(parents=True)
    data = {
        "session_status": "READY_LOGGED_IN",
        "observed_at": "20260426_111834",
        "app_count": 1,
        "apps": [
            {
                "app_id": app_id,
                "app_name_hint": "해한메이아이출퇴근",
                "scope": {"has_rejected": False, "biz_required_items": False, "review_needed": False},
                "platform": {"web_registered": False},
                "login": {"login_activated": True, "redirect_uri_registered": False},
                "biz": {"biz_required": False, "biz_pending": False},
                "diagnosis": ["Redirect URI 미등록"],
            }
        ],
    }
    p = run_dir / "app_details.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _find_latest_details_json
# ---------------------------------------------------------------------------

def test_find_latest_details_json(tmp_path):
    _make_details_json(tmp_path)
    result = _mod._find_latest_details_json(str(tmp_path))
    assert result is not None
    assert result.name == "app_details.json"


def test_find_latest_details_json_empty(tmp_path):
    result = _mod._find_latest_details_json(str(tmp_path))
    assert result is None


# ---------------------------------------------------------------------------
# draft 파일 생성 검증
# ---------------------------------------------------------------------------

def test_draft_json_created(tmp_path):
    details_json = _make_details_json(tmp_path)
    data = json.loads(details_json.read_text(encoding="utf-8"))
    from scripts.observe_kakao_app_details import _build_permission_draft
    result = _build_permission_draft(data["apps"], tmp_path, "20260426_111834")
    ddir = Path(result["draft_dir"])
    assert (ddir / "draft.json").exists()


def test_draft_md_created(tmp_path):
    details_json = _make_details_json(tmp_path)
    data = json.loads(details_json.read_text(encoding="utf-8"))
    from scripts.observe_kakao_app_details import _build_permission_draft
    result = _build_permission_draft(data["apps"], tmp_path, "20260426_111834")
    ddir = Path(result["draft_dir"])
    assert (ddir / "draft.md").exists()


def test_required_documents_md_created(tmp_path):
    details_json = _make_details_json(tmp_path)
    data = json.loads(details_json.read_text(encoding="utf-8"))
    from scripts.observe_kakao_app_details import _build_permission_draft
    result = _build_permission_draft(data["apps"], tmp_path, "20260426_111834")
    ddir = Path(result["draft_dir"])
    assert (ddir / "required_documents.md").exists()


def test_next_actions_md_created(tmp_path):
    details_json = _make_details_json(tmp_path)
    data = json.loads(details_json.read_text(encoding="utf-8"))
    from scripts.observe_kakao_app_details import _build_permission_draft
    result = _build_permission_draft(data["apps"], tmp_path, "20260426_111834")
    ddir = Path(result["draft_dir"])
    assert (ddir / "next_actions.md").exists()


# ---------------------------------------------------------------------------
# draft 내용 검증
# ---------------------------------------------------------------------------

def test_submit_ready_false(tmp_path):
    details_json = _make_details_json(tmp_path)
    data = json.loads(details_json.read_text(encoding="utf-8"))
    from scripts.observe_kakao_app_details import _build_permission_draft
    result = _build_permission_draft(data["apps"], tmp_path, "20260426_000010")
    drafts = result.get("drafts") or []
    assert all(d["submit_ready"] is False for d in drafts)


def test_review_required_true(tmp_path):
    details_json = _make_details_json(tmp_path)
    data = json.loads(details_json.read_text(encoding="utf-8"))
    from scripts.observe_kakao_app_details import _build_permission_draft
    result = _build_permission_draft(data["apps"], tmp_path, "20260426_000011")
    drafts = result.get("drafts") or []
    assert all(d.get("review_required") is True for d in drafts)


def test_account_email_not_auto_required(tmp_path):
    """account_email은 requested_features에 자동으로 포함되지 않는다."""
    details_json = _make_details_json(tmp_path)
    data = json.loads(details_json.read_text(encoding="utf-8"))
    from scripts.observe_kakao_app_details import _build_permission_draft
    result = _build_permission_draft(data["apps"], tmp_path, "20260426_000012")
    drafts = result.get("drafts") or []
    for d in drafts:
        features = " ".join(d.get("requested_features") or []).lower()
        assert "account_email" not in features, "account_email이 자동으로 필수 포함됨"


def test_account_email_warning_present(tmp_path):
    details_json = _make_details_json(tmp_path)
    data = json.loads(details_json.read_text(encoding="utf-8"))
    from scripts.observe_kakao_app_details import _build_permission_draft
    result = _build_permission_draft(data["apps"], tmp_path, "20260426_000013")
    drafts = result.get("drafts") or []
    for d in drafts:
        assert "account_email_warning" in d, "account_email_warning 필드 없음"
        assert d["account_email_warning"], "account_email_warning가 비어있음"


def test_no_secret_in_draft_json(tmp_path):
    details_json = _make_details_json(tmp_path)
    data = json.loads(details_json.read_text(encoding="utf-8"))
    from scripts.observe_kakao_app_details import _build_permission_draft
    result = _build_permission_draft(data["apps"], tmp_path, "20260426_000014")
    ddir = Path(result["draft_dir"])
    content = (ddir / "draft.json").read_text(encoding="utf-8")
    matches = _SECRET_PATTERN.findall(content)
    assert not matches, f"draft.json에 secret 패턴 감지: {matches[:3]}"


def test_main_from_latest_details(tmp_path):
    """main() --from-latest-details 경로 테스트."""
    _make_details_json(tmp_path)
    sys.argv = [
        "build_kakao_permission_draft.py",
        "--from-latest-details",
        "--out-dir", str(tmp_path),
    ]
    ret = _mod.main()
    assert ret == 0
