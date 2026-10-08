import copy
import logging
import logging.handlers
import re

from .config import LOG_DIR, LOG_LEVEL

_initialized = False


def setup_logging() -> logging.Logger:
    global _initialized
    root = logging.getLogger("ai_orchestrator")
    if _initialized:
        return root

    root.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            LOG_DIR / "app.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as e:
        root.warning("앱 로그 파일 핸들러 초기화 실패: %s", e)

    _initialized = True
    return root


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


# ── 비밀값 마스킹 ─────────────────────────────────────────────────────────────
# uvicorn 접근 로그(uvicorn.access)와 WebSocket 접속 줄(uvicorn.error)은 요청 경로를 쿼리 문자열째 기록한다.
# 옛 클라이언트가 ?license=<데스크톱 키> 로 접속하면 키가 fastapi.log 에 평문으로 남는다(2026-10-08 실측).
# 새 클라이언트는 헤더로 보내지만, 옛 클라이언트·외부 호출 대비로 기록 직전에 값을 가린다.
_SECRET_QUERY_RE = re.compile(
    r"(?i)([?&](?:license|license_key|device_token|access_token|token|api_key|apikey|password|secret)=)[^&\s\"']+"
)


def mask_secrets(text: str) -> str:
    """URL 쿼리의 비밀값(license=, token= 등)을 ***로 바꾼다."""
    return _SECRET_QUERY_RE.sub(r"\g<1>***", text)


class MaskSecretsFilter(logging.Filter):
    """로그 레코드의 메시지·인자(문자열)에서 쿼리 비밀값을 가린다. 인자 개수·순서는 유지(uvicorn AccessFormatter 호환)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_secrets(record.msg)
        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(mask_secrets(a) if isinstance(a, str) else a for a in args)
        elif isinstance(args, dict):
            record.args = {k: mask_secrets(v) if isinstance(v, str) else v for k, v in args.items()}
        return True


def uvicorn_log_config() -> dict:
    """uvicorn 기본 로깅 설정에 MaskSecretsFilter 를 모든 핸들러에 붙인 사본."""
    from uvicorn.config import LOGGING_CONFIG

    cfg = copy.deepcopy(LOGGING_CONFIG)
    cfg.setdefault("filters", {})["mask_secrets"] = {"()": f"{__name__}.MaskSecretsFilter"}
    for handler in cfg.get("handlers", {}).values():
        handler.setdefault("filters", []).append("mask_secrets")
    return cfg
