"""action 메타데이터 레지스트리.

- 공통 인터페이스 (카테고리/리스크/요구자원) 를 등록해 app/log/감사 계층이 참조.
- 이번 단계에서는 **기존 action 6종만** 등록한다 (기능 추가 없음).
- 향후 excel / mcp 카테고리 확장 지점이 된다.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── 카테고리 / 리스크 상수 ──────────────────────────────────────────────
CATEGORY_SYSTEM = "system"
CATEGORY_WEB = "web"
CATEGORY_SECRET = "secret"  # noqa: S105
CATEGORY_UNKNOWN = "unknown"

# 향후 확장 지점 (이번 단계에서는 값으로만 존재):
CATEGORY_EXCEL = "excel"
CATEGORY_EXCEL_COM = "excel_com"
CATEGORY_HANCOM = "hancom"
CATEGORY_MCP = "mcp"
# local_agent.browser_launcher.open_local_browser 전용. 서버측 Playwright
# 경로와 분리해 visible 로컬 브라우저 기동만 다룬다.
CATEGORY_LOCAL_BROWSER = "local_browser"
CATEGORY_INVENTORY = "inventory"
# 로컬 환경 관리: 프로그램 설치, 파일 정리 등
CATEGORY_LOCAL_ENVIRONMENT = "local_environment"
# server-side Playwright browser automation (read/navigate 계열)
CATEGORY_BROWSER = "browser"

KNOWN_CATEGORIES: frozenset[str] = frozenset(
    {
        CATEGORY_SYSTEM,
        CATEGORY_WEB,
        CATEGORY_SECRET,
        CATEGORY_EXCEL,
        CATEGORY_EXCEL_COM,
        CATEGORY_HANCOM,
        CATEGORY_MCP,
        CATEGORY_LOCAL_BROWSER,
        CATEGORY_INVENTORY,
        CATEGORY_LOCAL_ENVIRONMENT,
        CATEGORY_BROWSER,
    }
)

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"
RISK_UNKNOWN = "unknown"

KNOWN_RISKS: frozenset[str] = frozenset(
    {
        RISK_LOW,
        RISK_MEDIUM,
        RISK_HIGH,
        RISK_CRITICAL,
    }
)


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
    # 파일 없이 동작하는 health-check 류 액션만 False.
    requires_file_path: bool = True
    # approval_policy 에서 write 액션에 save_as 를 강제할지 여부. 대부분
    # 로컬 쓰기 액션(excel_write_cell 등)은 원본 보호를
    # 위해 save_as 필수 — 기본 True 유지. 서버 리소스에 대한 HTTP 조작류
    # 액션만 False.
    requires_save_as: bool = True
    # 액션 실행 시 사용자 승인 필수 여부. 기본값은 read_only=False 시 True,
    # read_only=True 시 False. 하지만 read_only이면서도 privacy 영향이 있는
    # local_inventory.scan 처럼 명시적으로 True로 설정 가능.
    requires_approval: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or not self.action:
            raise ValueError("action must be a non-empty string")
        if self.category not in KNOWN_CATEGORIES:
            raise ValueError(f"unknown category: {self.category!r} (expected one of {sorted(KNOWN_CATEGORIES)})")
        if self.risk_level not in KNOWN_RISKS:
            raise ValueError(f"unknown risk_level: {self.risk_level!r} (expected one of {sorted(KNOWN_RISKS)})")


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
        requires_approval=True,
    ),
    "inspect_after_login": ActionMeta(
        action="inspect_after_login",
        category=CATEGORY_SECRET,
        risk_level=RISK_HIGH,
        requires_secret=True,
        requires_browser=True,
        read_only=False,
        requires_approval=True,
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
        requires_approval=True,
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
        requires_approval=True,
    ),
    "excel.save_as": ActionMeta(
        action="excel.save_as",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
        requires_approval=True,
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
        requires_approval=True,
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
        requires_approval=True,
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
        requires_approval=True,
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
        requires_approval=True,
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
        requires_approval=True,
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
    # Excel COM 보고서 액션: AI 검토 요약 시트 생성 (EXCEL-PC-6A 고도화).
    # 변경/검증 결과를 새 시트로 요약, SaveCopyAs만 허용 (requires approval).
    "excel.create_review_summary_sheet_copy": ActionMeta(
        action="excel.create_review_summary_sheet_copy",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,  # 시트 추가 = write 작업
        requires_file_path=False,  # GetActiveObject 기반
        requires_save_as=True,  # SaveCopyAs 필수 (원본 보호)
        requires_approval=True,
    ),
    # Excel COM PDF 내보내기 액션: Workbook/Sheet를 PDF로 저장 (EXCEL-PC-6B 고도화).
    # 복사본 기반 PDF 내보내기, 인쇄 영역 설정은 복사본에서만 허용 (requires approval).
    "excel.export_pdf_copy": ActionMeta(
        action="excel.export_pdf_copy",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,  # PDF 파일 생성 = write 작업
        requires_file_path=False,  # GetActiveObject 기반
        requires_save_as=True,  # 원본 보호 (PDF는 복사본 기반)
        requires_approval=True,
    ),
    # 업무팩: 건설/소방 Excel 자동화 (EXCEL-PC-7A 고도화).
    # 내역서/견적서/정산서 등의 자동 검토 및 검증.
    # DB 연결 없이 파일 내부 검토 먼저 구현 (추후 DB 연결 예정).
    "excel.pack.review_estimate_copy": ActionMeta(
        action="excel.pack.review_estimate_copy",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,  # 검토 시트 추가 = write 작업
        requires_file_path=False,  # GetActiveObject 기반
        requires_save_as=True,  # SaveCopyAs 필수 (원본 보호)
        requires_approval=True,
    ),
    "excel.pack.review_settlement_copy": ActionMeta(
        action="excel.pack.review_settlement_copy",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,  # 검토 시트 추가 = write 작업
        requires_file_path=False,  # GetActiveObject 기반
        requires_save_as=True,  # SaveCopyAs 필수 (원본 보호)
        requires_approval=True,
    ),
    "excel.pack.check_material_prices_copy": ActionMeta(
        action="excel.pack.check_material_prices_copy",
        category=CATEGORY_EXCEL_COM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,  # 검증 정보 시트 추가 = write 작업
        requires_file_path=False,  # GetActiveObject 기반
        requires_save_as=True,  # SaveCopyAs 필수 (원본 보호)
        requires_approval=True,
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
    # Hancom HWP → HWPX 변환 (1B): 한컴 HwpObject 자동화 기반.
    # - 공식 보안모듈 RegisterModule 사용
    # - 읽기 전용으로 열기 (원본 보호)
    # - SaveAs 기반 복사본 저장
    # - 보안모듈 미등록 시 SETUP_REQUIRED 반환
    "hancom.convert_hwp_to_hwpx_copy": ActionMeta(
        action="hancom.convert_hwp_to_hwpx_copy",
        category=CATEGORY_HANCOM,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
        requires_file_path=True,
        requires_save_as=True,
        requires_approval=True,
    ),
    # ── Local Inventory 액션 ────
    "local_inventory.scan": ActionMeta(
        action="local_inventory.scan",
        category=CATEGORY_INVENTORY,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=True,  # read_only이면서도 privacy 영향이 있어 동의 필수
    ),
    "local_inventory.status": ActionMeta(
        action="local_inventory.status",
        category=CATEGORY_INVENTORY,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=False,
    ),
    "local_inventory.compare": ActionMeta(
        action="local_inventory.compare",
        category=CATEGORY_INVENTORY,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=False,
    ),
    # 업무 프로그램 지도 생성 (inventory 기반)
    "local_inventory.build_app_map": ActionMeta(
        action="local_inventory.build_app_map",
        category=CATEGORY_INVENTORY,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=True,  # 메타데이터 분석이지만 사용자 PC 정보 활용이므로 승인 필수
    ),
    # 저장된 앱 지도 조회 (approval 불필요)
    "local_inventory.app_map_status": ActionMeta(
        action="local_inventory.app_map_status",
        category=CATEGORY_INVENTORY,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=False,
    ),
    # 파일 지도 스캔
    "local_file_map.scan": ActionMeta(
        action="local_file_map.scan",
        category=CATEGORY_INVENTORY,
        risk_level=RISK_MEDIUM,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=True,  # 메타데이터 분석이지만 사용자 PC 폴더 정보
    ),
    # 저장된 파일 지도 조회
    "local_file_map.status": ActionMeta(
        action="local_file_map.status",
        category=CATEGORY_INVENTORY,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=False,
    ),
    # 파일 정리 추천안 조회
    "local_file_map.suggest": ActionMeta(
        action="local_file_map.suggest",
        category=CATEGORY_INVENTORY,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=False,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=False,
    ),
    # 로컬 프로그램 설치 실행 (1C: dry_run 프레임워크)
    "local_software.install": ActionMeta(
        action="local_software.install",
        category=CATEGORY_LOCAL_ENVIRONMENT,
        risk_level=RISK_HIGH,
        requires_secret=False,
        requires_browser=False,
        read_only=False,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=True,
    ),
    # ── browser read/navigate 계열 (BROWSER_READ_NAVIGATE_ACTION_REGISTRY_1) ──
    # dispatcher 미연결 상태. production submit 불가. allowlist 정책 TODO 참조.
    # TODO: browser.plan_open_url allowlist_required 정책 별도 설계 필요
    "browser.inspect": ActionMeta(
        action="browser.inspect",
        category=CATEGORY_BROWSER,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=True,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=False,
    ),
    "browser.plan_click": ActionMeta(
        action="browser.plan_click",
        category=CATEGORY_BROWSER,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=True,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=False,
    ),
    "browser.plan_open_url": ActionMeta(
        action="browser.plan_open_url",
        category=CATEGORY_BROWSER,
        risk_level=RISK_LOW,
        requires_secret=False,
        requires_browser=True,
        read_only=True,
        requires_file_path=False,
        requires_save_as=False,
        requires_approval=False,
    ),
}


# ── 조회 API ───────────────────────────────────────────────────────────
def get_meta(action: str) -> ActionMeta | None:
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
    "CATEGORY_BROWSER",
    "CATEGORY_EXCEL",
    "CATEGORY_EXCEL_COM",
    "CATEGORY_HANCOM",
    "CATEGORY_INVENTORY",
    "CATEGORY_LOCAL_BROWSER",
    "CATEGORY_LOCAL_ENVIRONMENT",
    "CATEGORY_MCP",
    "CATEGORY_SECRET",
    "CATEGORY_SYSTEM",
    "CATEGORY_UNKNOWN",
    "CATEGORY_WEB",
    "KNOWN_CATEGORIES",
    "KNOWN_RISKS",
    "RISK_CRITICAL",
    "RISK_HIGH",
    "RISK_LOW",
    "RISK_MEDIUM",
    "RISK_UNKNOWN",
    "ActionMeta",
    "category_of",
    "get_meta",
    "is_known_action",
    "list_actions",
    "risk_of",
]
