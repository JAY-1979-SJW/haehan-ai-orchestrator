"""사이트별 브라우저 세션 관리 (persistent profile + 세션 메타데이터).

책임:
- 사이트별 고정 프로필 디렉터리(user data dir) 결정/생성
- Playwright persistent context 실행 (매 실행 신규 세션 금지)
- 세션 메타데이터(SessionMeta) 저장/조회
  - status: ACTIVE / EXPIRED / REAUTH_REQUIRED / UNKNOWN
  - last_verified_at / last_reauth_at
- 브라우저 종료 후 재실행 시에도 동일 프로필을 재사용

비-책임 (의도적으로 제외):
- 로그인 자동 수행
- OTP/2차 인증 자동 처리
- 쿠키/스토리지 원문 외부 전송

Playwright 가 없는 환경에서도 import/테스트는 깨지지 않아야 하므로, 실제 브라우저 기동은
`open_persistent_context` 호출 시점에서만 수행한다.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from scripts.browser.session.browser_sandbox_gate import assert_browser_launch_allowed

from . import secrets_policy
from .browser import DEFAULT_HEADLESS, DEFAULT_TIMEOUT_MS

logger = logging.getLogger(__name__)


SessionStatus = Literal["ACTIVE", "EXPIRED", "REAUTH_REQUIRED", "UNKNOWN"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class SessionMeta:
    """세션 상태 메타데이터. 쿠키/토큰 원문은 절대 담지 않는다."""

    site_id: str
    status: SessionStatus = "UNKNOWN"
    last_verified_at: str = ""  # post_login_verify 성공 시 갱신
    last_reauth_at: str = ""  # 재인증 완료 시 갱신
    last_checked_at: str = field(default_factory=_utc_now_iso)
    last_reason: str = ""  # 짧은 코드 (예: "redirected_to_login")
    detected_url: str = ""
    # 재인증 대기 중인 job_id (있을 때만). 감사/복구용.
    paused_job_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_META_LOCK = threading.Lock()


def _meta_read(site_id: str) -> SessionMeta:
    path = secrets_policy.session_meta_path(site_id)
    if not path.is_file():
        return SessionMeta(site_id=site_id, status="UNKNOWN")
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[SESSION-META-READ-FAIL] site=%s err=%s", site_id, type(e).__name__)
        return SessionMeta(site_id=site_id, status="UNKNOWN", last_reason="meta_read_failed")
    # 알 수 없는 필드는 무시, 누락 필드는 기본값으로.
    allowed = {f for f in SessionMeta.__dataclass_fields__}
    data = {k: v for k, v in raw.items() if k in allowed}
    data["site_id"] = site_id
    return SessionMeta(**data)


def _meta_write(meta: SessionMeta) -> None:
    path = secrets_policy.session_meta_path(meta.site_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(meta.to_dict(), f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def get_meta(site_id: str) -> SessionMeta:
    """사이트의 현재 세션 메타데이터 조회."""
    with _META_LOCK:
        return _meta_read(site_id)


def update_meta(  # noqa: PLR0913 - 세션 메타 갱신 공개 함수, 시그니처 유지
    site_id: str,
    *,
    status: SessionStatus | None = None,
    last_verified_at: str | None = None,
    last_reauth_at: str | None = None,
    last_reason: str | None = None,
    detected_url: str | None = None,
    paused_job_id: str | None = None,
) -> SessionMeta:
    """메타데이터 부분 갱신. 제공된 필드만 덮어쓴다."""
    with _META_LOCK:
        meta = _meta_read(site_id)
        if status is not None:
            meta.status = status
        if last_verified_at is not None:
            meta.last_verified_at = last_verified_at
        if last_reauth_at is not None:
            meta.last_reauth_at = last_reauth_at
        if last_reason is not None:
            meta.last_reason = last_reason
        if detected_url is not None:
            meta.detected_url = detected_url
        if paused_job_id is not None:
            meta.paused_job_id = paused_job_id
        meta.last_checked_at = _utc_now_iso()
        _meta_write(meta)
        logger.info(
            "[SESSION-META-UPDATE] site=%s status=%s reason=%s paused_job=%s",
            site_id,
            meta.status,
            meta.last_reason,
            meta.paused_job_id or "-",
        )
        return meta


def mark_active(site_id: str, *, detected_url: str = "") -> SessionMeta:
    now = _utc_now_iso()
    return update_meta(
        site_id,
        status="ACTIVE",
        last_verified_at=now,
        last_reason="verified",
        detected_url=detected_url,
        paused_job_id="",
    )


def mark_reauth_required(
    site_id: str,
    *,
    reason: str,
    detected_url: str = "",
    paused_job_id: str = "",
) -> SessionMeta:
    return update_meta(
        site_id,
        status="REAUTH_REQUIRED",
        last_reason=reason,
        detected_url=detected_url,
        paused_job_id=paused_job_id,
    )


def mark_reauth_success(site_id: str, *, detected_url: str = "") -> SessionMeta:
    now = _utc_now_iso()
    return update_meta(
        site_id,
        status="ACTIVE",
        last_verified_at=now,
        last_reauth_at=now,
        last_reason="reauth_succeeded",
        detected_url=detected_url,
        paused_job_id="",
    )


def mark_expired(site_id: str, *, reason: str = "session_expired") -> SessionMeta:
    return update_meta(site_id, status="EXPIRED", last_reason=reason)


# ── Persistent browser context ────────────────────────────────────
def ensure_profile_dir(site_id: str) -> Path:
    """사이트별 프로필 디렉터리 보장. 존재하지 않으면 생성."""
    profile = secrets_policy.browser_profile_dir(site_id)
    profile.mkdir(parents=True, exist_ok=True)
    return profile


@contextmanager
def open_persistent_context(
    site_id: str,
    *,
    headless: bool = DEFAULT_HEADLESS,
    default_timeout_ms: int = DEFAULT_TIMEOUT_MS,
    playwright_sync_api: Any = None,
) -> Iterator[Any]:
    """사이트 고정 프로필로 persistent chromium context 를 연다.

    Playwright 를 동적으로 import. 설치되지 않았거나 launch 실패 시
    RuntimeError 를 발생시킨다 (호출자가 처리).

    `playwright_sync_api` 는 테스트에서 실제 Playwright 없이 주입하기 위한 hook.
    """
    if not secrets_policy.is_safe_site_name(site_id):
        raise ValueError(f"invalid site_id: {site_id!r}")

    profile_dir = ensure_profile_dir(site_id)

    if playwright_sync_api is None:
        try:
            from playwright import sync_api as _sync_api  # type: ignore
        except Exception as e:
            raise RuntimeError(f"playwright import 실패: {type(e).__name__}") from e
        playwright_sync_api = _sync_api

    logger.info(
        "[SESSION-OPEN] site=%s profile=%s headless=%s",
        site_id,
        profile_dir.name,
        headless,
    )
    pw_cm = playwright_sync_api.sync_playwright()
    pw = pw_cm.start()
    try:
        assert_browser_launch_allowed(
            component="ai_orchestrator.sites.session_manager", action="playwright_persistent_context"
        )
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
        )
        with suppress(Exception):  # mock 에서 없을 수 있음
            context.set_default_timeout(default_timeout_ms)
        try:
            yield context
        finally:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                logger.warning("[SESSION-CLOSE-ERR] site=%s", site_id)
    finally:
        with suppress(Exception):  # playwright 종료 정리, 실패해도 프로세스 종료에 영향 없음
            pw.stop()


def clear_meta_for_tests(site_id: str) -> None:
    """테스트 전용 — 메타데이터 파일 삭제 (프로필은 보존)."""
    path = secrets_policy.session_meta_path(site_id)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


__all__ = [
    "SessionMeta",
    "SessionStatus",
    "clear_meta_for_tests",
    "ensure_profile_dir",
    "get_meta",
    "mark_active",
    "mark_expired",
    "mark_reauth_required",
    "mark_reauth_success",
    "open_persistent_context",
    "update_meta",
]
