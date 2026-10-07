"""L1 Shared Contracts — 업무 후보의 `never`(자동 실행 불가) 분류와 업무 명세(task spec) 규칙 (순수, 입출력 없음).

기준서: docs/specs/2026-10-05_new_site_onboarding_pipeline.md (M12)

- `never` 는 위험 등급(`risk`: read/write/submit)을 늘리지 않고 업무에 **별도 표시 키**로 붙는다. 기존 검증·응답은 그대로다.
- 판정은 fail-closed 다: 글자(키워드)와 입력칸 종류를 함께 보고, 위험 등급이 submit 인데 판정할 글자가 전혀 없으면 `unclassified` 로 막는다.
- `never` 업무는 명세 생성·실행 계획(드라이런)·승인 요청 대상에서 모두 제외한다. 승인으로도 풀리지 않는다(사람이 사이트에서 직접 한다).
- 이 모듈은 `site_task_map` 을 import 하지 않는다(그쪽이 이 모듈을 쓴다) — 위험 등급 문자열만 안다.
"""

from __future__ import annotations

import re
from typing import Any

NEVER_DELETE, NEVER_PAYMENT, NEVER_SIGNATURE, NEVER_OTP, NEVER_CREDENTIAL, NEVER_IRREVERSIBLE, NEVER_UNCLASSIFIED = (
    "delete",
    "payment",
    "signature",
    "otp",
    "credential",
    "irreversible",
    "unclassified",
)
NEVER_KINDS = (
    NEVER_DELETE,
    NEVER_PAYMENT,
    NEVER_SIGNATURE,
    NEVER_OTP,
    NEVER_CREDENTIAL,
    NEVER_IRREVERSIBLE,
    NEVER_UNCLASSIFIED,
)

# 종류별 (한글 부분 문자열, 영문 단어 접두). 앞선 종류가 우선한다.
_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        NEVER_PAYMENT,
        ("결제", "송금", "이체", "출금", "입금", "납부", "지급", "환불", "충전", "투찰"),
        ("pay", "payment", "transfer", "withdraw", "remit", "checkout", "refund", "bid"),
    ),
    (
        NEVER_SIGNATURE,
        ("전자서명", "서명", "인증서", "공동인증", "공인인증"),
        ("sign", "signature", "certificate", "esign"),
    ),
    (NEVER_OTP, ("otp", "인증번호", "보안카드", "일회용", "본인확인"), ("otp", "2fa", "mfa")),
    (
        NEVER_DELETE,
        ("삭제", "제거", "파기", "폐기", "말소", "해지", "탈퇴"),
        ("delete", "remove", "destroy", "purge", "terminate", "deactivate"),
    ),
    (
        NEVER_IRREVERSIBLE,
        ("도메인", "호스팅", "네임서버", "연장", "권한 철회", "권한철회", "계정 삭제", "계정삭제"),
        ("dns", "domain", "nameserver", "hosting", "revoke", "renew"),
    ),
)
_PASSWORD_TYPES = frozenset({"password"})
_SENSITIVE_WORDS = (
    "password",
    "passwd",
    "pwd",
    "비밀번호",
    "패스워드",
    "card",
    "카드번호",
    "ssn",
    "주민",
    "otp",
    "token",
    "secret",
)
_TOKEN = re.compile(r"[a-z0-9]+")


def _has(text: str, ko: tuple[str, ...], en: tuple[str, ...]) -> bool:
    low = text.lower()
    if any(k in low for k in ko):
        return True
    tokens = _TOKEN.findall(low)
    return any(tok.startswith(w) for tok in tokens for w in en)


def never_kind(texts: list[str], fields: list[dict[str, Any]] | None = None, *, risk: str = "read") -> str:
    """업무의 `never` 종류(없으면 빈 문자열). 글자·입력칸 종류·(위험 등급 + 판정 근거 유무)를 함께 본다."""
    joined = " ".join(str(t) for t in texts if t)
    for kind, ko, en in _RULES:
        # 조회(read) 업무는 이름에 '결제 내역' 같은 말이 있어도 읽기만 하므로 글자로는 막지 않는다 — 입력칸 종류(비밀번호·OTP)로만 판정한다
        if risk != "read" and _has(joined, ko, en):
            return kind
    for field in fields or []:
        if str(field.get("type") or "").lower() in _PASSWORD_TYPES:
            return NEVER_CREDENTIAL
        label = f"{field.get('name', '')} {field.get('label', '')}"
        if _has(label, ("otp", "인증번호", "보안카드"), ("otp",)):
            return NEVER_OTP
    if risk == "submit" and not joined.strip() and not fields:
        return NEVER_UNCLASSIFIED  # 제출 업무인데 판정할 글자·입력칸이 전혀 없다 — 모르면 막는다
    return ""


