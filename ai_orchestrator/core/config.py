import os
import re
import secrets as _secrets
from pathlib import Path

from dotenv import load_dotenv

from ai_orchestrator.paths.runtime import atomic_write_text, data_dir, storage_dir

# 명시적 UTF-8 인코딩으로 .env 파일 로드 (인코딩 오류 방지)
load_dotenv(encoding="utf-8")

# LOG_LEVEL — 유효하지 않은 값은 INFO로 대체
_log_level_env = os.environ.get("LOG_LEVEL", "INFO").upper().strip()
LOG_LEVEL = _log_level_env if _log_level_env in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "INFO"

# LOG_DIR — 비어있으면 패키지 내 storage/ 사용
_log_dir_env = os.environ.get("LOG_DIR", "").strip()
LOG_DIR = Path(_log_dir_env) if _log_dir_env else storage_dir()
AUDIT_LOG_PATH = LOG_DIR / "audit_logs.jsonl"
APPROVAL_STORE_PATH = LOG_DIR / "approval_tokens.jsonl"
APPROVAL_RECORD_STORE_PATH = LOG_DIR / "approval_records.jsonl"
AUDIT_RECORD_STORE_PATH = LOG_DIR / "audit_records.jsonl"
INBOX_PATH = LOG_DIR / "inbox.jsonl"
EXECUTION_HISTORY_PATH = LOG_DIR / "execution_history.jsonl"


# ── 실행 리밋 (low 위험 인라인 실행에만 적용) ─────────────────────
# 보수적 기본값: 짧은 시간 내 동일 action/사용자 반복 차단, 실행 시간 상한
def _env_int(name: str, default: int, lo: int = 1, hi: int = 3600) -> int:
    try:
        v = int(os.environ.get(name, str(default)))
        return v if lo <= v <= hi else default
    except (TypeError, ValueError):
        return default


EXEC_RATE_LIMIT_WINDOW_SEC = _env_int("EXEC_RATE_LIMIT_WINDOW_SEC", 60, 1, 3600)
EXEC_RATE_LIMIT_ACTION_MAX = _env_int("EXEC_RATE_LIMIT_ACTION_MAX", 3, 1, 1000)
EXEC_RATE_LIMIT_USER_MAX = _env_int("EXEC_RATE_LIMIT_USER_MAX", 5, 1, 1000)
EXEC_TIMEOUT_SEC = _env_int("EXEC_TIMEOUT_SEC", 10, 1, 600)

# Gmail OAuth2 인증 파일 경로 (비어있으면 storage/ 기본값)
_gcred = os.environ.get("GMAIL_CREDENTIALS_PATH", "").strip()
GMAIL_CREDENTIALS_PATH = Path(_gcred) if _gcred else LOG_DIR / "gmail_credentials.json"
_gtok = os.environ.get("GMAIL_TOKEN_PATH", "").strip()
GMAIL_TOKEN_PATH = Path(_gtok) if _gtok else LOG_DIR / "gmail_token.json"


# ── HTTP 인증 (구조 토대만, 실제 강제는 추후 단계) ─────────────────
# Fail closed by default. Tests may monkeypatch this to False, but production
# deployments must keep authentication enabled.
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}

_http_users_env = os.environ.get("HTTP_USERS_PATH", "").strip()
HTTP_USERS_PATH = (
    Path(_http_users_env) if _http_users_env else Path(__file__).resolve().parents[1] / "policies" / "http_users.json"
)

# ── CAD 프록시 ────────────────────────────────────────────────────
# cad-backend(cad-quantity FastAPI) 의 내부 주소. 도커 네트워크 연결 시
# compose 의 cad-quantity_default 외부 네트워크로부터 ``cad-backend`` DNS
# 로 해석된다. 테스트/로컬에서는 env 로 덮어쓴다.
CAD_BACKEND_URL = (
    os.environ.get("CAD_BACKEND_URL", "http://cad-backend:8000").strip() or "http://cad-backend:8000"
).rstrip("/")
# 프록시 타임아웃(초). 파서/업로드처럼 긴 호출은 env 로 상향 가능.
try:
    CAD_PROXY_TIMEOUT_SEC = float(os.environ.get("CAD_PROXY_TIMEOUT_SEC", "60"))
    if CAD_PROXY_TIMEOUT_SEC <= 0 or CAD_PROXY_TIMEOUT_SEC > 600:
        raise ValueError()
except (TypeError, ValueError):
    CAD_PROXY_TIMEOUT_SEC = 60.0

# APP_HOST — 데스크톱(frozen) 앱만 loopback 강제(외부 접근 차단). 서버/개발은 명시값 존중.
import sys as _sys  # noqa: E402

_env_host = os.environ.get("APP_HOST", "127.0.0.1").strip()
_is_desktop = getattr(_sys, "frozen", False)  # PyInstaller 패키지 앱
if _is_desktop and _env_host in ("", "0.0.0.0", "::"):  # noqa: S104
    APP_HOST = "127.0.0.1"  # 데스크톱: 0.0.0.0/:: 입력돼도 loopback으로 교정
