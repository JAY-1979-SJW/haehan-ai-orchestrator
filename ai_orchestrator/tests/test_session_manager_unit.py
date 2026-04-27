"""SessionMeta JSON roundtrip + 경로 정책 검증 — 외부 접속 없음."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_orchestrator.sites import session_manager
from ai_orchestrator.sites.session_manager import SessionMeta
from ai_orchestrator.sites import secrets_policy


# ── SessionMeta JSON roundtrip ────────────────────────────────────
class TestSessionMetaRoundtrip:
    def test_to_dict_and_reconstruct(self) -> None:
        meta = SessionMeta(
            site_id="test_site",
            status="ACTIVE",
            last_verified_at="2026-01-01T00:00:00+00:00",
            last_reauth_at="",
            last_reason="verified",
            detected_url="https://example.test/",
            paused_job_id="",
        )
        d = meta.to_dict()
        assert d["site_id"] == "test_site"
        assert d["status"] == "ACTIVE"
        serialized = json.dumps(d)
        reloaded = json.loads(serialized)
        assert reloaded["site_id"] == "test_site"
        assert reloaded["status"] == "ACTIVE"

    def test_no_sensitive_fields_in_dict(self) -> None:
        meta = SessionMeta(site_id="test_site", status="UNKNOWN")
        d = meta.to_dict()
        for bad in ("password", "token", "cookie", "session_token",
                    "secret", "otp", "auth_header"):
            assert bad not in d, f"민감 필드 발견: {bad}"

    def test_default_status_unknown(self) -> None:
        meta = SessionMeta(site_id="test_site")
        assert meta.status == "UNKNOWN"

    def test_paused_job_id_is_non_sensitive_string(self) -> None:
        meta = SessionMeta(site_id="s", paused_job_id="job-123")
        d = meta.to_dict()
        assert d["paused_job_id"] == "job-123"


# ── 경로가 지정 root 아래로만 생성되는지 ─────────────────────────
class TestSessionMetaPath:
    def test_meta_path_under_meta_root(self, tmp_path: Path) -> None:
        meta_root = tmp_path / "session_meta"
        with patch.dict(os.environ, {"SESSION_META_ROOT": str(meta_root)}):
            path = secrets_policy.session_meta_path("test_site")
        assert str(path).startswith(str(meta_root))
        assert path.name == "test_site.json"

    def test_profile_dir_under_profile_root(self, tmp_path: Path) -> None:
        profile_root = tmp_path / "browser_profiles"
        with patch.dict(os.environ, {"BROWSER_PROFILE_ROOT": str(profile_root)}):
            path = secrets_policy.browser_profile_dir("test_site")
        assert str(path).startswith(str(profile_root))
        assert path.name == "test_site"

    def test_invalid_site_name_raises(self) -> None:
        with pytest.raises(ValueError):
            secrets_policy.session_meta_path("../evil")

    def test_invalid_profile_name_raises(self) -> None:
        with pytest.raises(ValueError):
            secrets_policy.browser_profile_dir("../evil")


# ── get_meta / update_meta (tmp_path 격리) ────────────────────────
class TestGetUpdateMeta:
    def test_get_meta_returns_unknown_when_no_file(self, tmp_path: Path) -> None:
        meta_root = tmp_path / "session_meta"
        with patch.dict(os.environ, {"SESSION_META_ROOT": str(meta_root)}):
            meta = session_manager.get_meta("new_site")
        assert meta.status == "UNKNOWN"
        assert meta.site_id == "new_site"

    def test_update_meta_writes_under_tmp(self, tmp_path: Path) -> None:
        meta_root = tmp_path / "session_meta"
        with patch.dict(os.environ, {"SESSION_META_ROOT": str(meta_root)}):
            updated = session_manager.update_meta("s1", status="ACTIVE", last_reason="verified")
        assert updated.status == "ACTIVE"
        assert updated.last_reason == "verified"
        # 파일이 tmp_path 하위에 생성됐어야 함
        written = meta_root / "s1.json"
        assert written.exists()
        data = json.loads(written.read_text(encoding="utf-8"))
        assert data["status"] == "ACTIVE"
        for bad in ("password", "token", "cookie", "secret"):
            assert bad not in data
