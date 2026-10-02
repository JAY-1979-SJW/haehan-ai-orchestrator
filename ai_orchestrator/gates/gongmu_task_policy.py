"""L2 Policy — 건설업 공무 업무 자동 생성 규칙 (순수 판정: DB·파일·네트워크 없음).

기준서: docs/specs/2026-10-02_construction_gongmu.md (§3-2)

⚠ 금액 기준·조문·신고 시점은 이미지 문구를 **초기값**으로 둔 것이다. 법령은 개정되므로 기준값은
설정(`DEFAULT_SETTINGS`)과 기준표(`DEFAULT_CATALOG`)에서 바꿀 수 있고, 이 모듈은 법률 판단을 보증하지 않는다.
기한 규칙이 모호하면 기한을 비우고 '기한 확인 필요'로 표시한다(조용히 추측하지 않는다).

나라장터(P7)는 사용자 결정으로 기준표에서 제외했다.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

# ── 상태 ────────────────────────────────────────────────────────────────────
TODO, DOING, SUBMIT_WAIT, DONE, NA = "todo", "doing", "submit_wait", "done", "na"
STATUSES = (TODO, DOING, SUBMIT_WAIT, DONE, NA)
CLOSED_STATUSES = (DONE, NA)
STATUS_LABEL = {TODO: "할 일", DOING: "진행", SUBMIT_WAIT: "제출 대기", DONE: "완료", NA: "해당 없음"}

ROLE_PRIME, ROLE_SUB = "prime", "sub"  # 우리 회사 지위: 원도급 / 하도급
KIND_PRIME, KIND_SUB = "prime", "sub"  # 계약 구분: 도급(발주처와) / 하도급(협력업체와)

# 기한 판정 등급
OVERDUE, SOON, LATER, UNKNOWN, CLOSED = "overdue", "soon", "later", "unknown", "closed"

# ── 설정 초기값(이미지 문구) — 사용자가 법령 확인 후 수정 ───────────────────────────
DEFAULT_SETTINGS: dict[str, int] = {
    "prime_notice_min": 100_000_000,  # 공사대장 통보: 원도급 1억원 이상
    "sub_notice_min": 40_000_000,  # 공사대장 통보: 하도급 4천만원 이상
    "soon_days": 7,  # 기한 임박 기준(일)
}

# ── 기준표 초기값(이미지 §1 — 나라장터 제외 12개) ─────────────────────────────────
# trigger: site_start(착공 시) · contract(계약마다) · contract_change(계약 변경마다) · monthly · yearly
# due_rule: {"type": "offset", "days": N}(기준일 + N일) · {"type": "period_end"} · {"type": "none"}(기한 확인 필요)
# condition: {"contract_kind": "sub"} · {"amount_key": 설정키, "role": ...} 등 — _qualifies 참고
DEFAULT_CATALOG: list[dict[str, Any]] = [
    {
        "code": "L1",
        "name": "키스콘(KISCON) 등록",
        "category": "legal",
        "trigger": "contract",
        "description": "하도급계약 체결 시 원도급자가 반드시 신고",
        "basis": "건설산업기본법 제22·26조(이미지 문구 — 원문 확인 필요)",
        "condition": {"contract_kind": "sub"},
        "due_rule": {"type": "none"},
        "docs": ["하도급계약서", "하도급 신고서"],
        "submit_to": "건설산업지식정보시스템(KISCON)",
        "verify_law": True,
    },
    {
        "code": "L2",
        "name": "공사대장 통보",
        "category": "legal",
        "trigger": "contract",
        "description": "원도급 1억원 이상·하도급 4천만원 이상 공사는 계약 체결·변경 시마다 발주자에게 통보",
        "basis": "이미지 문구 — 금액 기준은 설정에서 수정·법령 원문 확인 필요",
        "condition": {"notice_amount": True},
        "due_rule": {"type": "none"},
        "docs": ["계약서 사본", "공사대장 통보서"],
        "submit_to": "발주자",
        "verify_law": True,
    },
    {
        "code": "L3",
        "name": "실적신고(건설공사 기성실적신고)",
        "category": "legal",
        "trigger": "yearly",
        "description": "시공능력평가액 산정 기초자료, 매년 신고",
        "basis": "이미지 문구 — 신고 기한은 법령 확인 후 기한 입력",
        "condition": {},
        "due_rule": {"type": "none"},
        "docs": ["기성실적 증명 자료", "실적신고서"],
        "submit_to": "건설산업지식정보시스템(KISCON)",
        "verify_law": True,
    },
    {
        "code": "L4",
        "name": "건설기술인 배치신고",
        "category": "legal",
        "trigger": "site_start",
        "description": "현장 배치 기술인의 경력·자격을 시스템에 등록",
        "basis": "이미지 문구 — 처리 시점은 현장 배치 시",
        "condition": {},
        "due_rule": {"type": "none"},
        "docs": ["자격증 사본", "경력증명서", "배치신고서"],
        "submit_to": "건설기술인 관련 시스템",
        "verify_law": True,
    },
    {
        "code": "P1",
        "name": "인허가",
        "category": "practice",
        "trigger": "site_start",
        "description": "착공신고, 인허가 서류 준비 및 관공서 제출",
        "basis": "",
        "condition": {},
        "due_rule": {"type": "offset", "days": -7},
        "docs": ["착공신고서", "인허가 서류"],
        "submit_to": "관할 관공서",
        "verify_law": False,
    },
    {
        "code": "P2",
        "name": "계약관리",
        "category": "practice",
        "trigger": "contract",
        "description": "도급계약서·하도급계약서 검토·체결",
        "basis": "",
        "condition": {},
        "due_rule": {"type": "offset", "days": 0},
        "docs": ["계약서 검토 의견", "체결본"],
        "submit_to": "",
        "verify_law": False,
    },
    {
        "code": "P3",
        "name": "협력업체 관리",
        "category": "practice",
        "trigger": "contract",
        "description": "하도급심사 자기평가표, 하도급대금지급보증서 발급",
        "basis": "",
        "condition": {"contract_kind": "sub"},
        "due_rule": {"type": "offset", "days": 0},
        "docs": ["하도급심사 자기평가표", "하도급대금지급보증서"],
        "submit_to": "",
        "verify_law": False,
    },
    {
        "code": "P4",
        "name": "기성금 청구/정산",
        "category": "practice",
        "trigger": "monthly",
        "description": "기성 검사, 세금계산서 발행, 대금 수령 관리",
        "basis": "",
        "condition": {},
        "due_rule": {"type": "period_end"},
        "docs": ["기성 내역서", "세금계산서"],
        "submit_to": "발주처",
        "verify_law": False,
    },
    {
        "code": "P5",
        "name": "자금관리",
        "category": "practice",
        "trigger": "site_start",
        "description": "현장 개설자금 청구, 예산 집행",
        "basis": "",
        "condition": {},
        "due_rule": {"type": "offset", "days": 0},
        "docs": ["개설자금 청구서", "실행예산"],
        "submit_to": "본사",
        "verify_law": False,
    },
    {
        "code": "P6",
        "name": "4대보험",
        "category": "practice",
        "trigger": "monthly",
        "description": "건설업 특례에 따른 국민연금·건강보험·고용/산재보험 신고",
        "basis": "이미지 문구 — 신고 시점은 법령 확인 필요",
        "condition": {},
        "due_rule": {"type": "period_end"},
        "docs": ["근로자 명단", "보험 신고서"],
        "submit_to": "4대사회보험 정보연계센터",
        "verify_law": True,
    },
    {
        "code": "P8",
        "name": "안전서류",
        "category": "practice",
        "trigger": "site_start",
        "description": "안전관리계획서, 산업안전보건 관련 서류 작성·제출",
        "basis": "",
        "condition": {},
        "due_rule": {"type": "offset", "days": -7},
        "docs": ["안전관리계획서", "산업안전보건 서류"],
        "submit_to": "발주처·관할 기관",
        "verify_law": True,
    },
    {
        "code": "P9",
        "name": "본사 보고",
        "category": "practice",
        "trigger": "monthly",
        "description": "공정률, 손익 현황 등 정기 보고",
        "basis": "",
        "condition": {},
        "due_rule": {"type": "period_end"},
        "docs": ["공정률 보고", "손익 현황"],
        "submit_to": "본사",
        "verify_law": False,
    },
]


# ── 값 정리 ─────────────────────────────────────────────────────────────────


def parse_date(value: Any) -> date | None:
    """YYYY-MM-DD 문자열(또는 date)을 date 로. 비었으면 None, 형식이 틀리면 ValueError."""
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as e:
        raise ValueError(f"날짜는 YYYY-MM-DD 형식이어야 합니다: {value!r}") from e


def parse_amount(value: Any) -> int | None:
    """금액(원). 쉼표·'원' 허용. 비었으면 None, 음수·숫자 아님은 ValueError."""
    if value in (None, ""):
        return None
    text = str(value).replace(",", "").replace("원", "").strip()
    try:
        amount = int(float(text))
    except ValueError as e:
        raise ValueError(f"금액은 숫자여야 합니다: {value!r}") from e
    if amount < 0:
        raise ValueError("금액은 0 이상이어야 합니다")
    return amount


def merged_settings(stored: dict[str, Any] | None) -> dict[str, int]:
    out = dict(DEFAULT_SETTINGS)
    for key, value in (stored or {}).items():
        if key in out:
            out[key] = int(value)
    return out


def validate_settings(raw: dict[str, Any]) -> dict[str, int]:
    """수정할 설정 검증 — 알 수 없는 키·음수·숫자 아님은 거부."""
    out: dict[str, int] = {}
    for key, value in raw.items():
        if key not in DEFAULT_SETTINGS:
            raise ValueError(f"알 수 없는 설정: {key}")
        try:
            number = int(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{key} 은(는) 숫자여야 합니다") from e
        if number < 0:
            raise ValueError(f"{key} 은(는) 0 이상이어야 합니다")
        out[key] = number
    return out


# ── 기한 계산 ───────────────────────────────────────────────────────────────


def compute_due(rule: dict[str, Any], base: date | None, period_end: date | None) -> date | None:
    """기한 규칙으로 기한을 계산한다. 계산할 근거가 없으면 None('기한 확인 필요')."""
    kind = (rule or {}).get("type", "none")
    if kind == "offset":
        if base is None:
            return None
        return base + timedelta(days=int(rule.get("days", 0)))
    if kind == "period_end":
        return period_end
    return None


def classify_due(due: date | None, status: str, today: date, soon_days: int) -> str:
    """종료 상태 → closed, 기한 없음 → unknown, 지남 → overdue, soon_days 이내 → soon, 그 외 later."""
    if status in CLOSED_STATUSES:
        return CLOSED
    if due is None:
        return UNKNOWN
    if due < today:
        return OVERDUE
    if (due - today).days <= soon_days:
        return SOON
    return LATER


# ── 계획 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlannedTask:
    dedupe_key: str
    catalog_code: str
    site_id: str
    contract_id: str  # 현장 단위 업무는 ""
    period: str  # 중복 판별용 기준일/기간("" · "2026" · "2026-10" · "chg:2026-03-01#1")
    due_date: date | None
    reason: str  # 왜 만들어졌는지(화면 표시)


def make_key(site_id: str, code: str, contract_id: str, period: str) -> str:
    return f"{site_id}|{code}|{contract_id}|{period}"


def _meets_notice(amount: int | None, kind: str, settings: dict[str, int]) -> bool:
    if amount is None:
        return False
    threshold = settings["prime_notice_min"] if kind == KIND_PRIME else settings["sub_notice_min"]
    return amount >= threshold


def _qualifies(condition: dict[str, Any], kind: str, amount: int | None, settings: dict[str, int]) -> bool:
    if "contract_kind" in condition and condition["contract_kind"] != kind:
        return False
    if condition.get("notice_amount") and not _meets_notice(amount, kind, settings):
        return False
    return True


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _site_active_in(site: dict[str, Any], first: date, last: date) -> bool:
    start, end = parse_date(site.get("start_date")), parse_date(site.get("end_date"))
    if start is None or start > last:
        return False
    return not (end is not None and end < first)


def _contract_events(contract: dict[str, Any]) -> list[tuple[str, date | None, int | None, str]]:
    """계약 1건의 (기간키, 기준일, 금액, 설명) 목록 — 체결 1회 + 변경 이력 각각."""
    amount = contract.get("amount")
    events = [("", parse_date(contract.get("contract_date")), amount, "계약 체결")]
    for idx, change in enumerate(contract.get("changes") or [], start=1):
        when = parse_date(change.get("date"))
        events.append(
            (f"chg:{when.isoformat() if when else 'x'}#{idx}", when, change.get("amount", amount), "계약 변경")
        )
    return events


Adder = Callable[[str, str, str, "date | None", str], None]


def _plan_site_start(item: dict[str, Any], site: dict[str, Any], settings: dict[str, int], add: Adder) -> None:
    start = parse_date(site.get("start_date"))
    if start is not None and _qualifies(
        item.get("condition") or {}, site.get("role") or ROLE_PRIME, site.get("contract_amount"), settings
    ):
        add(item["code"], "", "", compute_due(item.get("due_rule") or {}, start, None), "착공일 기준")


def _plan_contract(
    item: dict[str, Any], site: dict[str, Any], contracts: list[dict[str, Any]], settings: dict[str, int], add: Adder
) -> None:
    code, condition, rule = item["code"], item.get("condition") or {}, item.get("due_rule") or {}
    for contract in contracts:
        kind = contract.get("kind") or KIND_SUB
        for period, base, amount, why in _contract_events(contract):
            if period and code != "L2":  # 변경 시마다 다시 생성하는 것은 공사대장 통보뿐
                continue
            if _qualifies(condition, kind, amount, settings):
                add(code, contract["id"], period, compute_due(rule, base, None), why)
    # 도급 계약 행이 없으면 현장 자체의 도급금액으로 공사대장 통보 판정(현장 등록 시)
    has_prime_row = any(c.get("kind") == KIND_PRIME for c in contracts)
    role = site.get("role") or ROLE_PRIME
    if code == "L2" and not has_prime_row and _meets_notice(site.get("contract_amount"), role, settings):
        add(code, "", "site", compute_due(rule, parse_date(site.get("start_date")), None), "현장 도급금액 기준")


def _plan_period(item: dict[str, Any], site: dict[str, Any], today: date, add: Adder) -> None:
    if item["trigger"] == "monthly":
        first, last = date(today.year, today.month, 1), _month_end(today.year, today.month)
        period, why = f"{today.year:04d}-{today.month:02d}", "월 정기"
    else:
        first, last = date(today.year, 1, 1), date(today.year, 12, 31)
        period, why = f"{today.year:04d}", "연 정기"
    if _site_active_in(site, first, last):
        add(item["code"], "", period, compute_due(item.get("due_rule") or {}, None, last), why)


def plan_tasks(
    site: dict[str, Any],
    contracts: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    settings: dict[str, int],
    today: date,
) -> list[PlannedTask]:
    """현장·계약 상태에서 만들어야 할 업무 전체를 계산한다(이미 있는 것은 호출 쪽에서 dedupe_key 로 걸러냄).

    같은 입력이면 같은 결과(순수)이고, 기준 날짜(today)가 지나 새 기간이 생기면 월·연 업무가 늘어난다.
    """
    site_id = site["id"]
    planned: dict[str, PlannedTask] = {}

    def add(code: str, contract_id: str, period: str, due: date | None, reason: str) -> None:
        key = make_key(site_id, code, contract_id, period)
        planned.setdefault(key, PlannedTask(key, code, site_id, contract_id, period, due, reason))

    for item in catalog:
        if not item.get("enabled", True):
            continue
        trigger = item["trigger"]
        if trigger == "site_start":
            _plan_site_start(item, site, settings, add)
        elif trigger == "contract":
            _plan_contract(item, site, contracts, settings, add)
        elif trigger in ("monthly", "yearly"):
            _plan_period(item, site, today, add)
    return list(planned.values())
