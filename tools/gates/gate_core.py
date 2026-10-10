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
    from tools.gates.gate_core import check, gated, GateBlocked

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

import contextlib
import functools
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir
from tools.gates.gate_types import GateResult, GateVerdict, RiskLevel

# 로거 이름은 "scripts" 계층 아래에 둔다 — 핸들러는 "scripts" 루트 로거에 붙어 있어 기존 로그 출력·파일 기록이 그대로다.
# (이 모듈은 scripts 를 import 하지 않는다. 이름 계층만 쓴다.)
_log = logging.getLogger("scripts.gate_core")

# 감사 기록 싱크: 게이트 판정을 op_log 등에 남기는 함수. scripts/common/gate.py(shim)와 앱 시작점이 등록한다(의존 방향 보존).
_audit_sink: Callable[..., Any] | None = None


def set_audit_sink(fn: Callable[..., Any] | None) -> None:
    """게이트 판정 감사 기록 함수 등록(없으면 감사 기록은 건너뛰고 판정은 그대로)."""
    global _audit_sink
    _audit_sink = fn


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

    # 감사 기록(등록된 싱크가 있을 때만) — 판정에는 영향을 주지 않는다
    sink = _audit_sink
    if sink is not None:
        try:
            sink(
                f"gate.{result.verdict.value}",
                ok=result.allowed,
                op=op_name,
                risk=level.value,
                reason=result.reason or "",
                **{k: str(v)[:80] for k, v in metadata.items()},
            )
        except Exception as exc:  # noqa: BLE001 - 감사 기록 실패를 무시 - 실제 게이트 판정(result.blocked/ALLOWED/BLOCKED)은 이 try 블록 이전에 이미 완료되어 있고, 이 except는 보조 감사로그 기록 실패만 삼킴, 판정 결과에 전혀 영향 없음
            _log.debug("[gate] 감사 기록 실패(판정에는 영향 없음): %s", exc)

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

# 작업별 승인 문구 — 사용자가 확인 단계에서 직접 입력해야 하는 값(코드·화면에서 자동으로 채우지 않는다).
# 한곳에 모아 두면 R2d-2(승인을 내용 해시에 묶기)에서 교체할 지점이 하나가 된다.
CONFIRM_TEXTS: dict[str, str] = {
    "blog_publish": "NAVER_BLOG_APPROVED_PUBLISH",
    "instagram_publish": "INSTAGRAM_APPROVED_PUBLISH",
    "smartstore_reply": "SMARTSTORE_APPROVED_REPLY",
    "drive_share": "GOOGLE_DRIVE_APPROVED_SHARE",
    "hanafax_send": "HANAFAX_APPROVED_SEND",
}
_LOCK_WAIT_S = 10.0
_LOCK_STALE_S = 30.0  # 이보다 오래된 잠금 파일은 죽은 프로세스가 남긴 것으로 보고 치운다


_IS_WINDOWS = os.name == "nt"
_UNLINK_RETRY_S = 1.0  # Windows 에서 잠금 파일 삭제가 공유 위반으로 잠깐 막힐 때 기다리는 최대 시간


def _release_lock_file(lock_path: Path) -> None:
    """잠금 파일을 지운다. Windows 의 일시적 공유 위반(PermissionError)은 짧게 재시도하고, 끝내 못 지우면 기록한다.

    예전에는 모든 OSError 를 조용히 삼켜 잠금 파일이 남을 수 있었다(다음 프로세스가 기한까지 기다리다 실패).
    """
    stop = time.monotonic() + _UNLINK_RETRY_S
    while True:
        try:
            lock_path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if not _IS_WINDOWS or time.monotonic() > stop:
                _log.warning("[gate] 수신거부 잠금 파일 삭제 실패(다음 획득자는 오래된 잠금 정리 규칙을 따른다): %s", lock_path)
                return
            time.sleep(0.02)
        except OSError:
            _log.warning("[gate] 수신거부 잠금 파일 삭제 실패: %s", lock_path)
            return


def _opt_out_path() -> Path:
    base = os.environ.get("GATE_DATA_DIR")
    root = Path(base) if base else data_dir() / "gate"
    return root / "opt_out.json"


@contextlib.contextmanager
def _opt_out_guard() -> Iterator[None]:
    """수신거부 목록 읽고-합치고-쓰기 구간의 배타 잠금. 스레드 락 + 잠금 파일(O_CREAT|O_EXCL)로 프로세스 간에도 막는다."""
    lock_path = _opt_out_path().with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + _LOCK_WAIT_S
    with _opt_out_lock:
        while True:
            try:
                os.close(os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except PermissionError:
                # Windows: 다른 프로세스가 방금 unlink 한 잠금 파일은 '삭제 보류' 상태라 같은 이름의 생성이
                # FileExistsError 가 아니라 PermissionError(Errno 13)로 실패한다 — 잠금 중과 같은 뜻이므로 기한까지 기다린다.
                # POSIX 의 PermissionError 는 진짜 권한 문제라 즉시 올린다. 기한이 지나면 원래 오류를 그대로 올린다(조용히 넘기지 않음).
                if not _IS_WINDOWS or time.monotonic() > deadline:
                    raise
                time.sleep(0.02)
            except FileExistsError:
                with contextlib.suppress(OSError):
                    if time.time() - lock_path.stat().st_mtime > _LOCK_STALE_S:
                        lock_path.unlink()
                        continue
                if time.monotonic() > deadline:
                    # 잠금을 못 얻으면 쓰지 않고 실패시킨다 — 조용히 덮어써서 수신거부를 잃는 것보다 낫다.
                    raise TimeoutError(f"[gate] 수신거부 잠금 획득 실패: {lock_path}") from None
                time.sleep(0.02)
        try:
            yield
        finally:
            _release_lock_file(lock_path)


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
    with _opt_out_guard():
        path = _opt_out_path()
        merged = sorted((opt_out_list() or set()) | {address.strip().lower()})
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)


def is_opted_out(address: str) -> bool:
    """수신거부 목록에 있으면 True. 목록 파일이 깨졌으면 보수적으로 True(보내지 않는다)."""
    opted = opt_out_list()
    return opted is None or address.strip().lower() in opted


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
    recipient: str | list[str] | None = None,
    **metadata: Any,
) -> GateResult:
    """외부 발행·발송 직전 공통 검사. 통과하면 GateResult, 아니면 GateBlocked.

    1) 승인 문구(approval == expected) — 불리언 force 가 아니라 사용자가 확인 단계에서 입력한 값이어야 한다
    2) 수신거부 — recipient(여러 명이면 목록) 중 하나라도 opt_out 목록에 있으면 차단(목록 파일이 깨졌으면 차단)
    """
    if approval != expected:
        raise _blocked(op_name, "명시 승인 문구 필요", **metadata)
    if recipient is not None:
        opted = opt_out_list()
        if opted is None:
            raise _blocked(op_name, "수신거부 목록을 읽을 수 없음", **metadata)
        names = [recipient] if isinstance(recipient, str) else list(recipient)
        hit = next((r for r in names if r.strip().lower() in opted), None)
        if hit is not None:
            raise _blocked(op_name, "수신거부 대상", recipient=hit, **metadata)
    return check(op_name, risk=RiskLevel.APPROVE, force=True, **metadata)


def require_approved(op_name: str, approval: str | None, **metadata: Any) -> GateResult:
    """CONFIRM_TEXTS 에 등록된 작업의 승인 문구 검사(수신자가 없는 공개 발행·답변·공유용)."""
    return require_side_effect(op_name, approval=approval, expected=CONFIRM_TEXTS[op_name], **metadata)
