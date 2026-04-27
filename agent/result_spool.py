"""결과 재전송 spool (B안 4단계 운영 안정화).

``report_result`` 이 실패할 때 결과 JSON 을 로컬 디스크에 1파일/1건으로
저장하고, 다음 루프에서 flush 를 시도한다. agent 가 crash 후 재시작해도
spool 디렉터리에 남은 파일을 그대로 재전송할 수 있다.

정책
----
- **idempotency_key** 을 파일명으로 사용해 같은 결과가 두 번 spool 되지
  않도록 한다. (``enqueue_failed_result`` 은 기존 파일이 있으면 no-op.)
- flush 중 **API 실패** 가 나오면 즉시 중단해 나머지를 유지한다. 다음
  루프에서 재시도.
- spool 파일이 손상되면(JSON 파싱 실패) 조용히 삭제하고 다음 파일로 진행
  — 무한 재시도 막기.
- 이 모듈은 agent 의 local storage 와 독립되어 있으며 ``agent.errors``
  체계와 엮이지 않는다 (api_client 의 err_code 와만 상호작용).
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from . import api_client

logger = logging.getLogger(__name__)

DEFAULT_SPOOL_DIR = Path(r"C:\tmp\excel_poc\spool")
_FILE_SUFFIX = ".result.json"


def _safe_name(idempotency_key: Optional[str]) -> str:
    """idempotency_key 를 파일명 안전 문자로 정규화."""
    key = (idempotency_key or uuid.uuid4().hex[:16])[:64]
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "_" for c in key)
    return f"{cleaned}{_FILE_SUFFIX}"


def enqueue_failed_result(spool_dir: Path, result: dict) -> Path:
    """result 를 spool 디렉터리에 저장. 동일 idempotency_key 는 no-op."""
    spool_dir = Path(spool_dir)
    spool_dir.mkdir(parents=True, exist_ok=True)
    target = spool_dir / _safe_name(result.get("idempotency_key"))
    if target.exists():
        logger.debug("spool already has key=%s", result.get("idempotency_key"))
        return target
    target.write_text(
        json.dumps(result, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("spooled result for retry: %s", target.name)
    return target


def list_spooled_results(spool_dir: Path) -> list[Path]:
    spool_dir = Path(spool_dir)
    if not spool_dir.exists():
        return []
    return sorted(spool_dir.glob(f"*{_FILE_SUFFIX}"))


def flush_spooled_results(
    spool_dir: Path, api_url: str, token: str,
) -> int:
    """spool 을 순회하며 재전송. 성공한 파일은 삭제, API 실패 시 즉시 중단.

    Returns:
        성공적으로 전송되어 삭제된 파일 개수.
    """
    if not api_url:
        return 0
    sent = 0
    for p in list_spooled_results(spool_dir):
        try:
            body = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("spool file corrupt, discarding: %s (%s)", p.name, e)
            try:
                p.unlink()
            except OSError:
                pass
            continue
        if not isinstance(body, dict):
            logger.warning("spool file not a dict, discarding: %s", p.name)
            try:
                p.unlink()
            except OSError:
                pass
            continue
        err = api_client.report_result(api_url, token, body)
        if err is None:
            try:
                p.unlink()
                sent += 1
            except OSError as e:
                logger.warning("spool cleanup failed for %s: %s", p.name, e)
        else:
            logger.info(
                "flush halted at %s (err=%s), %d file(s) remain for retry",
                p.name, err, len(list_spooled_results(spool_dir)),
            )
            break
    return sent


__all__ = [
    "DEFAULT_SPOOL_DIR",
    "enqueue_failed_result",
    "flush_spooled_results",
    "list_spooled_results",
]
