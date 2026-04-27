"""cad-mcp 환경변수 설정.

read / write 경로 분리 원칙:
  - 읽기(GET): CAD_BACKEND_URL 직통 — MCP_ALLOW_DIRECT_READ=true 기본
  - 쓰기(POST/PATCH/DELETE): ORCHESTRATOR_URL 경유 필수
    MCP_ALLOW_DIRECT_WRITE 는 코드 레벨에서 False 로 하드락.
    env 로 변경 불가 — 변경 시 PR 리뷰 필요.
"""
from __future__ import annotations

import os


def _bool_env(name: str, default: bool) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v in {"true", "1", "yes", "on"}:
        return True
    if v in {"false", "0", "no", "off"}:
        return False
    return default


def _float_env(name: str, default: float, lo: float = 1.0, hi: float = 600.0) -> float:
    try:
        v = float(os.environ.get(name, str(default)))
        return v if lo <= v <= hi else default
    except (TypeError, ValueError):
        return default


# ── upstream 주소 ─────────────────────────────────────────────────────
CAD_BACKEND_URL: str = (
    os.environ.get("CAD_BACKEND_URL", "http://cad-backend:8000").strip()
    or "http://cad-backend:8000"
).rstrip("/")

# write 필수 — 미설정 시 빈 문자열 → write_guard 가 즉시 차단
# 컨테이너 환경에서는 docker-compose env 로 명시적으로 설정할 것.
# fallback 을 두면 미설정 시 잘못된 호스트로 HTTP 호출 후 네트워크 에러가 발생하는
# 불명확한 실패 모드가 생기므로 의도적으로 제거함.
ORCHESTRATOR_URL: str = os.environ.get("ORCHESTRATOR_URL", "").strip().rstrip("/")

# ── read/write 정책 플래그 ────────────────────────────────────────────
# read: env 로 비활성화 가능 (기본 허용)
MCP_ALLOW_DIRECT_READ: bool = _bool_env("MCP_ALLOW_DIRECT_READ", default=True)

# write: 코드 레벨 하드락 — env 로 절대 변경 불가.
# "MCP_ALLOW_DIRECT_WRITE=true" 를 env 에 넣어도 아무 효과 없음.
# 이 상수를 True 로 바꾸려면 코드 변경 + PR 리뷰가 필요하다.
MCP_ALLOW_DIRECT_WRITE: bool = False  # HARD-LOCKED — DO NOT CHANGE WITHOUT REVIEW

# write 시 approval token 요구 — 코드 레벨 하드락
MCP_REQUIRE_APPROVAL_FOR_WRITE: bool = True  # HARD-LOCKED

# ── 내부 서비스 인증 (orchestrator 호출용 서비스 계정) ──────────────────
# operator 이상 권한 서비스 계정. orchestrator Basic Auth 요구 시 사용.
# 비어있으면 no-auth (orchestrator AUTH_ENABLED=false 환경용).
MCP_ORCHESTRATOR_USER: str = os.environ.get("MCP_ORCHESTRATOR_USER", "").strip()
MCP_ORCHESTRATOR_PASS: str = os.environ.get("MCP_ORCHESTRATOR_PASS", "").strip()

# orchestrator 가 audit 로그에 기록하는 실사용자 헤더명
MCP_ACTOR_HEADER: str = "X-MCP-Actor"

# ── 타임아웃 ─────────────────────────────────────────────────────────
READ_TIMEOUT_SEC: float = _float_env("MCP_READ_TIMEOUT_SEC", default=30.0)
WRITE_TIMEOUT_SEC: float = _float_env("MCP_WRITE_TIMEOUT_SEC", default=60.0)

# ── 스토리지 ─────────────────────────────────────────────────────────
STORAGE_ROOT: str = os.environ.get("STORAGE_ROOT", "/storage").strip() or "/storage"
