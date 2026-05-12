"""경량 위험 게이트 — gate v1.0

scripts 레이어의 모든 주요 작업에 대해 위험 등급을 사전 검사하고
op_log에 게이트 결과를 기록한다.

ai_orchestrator/local_agent/action_gate.py (서버 레이어 풀스택 게이트)의
scripts 레이어 경량 버전. 승인 UI 없이 위험 등급 판단 + 로그 기록에 집중.

등급:
  AUTO    — 자동 실행 허용
  NOTIFY  — 실행하되 경고 기록 (주의 필요 작업)
  APPROVE — 비가역·외부 공개 작업 → 사용자 확인 필요 (GateBlocked 발생)
  BLOCK   — 항상 차단

APPROVE 작업을 자동 진행하려면 force=True 전달 또는
CLAUDE.md 의 "사용자 승인 후 자동 진행" 정책 적용 시 호출자가 판단.

사용법:
    from scripts.gate import check, gated, GateBlocked

    # 수동 체크
    result = check("mail_send", risk="approve", to="vendor@x.com")
    if result.blocked:
        raise RuntimeError(result.reason)

    # 데코레이터
    @gated("notify")
    def goto(target: str) -> None: ...

    # force=True (승인 흐름에서 사용자 동의 받은 후)
    check("mail_send", risk="approve", force=True, to="vendor@x.com")
"""
from __future__ import annotations

import functools
import threading
from typing import Any, Callable

from scripts.logger import get_logger
from scripts.schemas import GateResult, GateVerdict, RiskLevel

_log = get_logger(__name__)

# ── 작업별 기본 위험 등급 레지스트리 ────────────────────────────────

_RISK_REGISTRY: dict[str, RiskLevel] = {
    # 브라우저 탐색 (읽기)
    "goto":            RiskLevel.NOTIFY,
    "scan_page":       RiskLevel.AUTO,
    "scan_links":      RiskLevel.AUTO,
    "verify_text":     RiskLevel.AUTO,
    "verify_input":    RiskLevel.AUTO,
    "is_ready":        RiskLevel.AUTO,
    "wait_login":      RiskLevel.NOTIFY,

    # 브라우저 조작 (쓰기)
    "click_button":    RiskLevel.NOTIFY,
    "click_link":      RiskLevel.NOTIFY,
    "type_into":       RiskLevel.NOTIFY,
    "paste_image":     RiskLevel.NOTIFY,

    # 세션/저장
    "save_session":    RiskLevel.NOTIFY,

    # 콘텐츠 생성 (비가역)
    "write_blog_post": RiskLevel.APPROVE,
    "blog_publish":    RiskLevel.APPROVE,

    # 메일 발송 (외부 공개)
    "mail_send":       RiskLevel.APPROVE,
    "gmail_send":      RiskLevel.APPROVE,
    "naver_mail_send": RiskLevel.APPROVE,

    # 결제/이체 (비가역)
    "payment":         RiskLevel.APPROVE,
    "bank_transfer":   RiskLevel.APPROVE,

    # 데이터 삭제
    "data_delete":     RiskLevel.APPROVE,
    "file_delete":     RiskLevel.APPROVE,

    # CDP 이벤트 (읽기)
    "cdp_nav":         RiskLevel.AUTO,
    "cdp_request":     RiskLevel.AUTO,

    # 코드 변경 (write는 내부 작업)
    "file_write":      RiskLevel.AUTO,
    "file_edit":       RiskLevel.AUTO,

    # EUM
    "eum_extract_all_devices": RiskLevel.AUTO,
    "eum_register":    RiskLevel.APPROVE,
    "eum_remove":      RiskLevel.APPROVE,
}

# thread-local로 force 플래그 전파 가능
_force_local = threading.local()


# ── 핵심 API ─────────────────────────────────────────────────────────

class GateBlocked(RuntimeError):
    """APPROVE/BLOCK 등급 작업을 force=False 로 실행하려 할 때."""
    def __init__(self, result: GateResult):
        self.result = result
        super().__init__(f"[gate] {result.op_name} 차단됨 ({result.risk.value}): {result.reason}")


def register(op_name: str, risk: RiskLevel | str) -> None:
    """런타임에 작업 위험 등급 등록/갱신."""
    _RISK_REGISTRY[op_name] = RiskLevel(risk) if isinstance(risk, str) else risk


