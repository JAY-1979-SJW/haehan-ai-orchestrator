import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# LOG_LEVEL — 유효하지 않은 값은 INFO로 대체
_log_level_env = os.environ.get("LOG_LEVEL", "INFO").upper().strip()
LOG_LEVEL = _log_level_env if _log_level_env in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "INFO"

# LOG_DIR — 비어있으면 패키지 내 storage/ 사용
_log_dir_env = os.environ.get("LOG_DIR", "").strip()
LOG_DIR = Path(_log_dir_env) if _log_dir_env else Path(__file__).parent / "storage"
AUDIT_LOG_PATH = LOG_DIR / "audit_logs.jsonl"
APPROVAL_STORE_PATH = LOG_DIR / "approval_tokens.jsonl"
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
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

_http_users_env = os.environ.get("HTTP_USERS_PATH", "").strip()
HTTP_USERS_PATH = Path(_http_users_env) if _http_users_env else Path(__file__).parent / "policies" / "http_users.json"

# APP_HOST
APP_HOST = os.environ.get("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"

# APP_PORT — 범위 밖이거나 숫자 아니면 기본값 8400
try:
    APP_PORT = int(os.environ.get("APP_PORT", "8400"))
    if not (1 <= APP_PORT <= 65535):
        raise ValueError(f"포트 범위 초과: {APP_PORT}")
except (ValueError, TypeError):
    APP_PORT = 8400
