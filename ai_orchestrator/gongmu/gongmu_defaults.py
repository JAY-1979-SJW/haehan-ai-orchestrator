"""L1 공유 계약 — 건설업 공무 업무의 상태 어휘·기준값(설정·기준표)·계획 항목 모양(순수 값, 부작용 없음).

저장소(`persistence/gongmu_store`, L7)는 L2 정책을 읽을 수 없으므로, 저장소와 정책이 함께 쓰는 값을 여기에 둔다.
정책(`gates/gongmu_task_policy`)은 이 이름들을 그대로 다시 내보내고, 기한 계산·계획 생성 같은 판정만 맡는다.
기준서: docs/specs/2026-10-02_construction_gongmu.md

⚠ 금액 기준·조문·신고 시점은 이미지 문구를 **초기값**으로 둔 것이다. 법령은 개정되므로 기준값은 설정
(`DEFAULT_SETTINGS`)과 기준표(`DEFAULT_CATALOG`)에서 바꿀 수 있고, 이 모듈은 법률 판단을 보증하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

# ── 상태 ────────────────────────────────────────────────────────────────────
TODO, DOING, SUBMIT_WAIT, DONE, NA = "todo", "doing", "submit_wait", "done", "na"
STATUSES = (TODO, DOING, SUBMIT_WAIT, DONE, NA)
CLOSED_STATUSES = (DONE, NA)
STATUS_LABEL = {TODO: "할 일", DOING: "진행", SUBMIT_WAIT: "제출 대기", DONE: "완료", NA: "해당 없음"}

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


def merged_settings(stored: dict[str, Any] | None) -> dict[str, int]:
    out = dict(DEFAULT_SETTINGS)
    for key, value in (stored or {}).items():
        if key in out:
            out[key] = int(value)
    return out


@dataclass(frozen=True)
class PlannedTask:
    dedupe_key: str
    catalog_code: str
    site_id: str
    contract_id: str  # 현장 단위 업무는 ""
    period: str  # 중복 판별용 기준일/기간("" · "2026" · "2026-10" · "chg:2026-03-01#1")
    due_date: date | None
    reason: str  # 왜 만들어졌는지(화면 표시)
