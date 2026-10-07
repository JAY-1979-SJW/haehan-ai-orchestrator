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
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.logger import get_logger
from scripts.schemas import GateResult, GateVerdict, RiskLevel

_log = get_logger(__name__)

# ── 작업별 기본 위험 등급 레지스트리 ────────────────────────────────

_RISK_REGISTRY: dict[str, RiskLevel] = {
    # 브라우저 탐색 (읽기)
    "goto": RiskLevel.NOTIFY,
    "scan_page": RiskLevel.AUTO,
    "scan_links": RiskLevel.AUTO,
    "verify_text": RiskLevel.AUTO,
    "verify_input": RiskLevel.AUTO,
    "is_ready": RiskLevel.AUTO,
    "wait_login": RiskLevel.NOTIFY,
    # 브라우저 조작 (쓰기)
    "click_button": RiskLevel.NOTIFY,
    "click_link": RiskLevel.NOTIFY,
    "type_into": RiskLevel.NOTIFY,
    "paste_image": RiskLevel.NOTIFY,
    # 세션/저장
    "save_session": RiskLevel.NOTIFY,
    # 콘텐츠 생성 (비가역)
    "write_blog_post": RiskLevel.APPROVE,
    "blog_publish": RiskLevel.APPROVE,
    # 메일 발송 (외부 공개)
    "mail_send": RiskLevel.APPROVE,
    "gmail_send": RiskLevel.APPROVE,
    "naver_mail_send": RiskLevel.APPROVE,
    "naver_mail_delete": RiskLevel.APPROVE,
    "naver_mail_move": RiskLevel.APPROVE,
    "naver_mail_settings_save": RiskLevel.APPROVE,
    "naver_paid_api_key_issue": RiskLevel.BLOCK,
    "naver_paid_api_use": RiskLevel.BLOCK,
    "naver_searchad_campaign_create": RiskLevel.BLOCK,
    "naver_searchad_budget_update": RiskLevel.BLOCK,
    "naver_payment_method_register": RiskLevel.BLOCK,
    "naver_ad_publish": RiskLevel.BLOCK,
    # 결제/이체 (비가역)
    "payment": RiskLevel.APPROVE,
    "bank_transfer": RiskLevel.APPROVE,
    # 데이터 삭제
    "data_delete": RiskLevel.APPROVE,
    "file_delete": RiskLevel.APPROVE,
    # CDP 이벤트 (읽기)
    "cdp_nav": RiskLevel.AUTO,
    "cdp_request": RiskLevel.AUTO,
    # 팝업 감지 (자동 처리)
    "popup_detect": RiskLevel.AUTO,
    "popup_dismiss": RiskLevel.NOTIFY,
    "chrome_ui_detect": RiskLevel.AUTO,
    "chrome_ui_dismiss": RiskLevel.NOTIFY,
    # 코드 변경 (write는 내부 작업)
    "file_write": RiskLevel.AUTO,
    "file_edit": RiskLevel.AUTO,
    # EUM
    "eum_extract_all_devices": RiskLevel.AUTO,
    "eum_register": RiskLevel.APPROVE,
    "eum_register_device": RiskLevel.APPROVE,
    "eum_remove": RiskLevel.APPROVE,
    "eum_deregister_device": RiskLevel.APPROVE,
    # G2B
    "g2b_discover": RiskLevel.NOTIFY,
    "g2b_download": RiskLevel.NOTIFY,
    "g2b_suite": RiskLevel.NOTIFY,
    # 로컬 에이전트 (고위험 정부/민원)
    "gov24": RiskLevel.APPROVE,
    "minwon": RiskLevel.APPROVE,
    "blog_explore": RiskLevel.AUTO,
    "blog_scrape": RiskLevel.AUTO,
    "create_profile": RiskLevel.NOTIFY,
    # 탐색
    "explore_page": RiskLevel.AUTO,
    "explore_tabs": RiskLevel.AUTO,
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
        result = GateResult(verdict=GateVerdict.ALLOWED, risk=level, op_name=op_name, metadata=metadata)

    elif level == RiskLevel.NOTIFY:
        _log.debug("[gate] notify: %s %s", op_name, " ".join(f"{k}={v}" for k, v in metadata.items()))
        result = GateResult(
            verdict=GateVerdict.NOTIFIED,
            risk=level,
            op_name=op_name,
            reason="주의 작업 — 로그 기록됨",
            metadata=metadata,
        )

    elif level == RiskLevel.APPROVE:
        if force or getattr(_force_local, "active", False):
            result = GateResult(
                verdict=GateVerdict.ALLOWED,
                risk=level,
                op_name=op_name,
                reason="force=True (사용자 승인 완료)",
                metadata=metadata,
            )
        else:
            result = GateResult(
                verdict=GateVerdict.BLOCKED,
                risk=level,
                op_name=op_name,
                reason="외부 공개/비가역 작업 — 사용자 확인 필요",
                metadata=metadata,
            )

    else:  # BLOCK
        result = GateResult(
            verdict=GateVerdict.BLOCKED, risk=level, op_name=op_name, reason="항상 차단된 작업", metadata=metadata
        )

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
    except Exception:  # noqa: BLE001 - op_log 기록(log_op) 실패를 무시 - 실제 게이트 판정(result.blocked/ALLOWED/BLOCKED)은 이 try 블록 이전에 이미 완료되어 있고, 이 except는 보조 감사로그 기록 실패만 삼킴, 판정 결과에 전혀 영향 없음
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


# ── 외부 발행·발송 승인·수신거부 장치 (R2) ──────────────────────────
# 승인 문구 + 수신거부를 한곳에서 판정한다. 라우터가 아니라 부작용 함수 안쪽에서 호출해 직접 import 호출도
# 거치게 한다. 발송량(하루 상한)은 제한하지 않는다 — 건수는 사용자가 판단한다(대표님 결정).
# 수신거부 목록은 data/gate/opt_out.json (GATE_DATA_DIR 로 변경) 에 tmp+rename 으로만 쓴다.

_opt_out_lock = threading.Lock()


def _opt_out_path() -> Path:
    base = os.environ.get("GATE_DATA_DIR")
    root = Path(base) if base else Path(__file__).resolve().parents[1] / "data" / "gate"
    return root / "opt_out.json"


def opt_out_list() -> set[str] | None:
    """수신거부 목록. 파일이 깨졌으면 None(호출자가 보수적으로 차단)."""
    try:
        data = json.loads(_opt_out_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except (OSError, ValueError):
        _log.warning("[gate] 수신거부 목록 읽기 실패 — 발송 차단: %s", _opt_out_path())
        return None
    return {str(a).strip().lower() for a in data}


def add_opt_out(address: str) -> None:
    with _opt_out_lock:
        path = _opt_out_path()
        merged = sorted((opt_out_list() or set()) | {address.strip().lower()})
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)


def _blocked(op_name: str, reason: str, **metadata: Any) -> GateBlocked:
    result = GateResult(
        verdict=GateVerdict.BLOCKED, risk=RiskLevel.APPROVE, op_name=op_name, reason=reason, metadata=metadata
    )
    return GateBlocked(result)


def require_side_effect(
    op_name: str,
    *,
    approval: str | None,
    expected: str,
    recipient: str | None = None,
    **metadata: Any,
) -> GateResult:
    """외부 발행·발송 직전 공통 검사. 통과하면 GateResult, 아니면 GateBlocked.

    1) 승인 문구(approval == expected) — 불리언 force 가 아니라 사용자가 확인 단계에서 입력한 값이어야 한다
    2) 수신거부 — recipient 가 opt_out 목록에 있으면 차단(목록 파일이 깨졌으면 차단)
    """
    if approval != expected:
        raise _blocked(op_name, "명시 승인 문구 필요", **metadata)
    if recipient is not None:
        opted = opt_out_list()
        if opted is None:
            raise _blocked(op_name, "수신거부 목록을 읽을 수 없음", **metadata)
        if recipient.strip().lower() in opted:
            raise _blocked(op_name, "수신거부 대상", recipient=recipient, **metadata)
    return check(op_name, risk=RiskLevel.APPROVE, force=True, **metadata)
