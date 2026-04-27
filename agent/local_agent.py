"""상시 실행 로컬 에이전트 (B안 4단계 — 운영 안정화).

3단계 대비 추가된 것:
- 승인형 실행 게이트 (``approval_policy``) : fetch → gate → execute.
- 결과 재전송 spool (``result_spool``) : report 실패 시 로컬 보관 후
  다음 루프 시작 때 재시도.
- 감사 로그 필드 통일 : id / action / category / risk_level / approved /
  approved_by / ok / error / started_at / finished_at / duration_ms
  (+ idempotency_key — 서버측 중복 전송 탐지용).
- 민감 키(``approval_token``, ``token``, ``session`` 등) 자동 스크럽.

환경변수:
    AGENT_API_URL       서버 base URL
    AGENT_TOKEN         Bearer 토큰
    AGENT_POLL_SECONDS  (선택) 빈 큐 대기 시간
    AGENT_SPOOL_DIR     (선택) 재전송 spool 경로
    AGENT_WORK_DIR      입력 파일 허용 base
    AGENT_OUTPUT_DIR    save_as 허용 base
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from . import api_client, approval_policy, result_spool, task_executor

logger = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 5.0

_SENSITIVE_KEY_PARTS = (
    "password", "token", "secret", "cookie",
    "session", "authorization", "apikey", "api_key",
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_config(
    api_url: Optional[str], token: Optional[str],
    poll_seconds: Optional[float], spool_dir: Optional[Path],
) -> Tuple[str, str, float, Path]:
    api = (api_url or os.environ.get("AGENT_API_URL", "") or "").strip()
    tok = token if token is not None else os.environ.get("AGENT_TOKEN", "")
    try:
        poll = float(
            poll_seconds if poll_seconds is not None
            else os.environ.get("AGENT_POLL_SECONDS", DEFAULT_POLL_SECONDS)
        )
    except (TypeError, ValueError):
        poll = DEFAULT_POLL_SECONDS
    sp = spool_dir
    if sp is None:
        env_sp = os.environ.get("AGENT_SPOOL_DIR", "").strip()
        sp = Path(env_sp) if env_sp else result_spool.DEFAULT_SPOOL_DIR
    else:
        sp = Path(sp)
    return api, tok, poll, sp


def _is_sensitive_key(key) -> bool:
    if not isinstance(key, str):
        return False
    low = key.lower()
    return any(s in low for s in _SENSITIVE_KEY_PARTS)


def _scrub(value):
    """민감 키를 재귀적으로 제거. 로그/서버 전송 전에 적용."""
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()
                if not _is_sensitive_key(k)}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _idempotency_key(task_id: str, started_at: str) -> str:
    raw = f"{task_id}|{started_at}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def fetch_task(api_url: str, token: str) -> Tuple[Optional[dict], Optional[str]]:
    """서버 API 에서 task 한 건 pull."""
    return api_client.fetch_task(api_url, token)


def execute_task(task: dict) -> dict:
    """task_executor 에 위임 (승인/경로 체크는 상위 루프에서 수행)."""
    out = task_executor.execute_task(task)
    return {
        "ok": bool(out.get("ok")),
        "data": _scrub(out.get("data", {})),
        "error": out.get("error"),
    }


def report_result(api_url: str, token: str, result: dict) -> Optional[str]:
    """서버 API 로 결과 POST."""
    return api_client.report_result(api_url, token, result)


def _build_result(
    task: dict, decision: approval_policy.Decision,
    exec_out: Optional[dict], started_at: str, start_mono: float,
) -> dict:
    finished_at = _iso_now()
    duration_ms = int((time.monotonic() - start_mono) * 1000)
    task_id = (task.get("id") if isinstance(task, dict) else "") or ""
    action = (task.get("action") if isinstance(task, dict) else "") or ""

    if exec_out is None:
        ok = False
        data: dict = {}
        error = decision.error
    else:
        ok = bool(exec_out.get("ok"))
        data = exec_out.get("data") or {}
        error = exec_out.get("error")

    return {
        "id": task_id,
        "action": action,
        "category": decision.category,
        "risk_level": decision.risk_level,
        "approved": bool(decision.approved),
        "approved_by": decision.approved_by,
        "ok": ok,
        "data": _scrub(data),
        "error": error,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "idempotency_key": _idempotency_key(task_id, started_at),
    }


def _send_or_spool(
    api_url: str, token: str, spool_dir: Path, result: dict,
) -> Optional[str]:
    """결과를 서버에 보내고, 실패 시 spool 에 enqueue 한다."""
    err = report_result(api_url, token, result)
    if err is None:
        return None
    logger.warning(
        "report_result failed (%s) — spooling result id=%s for retry",
        err, result.get("id"),
    )
    try:
        result_spool.enqueue_failed_result(spool_dir, result)
    except OSError as e:
        logger.error("spool enqueue failed: %s", e)
    return err


def run_agent_loop(
    api_url: Optional[str] = None,
    token: Optional[str] = None,
    *,
    poll_seconds: Optional[float] = None,
    max_iterations: Optional[int] = None,
    stop_file: Optional[Path] = None,
    spool_dir: Optional[Path] = None,
) -> int:
    """메인 루프.

    한 iteration 흐름:
        1) flush_spooled_results   (이전 실패분 재전송)
        2) fetch_task              (서버에서 다음 작업 pull)
        3) approval_policy.evaluate (경로/승인 게이트)
        4) task_executor.execute_task (허용된 경우만)
        5) report_result
        6) 실패 시 result_spool 에 보관 → 다음 주기 1) 단계가 재시도
    """
    api_url, token, poll_seconds, spool_dir = _resolve_config(
        api_url, token, poll_seconds, spool_dir,
    )
    if not api_url:
        raise ValueError("AGENT_API_URL is required (env or parameter)")

    processed = 0
    iteration = 0
    while True:
        if max_iterations is not None and iteration >= max_iterations:
            break
        if stop_file is not None and Path(stop_file).exists():
            logger.info("stop_file detected, exiting loop")
            break
        iteration += 1

        # 1) 이전 실패 결과 재전송
        try:
            flushed = result_spool.flush_spooled_results(
                spool_dir, api_url, token,
            )
            if flushed:
                logger.info("flushed %d spooled result(s)", flushed)
        except Exception as e:  # noqa: BLE001
            logger.exception("spool flush crashed (non-fatal): %s", e)

        # 2) 다음 task pull
        task, fetch_err = fetch_task(api_url, token)
        if fetch_err:
            logger.warning("fetch_task failed: %s — sleep and retry", fetch_err)
            time.sleep(max(0.0, poll_seconds))
            continue
        if task is None:
            time.sleep(max(0.0, poll_seconds))
            continue

        started_at = _iso_now()
        start_mono = time.monotonic()

        # 3) 승인/경로 게이트
        decision = approval_policy.evaluate(task)
        logger.info(
            "task gated: id=%s action=%s risk=%s allowed=%s error=%s",
            task.get("id"), task.get("action"),
            decision.risk_level, decision.allowed, decision.error,
        )

        if not decision.allowed:
            # 게이트에서 차단된 task 도 결과로 서버에 알려야 감사 기록이 남는다.
            result = _build_result(
                task, decision, exec_out=None,
                started_at=started_at, start_mono=start_mono,
            )
        else:
            # 4) 실행
            try:
                exec_out = execute_task(task)
            except Exception as e:  # noqa: BLE001
                logger.exception("execute_task crashed: %s", e)
                exec_out = {
                    "ok": False, "data": {},
                    "error": f"execute_crashed:{type(e).__name__}",
                }
            result = _build_result(
                task, decision, exec_out=exec_out,
                started_at=started_at, start_mono=start_mono,
            )

        # 5~6) report 또는 spool
        _send_or_spool(api_url, token, spool_dir, result)
        try:
            print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception:  # noqa: BLE001
            pass
        processed += 1

    return processed


__all__ = [
    "DEFAULT_POLL_SECONDS",
    "fetch_task",
    "execute_task",
    "report_result",
    "run_agent_loop",
]
