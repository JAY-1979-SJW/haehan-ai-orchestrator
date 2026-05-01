"""action 메타데이터 레지스트리.

- 공통 인터페이스 (카테고리/리스크/요구자원) 를 등록해 app/log/감사 계층이 참조.
- 이번 단계에서는 **기존 action 6종만** 등록한다 (기능 추가 없음).
- 향후 excel / cad / mcp 카테고리 확장 지점이 된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ── 카테고리 / 리스크 상수 ──────────────────────────────────────────────
CATEGORY_SYSTEM = "system"
CATEGORY_WEB = "web"
CATEGORY_SECRET = "secret"
CATEGORY_UNKNOWN = "unknown"

# 향후 확장 지점 (이번 단계에서는 값으로만 존재):
CATEGORY_EXCEL = "excel"
CATEGORY_EXCEL_COM = "excel_com"
CATEGORY_CAD = "cad"
CATEGORY_MCP = "mcp"
# local_agent.browser_launcher.open_local_browser 전용. 서버측 Playwright
# 경로와 분리해 visible 로컬 브라우저 기동만 다룬다.
CATEGORY_LOCAL_BROWSER = "local_browser"

KNOWN_CATEGORIES: frozenset[str] = frozenset({
    CATEGORY_SYSTEM, CATEGORY_WEB, CATEGORY_SECRET,
    CATEGORY_EXCEL, CATEGORY_EXCEL_COM, CATEGORY_CAD, CATEGORY_MCP,
    CATEGORY_LOCAL_BROWSER,
})

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"
RISK_UNKNOWN = "unknown"

KNOWN_RISKS: frozenset[str] = frozenset({
    RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL,
})


@dataclass(frozen=True)
class ActionMeta:
    action: str
    category: str
    risk_level: str
    requires_secret: bool
    requires_browser: bool
    read_only: bool
    # approval_policy 에서 file_path 강제 여부. 대부분의 액션은 파일 기반이라
    # 기본 True 로 둬 기존 6종 웹/시크릿 + Excel 전체의 의미를 유지한다.
    # cad.health 처럼 파일 없이 동작하는 health-check 류 액션만 False.
    requires_file_path: bool = True
    # approval_policy 에서 write 액션에 save_as 를 강제할지 여부. 대부분
    # 로컬 쓰기 액션(excel_write_cell / cad.add_text_save_as 등)은 원본 보호를
    # 위해 save_as 필수 — 기본 True 유지. 서버 리소스에 대한 HTTP 조작류
    # CAD API write 액션(cad.create_project, cad.update_project, …) 만 False.
    requires_save_as: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or not self.action:
            raise ValueError("action must be a non-empty string")
        if self.category not in KNOWN_CATEGORIES:
            raise ValueError(
                f"unknown category: {self.category!r} "
                f"(expected one of {sorted(KNOWN_CATEGORIES)})"
            )
        if self.risk_level not in KNOWN_RISKS:
            raise ValueError(
                f"unknown risk_level: {self.risk_level!r} "
                f"(expected one of {sorted(KNOWN_RISKS)})"
            )


# ── 레지스트리 (기본값) ────────────────────────────────────────────────
_REGISTRY: dict[str, ActionMeta] = {
    "ping": ActionMeta(
        action="ping",
        category=CATEGORY_SYSTEM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
    ),
    "get_system_info": ActionMeta(
        action="get_system_info",
        category=CATEGORY_SYSTEM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
    ),
    "open_page_readonly": ActionMeta(
        action="open_page_readonly",
        category=CATEGORY_WEB,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=True,
        read_only=True,
    ),
    "inspect_page": ActionMeta(
        action="inspect_page",
        category=CATEGORY_WEB,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=True,
        read_only=True,
    ),
    # login_with_secret / inspect_after_login 은 username/password fill + submit click
    # 을 **제한적으로** 수행하므로 read_only=False.
    "login_with_secret": ActionMeta(
        action="login_with_secret",
        category=CATEGORY_SECRET,
        risk_level=RISK_HIGH,
        requires_secret=True,
        requires_browser=True,
        read_only=False,
    ),
    "inspect_after_login": ActionMeta(
        action="inspect_after_login",
        category=CATEGORY_SECRET,
        risk_level=RISK_HIGH,
        requires_secret=True,
        requires_browser=True,
        read_only=False,
    ),
    # Excel 1단계: 읽기 + 결과 복사본 저장 (원본 overwrite 금지).
    "excel_read_sheet": ActionMeta(
        action="excel_read_sheet",
        category=CATEGORY_EXCEL,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
    ),
    "excel_write_report_copy": ActionMeta(
        action="excel_write_report_copy",
        category=CATEGORY_EXCEL,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
    ),
    # Excel 2단계: 구조 요약 / 헤더 기반 표 읽기 (둘 다 read-only).
    "excel_describe_workbook": ActionMeta(
        action="excel_describe_workbook",
        category=CATEGORY_EXCEL,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
    ),
    "excel_read_table": ActionMeta(
        action="excel_read_table",
        category=CATEGORY_EXCEL,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
    ),
    # Excel COM (B안 4단계): 실제 Excel 데스크톱 앱 제어. 모두 excel_com 카테고리.
    "excel.run_poc": ActionMeta(
        action="excel.run_poc",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=False,  # B2 쓰기 + save 포함
    ),
    "excel.read_cell": ActionMeta(
        action="excel.read_cell",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
    ),
    "excel.write_cell": ActionMeta(
        action="excel.write_cell",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
    ),
    "excel.save_as": ActionMeta(
        action="excel.save_as",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
    ),
    # Excel COM read-only probe (B안 1-2단계): 실행 중인 Excel 감지 + workbook 정보 조회.
    # - GetActiveObject 사용하여 이미 열려 있는 Excel만 대상
    # - 파일 경로/변경사항 감지
    # - UsedRange, Sheet 정보 조회
    # - 저장/종료 없음
    "excel.probe_active_workbook": ActionMeta(
        action="excel.probe_active_workbook",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,  # 실행 중인 Excel 대상이므로 파일 경로 불필요
    ),
    # Excel COM write 액션: 헤더명 기반 셀 수정 + 복사본 저장 (원본 보호).
    "excel.update_cell_by_header_copy": ActionMeta(
        action="excel.update_cell_by_header_copy",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
        requires_file_path=False,  # 실행 중인 Excel 대상이므로 파일 경로 불필요
        requires_save_as=True,  # 복사본 저장만 허용, 원본 overwrite 금지
    ),
    # Excel COM write 액션: 헤더명 기반 행 추가 + 복사본 저장 (원본 보호).
    "excel.insert_row_by_header_copy": ActionMeta(
        action="excel.insert_row_by_header_copy",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
        requires_file_path=False,
        requires_save_as=True,
    ),
    # Excel COM write 액션: 헤더명 기반 열 추가 + 복사본 저장 (원본 보호).
    "excel.insert_column_by_header_copy": ActionMeta(
        action="excel.insert_column_by_header_copy",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
        requires_file_path=False,
        requires_save_as=True,
    ),
    # Excel COM write 액션: 헤더명 기반 수식 입력 + 복사본 저장 (원본 보호).
    "excel.write_formula_by_header_copy": ActionMeta(
        action="excel.write_formula_by_header_copy",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
        requires_file_path=False,
        requires_save_as=True,
    ),
    # Excel COM 분석 액션: 실행 중인 Excel의 표 구조 분석 (read-only, safe).
    "excel.analyze_workbook": ActionMeta(
        action="excel.analyze_workbook",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,  # GetActiveObject 기반
        requires_save_as=False,  # read-only 작업
    ),
    # Excel COM 분석 액션: 데이터 품질 검증 (read-only, safe).
    "excel.validate_data_quality": ActionMeta(
        action="excel.validate_data_quality",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
    ),
    # Excel COM 분석 액션: 수식 검증 (read-only, safe).
    "excel.validate_formulas": ActionMeta(
        action="excel.validate_formulas",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
    ),
    # Excel COM 보고 액션: 종합 분석 보고서 생성 (read-only, safe).
    "excel.generate_analysis_report": ActionMeta(
        action="excel.generate_analysis_report",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
    ),
    # Excel COM 구조 분석 액션: 활성 시트 상세 구조 분석 (EXCEL-PC-4A 고도화).
    # 병합셀, 숨김행/열, AutoFilter, 표 영역, 헤더/합계 행, 수식, 숫자텍스트 감지 (read-only, safe).
    "excel.analyze_active_sheet_structure": ActionMeta(
        action="excel.analyze_active_sheet_structure",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
    ),
    # Excel COM 계획 액션: 변경 계획 수립 (EXCEL-PC-4B 고도화).
    # 복합 작업 계획 dry-run, 승인 필요도 분석, 저장 모드 결정 (read-only, safe).
    "excel.plan_changes": ActionMeta(
        action="excel.plan_changes",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
    ),
    # Excel COM 실행 액션: 승인된 계획을 복사본으로 실행 (EXCEL-PC-5A 고도화).
    # Operation 순차 실행, 원본 저장 금지, SaveCopyAs만 허용 (requires approval).
    "excel.apply_change_plan_copy": ActionMeta(
        action="excel.apply_change_plan_copy",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,  # 실제 쓰기 작업 수행
        requires_file_path=False,  # GetActiveObject 기반
        requires_save_as=True,  # SaveCopyAs 필수 (원본 보호)
    ),
    # Excel COM 검증 액션: 활성 workbook 자동 검증 (EXCEL-PC-5B 고도화).
    # 수식 패턴, 합계, 타입, 필수 열 등 검증 (read-only, safe).
    "excel.validate_active_workbook": ActionMeta(
        action="excel.validate_active_workbook",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
    ),
    # Excel COM 검증 액션: 변경 결과 검증 (EXCEL-PC-5B 고도화).
    # 변경 전후 비교, diff 생성, 영향도 분석 (read-only, safe).
    "excel.validate_change_result": ActionMeta(
        action="excel.validate_change_result",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
    ),
    # CAD COM 액션 편입 (2단계). POC 검증이 끝난 cad_com_connector 를 재사용.
    # - cad.health           : 실제 파일 없이 AutoCAD 사용 가능 여부만 점검.
    # - cad.open_info        : 원본 DWG 를 열고 기본 정보만 반환 (read-only).
    # - cad.add_text_save_as : ModelSpace 에 테스트 텍스트 1개 추가 후 반드시
    #                          save_as 로만 저장 (원본 overwrite 금지).
    "cad.health": ActionMeta(
        action="cad.health",
        category=CATEGORY_CAD,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
    ),
    "cad.open_info": ActionMeta(
        action="cad.open_info",
        category=CATEGORY_CAD,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
    ),
    "cad.add_text_save_as": ActionMeta(
        action="cad.add_text_save_as",
        category=CATEGORY_CAD,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
    ),
    # local_agent 전용. 사용자 PC 의 visible 브라우저(msedge/chrome/chromium)를
    # 전용 HaehanAI 프로필로 띄운다. 자동 입력/쿠키 수집/headless/디버깅 포트는
    # 일절 수행하지 않으며, 사용자가 화면을 보면서 직접 로그인하는 흐름이라
    # read_only=True. 그래도 외부 프로세스 spawn 자체가 medium risk.
    "open_local_browser": ActionMeta(
        action="open_local_browser",
        category=CATEGORY_LOCAL_BROWSER,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=True,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
    ),
    # local_agent 전용 (E-2). 사용자 PC 의 visible 브라우저를 dedicated
    # HaehanAI 프로필로 띄우고 Playwright API 로 read-only 관찰 (URL/title/
    # context.pages 만). page.content / cookies / storage_state 는 호출하지
    # 않으므로 read_only=True. 외부 프로세스 spawn + Playwright 실행이라
    # medium risk.
    "open_local_browser_probe": ActionMeta(
        action="open_local_browser_probe",
        category=CATEGORY_LOCAL_BROWSER,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=True,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
    ),
    # local_agent 전용 (F-4B). 공개 웹페이지를 fresh BrowserContext (no
    # storage_state / no persistent profile) 로 열어 read-only 로 구조를
    # 수집하고 page_state 를 1차 분류한다. 사용자 세션/쿠키/스토리지를
    # 절대 건드리지 않고 page.fill / click / type / press / keyboard / mouse /
    # cookies / storage_state / evaluate 도 호출하지 않는다. 외부 프로세스
    # spawn + Playwright 실행이라 medium risk.
    "observe_public_browser_page": ActionMeta(
        action="observe_public_browser_page",
        category=CATEGORY_LOCAL_BROWSER,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=True,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
    ),
}


# ──────────────────────────────────────────────────────────────────
# CAD API 액션 편입 (3단계).
# cad-quantity(cad-backend) REST API 42종을 로컬 agent action 으로 확장.
# orchestrator 의 /api/v1/cad/* 프록시를 거쳐 호출되며, requires_file_path
# 및 requires_save_as 는 기본 False (서버 리소스 조작이라 로컬 파일/경로
# 불필요). upload_drawing 만 requires_file_path=True 의 예외.
# ──────────────────────────────────────────────────────────────────
def _register_cad_api_actions() -> None:
    """cad_api_spec.CAD_API_ACTIONS 를 순회해 ActionMeta 로 등록."""
    # 지연 import (module import 순환 방지 — cad_api_spec 는 순수 데이터).
    from .cad_api_spec import CAD_API_ACTIONS

    _RISK_MAP = {"low": RISK_LOW, "medium": RISK_MEDIUM}
    for spec in CAD_API_ACTIONS:
        if spec.action in _REGISTRY:
            raise ValueError(f"cad_api action 이름 충돌: {spec.action!r}")
        risk = _RISK_MAP.get(spec.risk_level)
        if risk is None:
            raise ValueError(
                f"{spec.action}: 알 수 없는 risk_level {spec.risk_level!r}"
            )
        _REGISTRY[spec.action] = ActionMeta(
            action=spec.action,
            category=CATEGORY_CAD,
            risk_level=risk,
            requires_secret=False,
            requires_browser=False,
            read_only=spec.read_only,
            requires_file_path=spec.requires_file_path,
            requires_save_as=spec.requires_save_as,
        )


_register_cad_api_actions()


# ── 조회 API ───────────────────────────────────────────────────────────
def get_meta(action: str) -> Optional[ActionMeta]:
    if not isinstance(action, str):
        return None
    return _REGISTRY.get(action)


def is_known_action(action: str) -> bool:
    return isinstance(action, str) and action in _REGISTRY


def list_actions() -> list[str]:
    return sorted(_REGISTRY.keys())


def category_of(action: str) -> str:
    m = get_meta(action)
    return m.category if m else CATEGORY_UNKNOWN


def risk_of(action: str) -> str:
    m = get_meta(action)
    return m.risk_level if m else RISK_UNKNOWN


__all__ = [
    "ActionMeta",
    "CATEGORY_SYSTEM",
    "CATEGORY_WEB",
    "CATEGORY_SECRET",
    "CATEGORY_UNKNOWN",
    "CATEGORY_EXCEL",
    "CATEGORY_EXCEL_COM",
    "CATEGORY_CAD",
    "CATEGORY_MCP",
    "CATEGORY_LOCAL_BROWSER",
    "KNOWN_CATEGORIES",
    "RISK_LOW",
    "RISK_MEDIUM",
    "RISK_HIGH",
    "RISK_CRITICAL",
    "RISK_UNKNOWN",
    "KNOWN_RISKS",
    "get_meta",
    "is_known_action",
    "list_actions",
    "category_of",
    "risk_of",
]
