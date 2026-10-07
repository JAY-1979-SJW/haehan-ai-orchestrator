"""발행·발송 공용 실패 기록·알림 래퍼 (L5 site_module — 여러 도메인이 공용으로 쓰는 조합 모듈).

기존 장치를 재사용만 한다(신규 채널 금지):
  - 기록: scripts/common/op_log.py(L7) log_op — 파일(data/logs/ops.log) + DB(data/cdp.db)
  - 알림: ai_orchestrator/core/telegram_sender.py(L3) send_message —
    TELEGRAM_BOT_TOKEN/TELEGRAM_APPROVER_CHAT_ID 미설정 시 자동 skip(예외 없음)

L5 는 allowed_deps 상 L3·L7 을 모두 허용하므로 이 조합을 여기(L5)에 둔다
(2026-09-26 기준서 docs/specs/2026-09-26_maturity_fix_batch1.md 3번, D3 결정).

사용법:
    from scripts.common.publish_guard import guarded_publish, guarded

    # 1) 컨텍스트 매니저 — 예외 전파형(반환값 그대로, 실패 시 기록+알림 후 raise)
    with guarded_publish("ig_publish"):
        return publish_reel(...)

    # 2) 데코레이터 — 예외형 + {"ok": False} 류 반환형 모두 지원
    @guarded("youtube_upload", ok_fn=lambda r: r[0]["status"] != "failed")
    def execute_upload_plan(...): ...

주의:
  - 성공 경로의 동작·반환값은 절대 바꾸지 않는다. 예외는 기록·알림 후 반드시 다시 raise 한다.
  - 알림 본문에 토큰·OAuth·이메일 원문 등 비밀값을 넣지 않는다(길이 300자 절단).
  - 알림 자체가 실패해도(텔레그램 API 오류 등) 원래 작업 흐름을 절대 깨지 않는다 —
    실패는 stderr 로만 남긴다.
"""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any

from scripts.common.op_log import log_op

_NOTIFY_PREFIX = "❌"  # ❌


def _notify(text: str) -> None:
    """텔레그램 알림. 전송 자체의 실패는 stderr 에만 남기고 삼킨다(원래 흐름 보존)."""
    try:
        from ai_orchestrator.core.telegram_sender import send_message

        result = send_message(text)
        if not result.get("ok") and not result.get("skipped"):
            print(f"[publish_guard] 텔레그램 알림 실패: {result}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - 알림 실패가 본작업을 절대 깨면 안 됨
        print(f"[publish_guard] 텔레그램 알림 예외: {type(exc).__name__}: {exc}", file=sys.stderr)


def _safe_notify(text: str) -> None:
    """_notify 호출 자체가 예외를 던져도(테스트 monkeypatch 포함) 절대 전파하지 않는다."""
    try:
        _notify(text)
    except Exception as exc:  # noqa: BLE001 - 실패 기록 시도가 본 작업 오류를 가리면 안 되어 의도적으로 넓게 잡음
        print(f"[publish_guard] 알림 래퍼 예외: {type(exc).__name__}: {exc}", file=sys.stderr)


def _fail_message(op_name: str, detail: str) -> str:
    return f"{_NOTIFY_PREFIX} {op_name} 실패: {detail[:300]}"


@contextmanager
def guarded_publish(op_name: str, *, notify: bool = True, **meta: Any) -> Generator[None, None, None]:
    """예외 전파형 발행·발송 진입점을 감싼다.

    성공 시 아무 것도 하지 않고 그대로 통과한다(반환값 불변).
    실패 시: op_log 기록 → stderr 출력 → (notify=True 면) 텔레그램 알림 → 원래 예외 재발생.
    """
    try:
        yield
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        log_op(op_name, ok=False, message=detail, **meta)
        print(f"[FAIL] {op_name}: {detail}", file=sys.stderr)
        if notify:
            _safe_notify(_fail_message(op_name, detail))
        raise


def guarded(
    op_name: str,
    *,
    ok_fn: Callable[[Any], bool] = lambda r: True,
    notify: bool = True,
    **meta: Any,
) -> Callable:
    """데코레이터형. 예외 전파와, {"ok": False} 류 반환값 실패를 모두 실패로 취급한다.

    ok_fn: 함수의 반환값을 받아 성공이면 True 를 돌려준다. 기본은 항상 True
    (즉 반환형 판정을 쓰지 않고 예외만 실패로 본다).
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}"
                log_op(op_name, ok=False, message=detail, **meta)
                print(f"[FAIL] {op_name}: {detail}", file=sys.stderr)
                if notify:
                    _safe_notify(_fail_message(op_name, detail))
                raise

            try:
                ok = ok_fn(result)
            except Exception:  # noqa: BLE001 - 후처리(기록·알림) 실패는 원래 예외 전파를 막으면 안 됨
                ok = True  # ok_fn 자체 오류로 본작업 실패 처리하지 않음(보수적)

            if not ok:
                detail = "ok_fn=False (반환값 실패 판정)"
                log_op(op_name, ok=False, message=detail, **meta)
                print(f"[FAIL] {op_name}: {detail}", file=sys.stderr)
                if notify:
                    _safe_notify(_fail_message(op_name, detail))
            return result

        return wrapper

    return decorator
