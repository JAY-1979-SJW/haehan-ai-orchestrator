import os
from pathlib import Path
from dotenv import load_dotenv

# 명시적 UTF-8 인코딩으로 .env 파일 로드 (인코딩 오류 방지)
load_dotenv(encoding='utf-8')

# LOG_LEVEL — 유효하지 않은 값은 INFO로 대체
_log_level_env = os.environ.get("LOG_LEVEL", "INFO").upper().strip()
LOG_LEVEL = _log_level_env if _log_level_env in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "INFO"

# LOG_DIR — 비어있으면 패키지 내 storage/ 사용
_log_dir_env = os.environ.get("LOG_DIR", "").strip()
LOG_DIR = Path(_log_dir_env) if _log_dir_env else Path(__file__).parent / "storage"
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

# OPENAI_API_KEY — 없으면 MOCK 모드 (openai_client.py에서 처리, 즉시 크래시 안 함)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ── HTTP 인증 (구조 토대만, 실제 강제는 추후 단계) ─────────────────
# Fail closed by default. Tests may monkeypatch this to False, but production
# deployments must keep authentication enabled.
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}

_http_users_env = os.environ.get("HTTP_USERS_PATH", "").strip()
HTTP_USERS_PATH = Path(_http_users_env) if _http_users_env else Path(__file__).parent / "policies" / "http_users.json"

# ── CAD 프록시 ────────────────────────────────────────────────────
# cad-backend(cad-quantity FastAPI) 의 내부 주소. 도커 네트워크 연결 시
# compose 의 cad-quantity_default 외부 네트워크로부터 ``cad-backend`` DNS
# 로 해석된다. 테스트/로컬에서는 env 로 덮어쓴다.
CAD_BACKEND_URL = (
    os.environ.get("CAD_BACKEND_URL", "http://cad-backend:8000").strip()
    or "http://cad-backend:8000"
).rstrip("/")
# 프록시 타임아웃(초). 파서/업로드처럼 긴 호출은 env 로 상향 가능.
try:
    CAD_PROXY_TIMEOUT_SEC = float(os.environ.get("CAD_PROXY_TIMEOUT_SEC", "60"))
    if CAD_PROXY_TIMEOUT_SEC <= 0 or CAD_PROXY_TIMEOUT_SEC > 600:
        raise ValueError()
except (TypeError, ValueError):
    CAD_PROXY_TIMEOUT_SEC = 60.0

# APP_HOST
APP_HOST = os.environ.get("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"

# APP_PORT — 범위 밖이거나 숫자 아니면 기본값 8400
try:
    APP_PORT = int(os.environ.get("APP_PORT", "8400"))
    if not (1 <= APP_PORT <= 65535):
        raise ValueError(f"포트 범위 초과: {APP_PORT}")
except (ValueError, TypeError):
    APP_PORT = 8400

# ── JWT 인증 ────────────────────────────────────────────────────────────────
import secrets as _secrets
JWT_SECRET = os.environ.get("JWT_SECRET", "").strip() or _secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30