else:
    APP_HOST = _env_host or "127.0.0.1"

# APP_PORT — 범위 밖이거나 숫자 아니면 기본값 8401
# 2026-09-30 수정(defect_index #18): 이 파일이 "진짜 단일 소스"여야 하는데 기본값 자체가
# 8400 이었다 — 실제 운영 포트는 8401(CLAUDE.md "로컬 개발 스택 포트 구성" 문서, 오늘까지
# uvicorn 기동 시 매번 --port 8401 을 명령줄에서 명시해 이 잘못된 기본값을 계속 우회해왔다).
# core/agent_runtime/common/config.py 등 다른 파일들의 기본값 불일치(같은 defect_index #18)도 결국 이
# "정본" 자체가 틀렸던 게 근본 원인이었다.
try:
    APP_PORT = int(os.environ.get("APP_PORT", "8401"))
    if not (1 <= APP_PORT <= 65535):
        raise ValueError(f"포트 범위 초과: {APP_PORT}")
except (ValueError, TypeError):
    APP_PORT = 8401

# ── JWT 인증 ────────────────────────────────────────────────────────────────
_JWT_SECRET_FILE_NAME = "jwt_secret.key"


def _load_or_create_persisted_jwt_secret() -> str:
    """JWT_SECRET 환경변수가 없을 때 쓰는 영속 비밀 — storage_dir()/jwt_secret.key.

    결함(2026-10-10): env 없으면 매 import(=매 프로세스 시작)마다 secrets.token_hex(32)
    로 새 비밀을 만들어, 서버를 재시작하면 그 전에 발급한 토큰이 전부 무효화됐다. 파일에
    한 번 만든 값을 저장해 재사용 — tmp+rename 원자적 쓰기, 생성 시 0o600(소유자 전용).
    storage_dir() 는 .gitignore:110(`storage/`)로 이미 커밋 차단된다.
    """
    path = storage_dir() / _JWT_SECRET_FILE_NAME
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    new_secret = _secrets.token_hex(32)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, new_secret)
        os.chmod(path, 0o600)
    except OSError:
        pass  # 파일 쓰기 실패해도 이번 프로세스는 이 값으로 계속 동작(재시작 시 또 바뀔 위험만 남음)
    return new_secret


_JWT_SECRET_ENV = os.environ.get("JWT_SECRET", "").strip()
JWT_SECRET_CONFIGURED = bool(_JWT_SECRET_ENV)  # False 면 영속 파일 비밀(위) 사용
JWT_SECRET = _JWT_SECRET_ENV or _load_or_create_persisted_jwt_secret()
# true 면 AUTH_ENABLED 인데 JWT_SECRET 이 없을 때 서버가 시작하지 않는다(asgi._check_jwt_secret). 기본 false = 경고만.
JWT_SECRET_REQUIRED = os.environ.get("JWT_SECRET_REQUIRED", "").strip().lower() in {"1", "true", "yes", "on"}
JWT_SECRET_MIN_LENGTH = 32
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30


def parse_owner_emails(raw: str) -> frozenset[str]:
    """OWNER_EMAILS(쉼표·세미콜론·공백 구분) → 소문자 이메일 집합. '@' 가 하나가 아니거나 앞뒤가 빈 항목은 버린다.

    가입 시 이메일은 소문자·공백 제거로 저장되므로 같은 기준으로 맞춘다. 별칭(`+tag`, gmail 점)은 정규화하지 않는다(정확히 같은 주소만)."""
    items = (item.strip().lower() for item in re.split(r"[,;\s]+", raw or ""))
    return frozenset(item for item in items if item.count("@") == 1 and all(item.split("@")))


# 이 이메일의 '승인된 활성 계정'은 DB role 과 무관하게 owner 로 취급한다(gates/auth.py 에서 판정 시점에만 적용, DB 는 안 바꿈).
# 비어 있으면 기존 동작 그대로. 값은 재시작해야 바뀐다.
OWNER_EMAILS = parse_owner_emails(os.environ.get("OWNER_EMAILS", ""))

# ── 로컬 대용량 데이터 루트 ──────────────────────────────────────────────────
# .env의 LOCAL_DATA_DIR을 매 호출마다 재읽어 경로 변경 시 재시작 불필요.
# 설정 예) LOCAL_DATA_DIR=C:\Users\skyjw\OneDrive\_local_data
_DEFAULT_DATA_DIR = data_dir()


def get_local_data_dir() -> Path:
    load_dotenv(override=True, encoding="utf-8")
    v = os.environ.get("LOCAL_DATA_DIR", "").strip()
    return Path(v) if v else _DEFAULT_DATA_DIR


# 모듈 임포트 시 1회 평가 (하위 호환). 실시간이 필요한 곳은 get_local_data_dir() 직접 호출.
LOCAL_DATA_DIR: Path = get_local_data_dir()