def stored_never(task: dict[str, Any]) -> str:
    value = str(task.get("never") or "")
    return value if value in NEVER_KINDS else ""


def effective_never(task: dict[str, Any]) -> str:
    """저장된 표시와 **현재 규칙**으로 다시 판정한 결과 중 하나라도 있으면 그것. 한 번 붙은 표시는 규칙이 바뀌어도 빠지지 않는다."""
    kept = stored_never(task)
    if kept:
        return kept
    texts = [str(task.get("name") or ""), str(task.get("control") or ""), str(task.get("url") or "")]
    return never_kind(texts, task.get("fields") or [], risk=str(task.get("risk") or "read"))


def carry_never(old: dict[str, Any], new: dict[str, Any]) -> str:
    """지도에 이미 있던 업무와 새로 관찰한 업무의 표시를 합친다(둘 중 하나라도 있으면 유지 — 자동 관찰이 표시를 지우지 못한다)."""
    return stored_never(old) or stored_never(new)


def is_ai_runnable(task: dict[str, Any], risk: str) -> bool:
    """AI 가 사람 개입 없이 실행할 수 있나: 위험 등급이 read 이고 never 가 아닐 때만."""
    return risk == "read" and not effective_never(task)


def candidate_view(task: dict[str, Any], risk: str) -> dict[str, Any]:
    """'이 사이트에서 할 수 있는 일' 목록의 한 줄. never 는 '자동 실행 불가'로 표시한다."""
    never = effective_never(task)
    if never:
        state = "자동 실행 불가"
    elif risk == "read":
        state = "AI 가 실행 가능"
    else:
        state = "사람 승인 필요"
    return {
        "task_key": str(task.get("id") or ""),
        "name": str(task.get("name") or ""),
        "risk": risk,
        "never": never,
        "ai_runnable": is_ai_runnable(task, risk),
        "availability": state,
        "has_spec": isinstance(task.get("spec"), dict),
    }


def _inputs(task: dict[str, Any], placeholders: list[str]) -> list[dict[str, Any]]:
    by_name = {str(f.get("name") or f.get("id") or ""): f for f in task.get("fields", [])}
    out = []
    for name in placeholders:
        f = by_name.get(name, {})
        text = f"{name} {f.get('label', '')}".lower()
        out.append(
            {
                "name": name,
                "type": str(f.get("type") or "text"),
                "required": bool(f.get("required", False)),
                "sensitive": str(f.get("type") or "") in _PASSWORD_TYPES or any(w in text for w in _SENSITIVE_WORDS),
            }
        )
    return out


def build_spec(task: dict[str, Any], risk: str, *, map_rev: int, placeholders: list[str]) -> dict[str, Any]:
    """업무 명세 초안. never 는 만들지 않는다(ValueError). 입력 **값**은 담지 않는다(이름·종류·민감 여부만)."""
    kind = effective_never(task)
    if kind:
        raise ValueError(
            f"자동 실행 불가 업무입니다(never:{kind}) — 명세·실행 계획·승인 요청을 만들 수 없습니다. 사람이 사이트에서 직접 해야 합니다"
        )
    steps = [str(s.get("type") or "") for s in task.get("steps", [])]
    final_click = (
        bool(task.get("control")) and risk != "read"
    )  # read 가 아니면 최종 버튼은 지도 절차에 없다 — 사람 확정 뒤에만 누른다
    return {
        "task_key": str(task.get("id") or ""),
        "map_rev": int(map_rev),
        "risk": risk,
        "inputs": _inputs(task, placeholders),
        "step_types": steps,
        "outputs": [str(o) for o in task.get("outputs", [])][:30],
        "success": "결과 표의 열 이름이 지도의 outputs 와 같고 행이 1개 이상"
        if risk == "read"
        else "최종 버튼 직전까지 입력되고 사람이 확정 카드에서 승인",
        "irreversible_at": (
            f"최종 버튼 '{task.get('control')}' 클릭" if final_click else "" if risk == "read" else "최종 제출"
        ),
        "approval_points": [] if risk == "read" else ["최종 버튼 클릭 전 사람 확정(확정 카드)"],
        "will_click_final": risk == "read",
    }


def validate_spec(spec: Any) -> dict[str, Any]:
    """저장된 명세 검증 — 되돌릴 수 없는 지점·승인 지점이 없는 비-read 명세는 거부한다."""
    if not isinstance(spec, dict) or not spec.get("task_key") or not isinstance(spec.get("inputs"), list):
        raise ValueError("업무 명세 형식이 올바르지 않습니다")
    if spec.get("risk") != "read" and (not spec.get("irreversible_at") or not spec.get("approval_points")):
        raise ValueError(
            "쓰기·제출 업무 명세에는 되돌릴 수 없는 지점(irreversible_at)과 승인 지점(approval_points)이 필요합니다"
        )
    return spec