def get_risk(op_name: str) -> RiskLevel:
    """op_name 의 등록된 위험 등급 반환. 미등록 시 NOTIFY."""
    return _RISK_REGISTRY.get(op_name, RiskLevel.NOTIFY)


def check(
    op_name: str,
    *,
    risk: RiskLevel | str | None = None,
    force: bool = False,
    **metadata: Any,
) -> GateResult:
    """게이트 체크.

    Args:
        op_name: 작업 이름 (레지스트리 키)
        risk:    명시 등급. None 이면 레지스트리 조회
        force:   True 이면 APPROVE 등급도 통과 (사용자 승인 받은 경우)
        **metadata: 로그에 기록할 추가 정보

    Returns:
        GateResult

    Raises:
        GateBlocked: APPROVE/BLOCK 등급이고 force=False 인 경우
    """
    level = RiskLevel(risk) if risk else get_risk(op_name)

    if level == RiskLevel.AUTO:
        result = GateResult(verdict=GateVerdict.ALLOWED, risk=level,
                            op_name=op_name, metadata=metadata)

    elif level == RiskLevel.NOTIFY:
        _log.debug("[gate] notify: %s %s", op_name,
                   " ".join(f"{k}={v}" for k, v in metadata.items()))
        result = GateResult(verdict=GateVerdict.NOTIFIED, risk=level,
                            op_name=op_name,
                            reason="주의 작업 — 로그 기록됨",
                            metadata=metadata)

    elif level == RiskLevel.APPROVE:
        if force or getattr(_force_local, "active", False):
            result = GateResult(verdict=GateVerdict.ALLOWED, risk=level,
                                op_name=op_name,
                                reason="force=True (사용자 승인 완료)",
                                metadata=metadata)
        else:
            result = GateResult(verdict=GateVerdict.BLOCKED, risk=level,
                                op_name=op_name,
                                reason="외부 공개/비가역 작업 — 사용자 확인 필요",
                                metadata=metadata)

    else:  # BLOCK
        result = GateResult(verdict=GateVerdict.BLOCKED, risk=level,
                            op_name=op_name,
                            reason="항상 차단된 작업",
                            metadata=metadata)

    # op_log 기록
    try:
        from scripts.op_log import log_op
        log_op(
            f"gate.{result.verdict.value}",
            ok=result.allowed,
            op=op_name,
            risk=level.value,
            reason=result.reason or "",
            **{k: str(v)[:80] for k, v in metadata.items()},
        )
    except Exception:
        pass

    if result.blocked:
        raise GateBlocked(result)

    return result


# ── 컨텍스트 매니저 — force 구간 ─────────────────────────────────────

class force_approved:
    """with force_approved(): 블록 안에서는 APPROVE 작업도 자동 통과.

    사용자가 한 흐름 전체를 승인한 경우 (CLAUDE.md 자동 진행 정책).

    with gate.force_approved():
        navigator.write_blog_post(...)   # APPROVE 지만 통과
        gmail.send(...)                  # APPROVE 지만 통과
    """
    def __enter__(self):
        _force_local.active = True
        return self

    def __exit__(self, *_):
        _force_local.active = False


# ── 데코레이터 ────────────────────────────────────────────────────────

def gated(risk: RiskLevel | str, *, op_name: str | None = None) -> Callable:
    """함수에 게이트를 적용하는 데코레이터.

    @gated("notify")
    def click_button(text: str) -> bool: ...

    @gated("approve", op_name="mail_send")
    def send(to: str, subject: str, body: str) -> bool: ...
    """
    level = RiskLevel(risk) if isinstance(risk, str) else risk

    def decorator(fn: Callable) -> Callable:
        name = op_name or fn.__name__
        register(name, level)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            meta: dict[str, Any] = {}
            if args:
                meta["arg0"] = str(args[0])[:80]
            check(name, risk=level, **meta)
            return fn(*args, **kwargs)

        return wrapper
    return decorator


# ── 조회 ─────────────────────────────────────────────────────────────

def list_registry() -> list[dict]:
    """등록된 전체 작업 + 위험 등급 목록 반환."""
    return [{"op_name": k, "risk": v.value} for k, v in sorted(_RISK_REGISTRY.items())]
