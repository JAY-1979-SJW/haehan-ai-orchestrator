"""action 별 실행 분기 (B안 2단계 + CAD 액션 편입 2단계).

로컬 에이전트가 받은 task dict 를 받아 실제 COM 동작으로 번역한다.
기존 ``excel_com_connector`` 에 더해 POC 검증이 끝난
``cad_com_connector`` 도 동일 dispatch 로 연결한다. 여기서는 새 COM 기능을
추가하지 않고, 이미 검증된 함수만 엮는다.

지원 action:
- Excel COM
    ``excel.run_poc``    — A1 읽기 / B2 쓰기 / 저장 통합 POC
    ``excel.read_cell``  — 단일 셀 읽기 (read-only open)
    ``excel.write_cell`` — 단일 셀 쓰기 후 저장 (save_as 권장)
    ``excel.save_as``    — 다른 이름으로 현재 상태 저장 (원본 보호)
- CAD COM (2단계 편입)
    ``cad.health``           — AutoCAD 사용 가능 여부 점검 (read-only)
    ``cad.open_info``        — DWG 열고 기본 정보만 반환 (read-only)
    ``cad.add_text_save_as`` — ModelSpace 에 Text 추가 후 반드시 save_as 로만 저장

task 공통 필드:
    ``id``, ``action``, ``file_path``, ``visible``
Excel 추가 필드: ``sheet_name``, ``cell_ref``, ``value``, ``save_as``
CAD 추가 필드:   ``save_as``, ``text``, ``x``, ``y``, ``z``, ``height``

반환: ``{ok: bool, data: dict, error: Optional[str]}``
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import httpx

from . import errors as _err
from .cad_api_spec import CAD_API_ACTIONS, CadApiAction
from .connectors import cad_com_connector as cad_com
from .connectors import excel_com_connector as com

logger = logging.getLogger(__name__)

ACTION_NOT_SUPPORTED = "action_not_supported"
FILE_PATH_REQUIRED = "file_path_required"
SAVE_AS_REQUIRED = "save_as_required"

# ── CAD API 프록시 호출 설정 ──────────────────────────────────────────
# agent 가 orchestrator 의 /api/v1/cad/* 프록시로 HTTP 요청을 보낼 때
# 사용하는 base URL / 자격증명 / 타임아웃. env 로 주입.
def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name, default)
    return v.strip() if isinstance(v, str) else default


def _cad_proxy_base() -> str:
    return (
        _env("AGENT_CAD_PROXY_URL", "http://127.0.0.1:8400")
        or "http://127.0.0.1:8400"
    ).rstrip("/")


def _cad_proxy_auth() -> Optional[tuple]:
    u = _env("AGENT_CAD_PROXY_USER")
    p = os.environ.get("AGENT_CAD_PROXY_PASSWORD", "")
    if not u:
        return None
    return (u, p)


def _cad_proxy_timeout() -> float:
    try:
        v = float(_env("AGENT_CAD_PROXY_TIMEOUT_SEC", "60"))
        return v if 0 < v <= 600 else 60.0
    except (TypeError, ValueError):
        return 60.0

# cad.add_text_save_as 의 text 길이 상한. 너무 긴 문자열이 들어오면
# 입력 단계에서 바로 표준 코드로 거절한다. ModelSpace 단일 엔터티용이라
# 실무 상한은 훨씬 낮아도 충분.
_CAD_TEXT_MAX_LEN = 2000


def _bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def _result(ok: bool, *, data: Optional[dict] = None, error: Optional[str] = None) -> dict:
    return {"ok": bool(ok), "data": dict(data or {}), "error": error}


def _run_excel_poc(task: dict) -> dict:
    file_path = task.get("file_path", "")
    if not file_path:
        return _result(False, error=FILE_PATH_REQUIRED)
    out = com.run_basic_poc(
        file_path=file_path,
        sheet_name=task.get("sheet_name", "Sheet1") or "Sheet1",
        visible=_bool(task.get("visible")),
        save_as=task.get("save_as") or None,
    )
    return _result(bool(out.get("ok")), data=out, error=out.get("error"))


def _open_session(
    file_path: str, *, visible: bool, read_only: bool,
) -> tuple[Any, Any, Optional[str]]:
    app, err = com.open_excel_app(visible=visible)
    if err or app is None:
        return None, None, err
    wb, err = com.open_workbook(app, file_path, read_only=read_only)
    if err or wb is None:
        com.quit_excel(app)
        return app, None, err
    return app, wb, None


def _close_session(app: Any, wb: Any) -> None:
    if wb is not None:
        com.close_workbook(wb, save_changes=False)
    if app is not None:
        com.quit_excel(app)


def _run_read_cell(task: dict) -> dict:
    file_path = task.get("file_path", "")
    if not file_path:
        return _result(False, error=FILE_PATH_REQUIRED)
    sheet = task.get("sheet_name", "Sheet1") or "Sheet1"
    cell_ref = task.get("cell_ref", "A1") or "A1"
    visible = _bool(task.get("visible"))

    app, wb, err = _open_session(file_path, visible=visible, read_only=True)
    if err:
        _close_session(app, wb)
        return _result(False, data={"cell_ref": cell_ref}, error=err)
    try:
        value, err = com.read_cell(wb, sheet, cell_ref)
        if err:
            return _result(False, data={"cell_ref": cell_ref}, error=err)
        return _result(True, data={
            "sheet_name": sheet, "cell_ref": cell_ref, "value": value,
        })
    finally:
        _close_session(app, wb)


def _run_write_cell(task: dict) -> dict:
    file_path = task.get("file_path", "")
    if not file_path:
        return _result(False, error=FILE_PATH_REQUIRED)
    sheet = task.get("sheet_name", "Sheet1") or "Sheet1"
    cell_ref = task.get("cell_ref", "A1") or "A1"
    value = task.get("value")
    save_as = task.get("save_as") or None
    visible = _bool(task.get("visible"))

    app, wb, err = _open_session(file_path, visible=visible, read_only=False)
    if err:
        _close_session(app, wb)
        return _result(False, data={"cell_ref": cell_ref}, error=err)
    try:
        err = com.write_cell(wb, sheet, cell_ref, value)
        if err:
            return _result(False, data={"cell_ref": cell_ref}, error=err)
        # 기본 정책: save_as 가 있으면 다른 이름 저장, 없으면 원본 Save.
        if save_as:
            err = com.save_workbook_as(wb, save_as)
        else:
            err = com.save_workbook(wb)
        if err:
            return _result(False, data={
                "cell_ref": cell_ref, "written_value": value,
                "save_as": save_as,
            }, error=err)
        return _result(True, data={
            "sheet_name": sheet, "cell_ref": cell_ref,
            "written_value": value, "saved": True, "save_as": save_as,
        })
    finally:
        _close_session(app, wb)


def _run_save_as(task: dict) -> dict:
    file_path = task.get("file_path", "")
    save_as = task.get("save_as") or None
    if not file_path:
        return _result(False, error=FILE_PATH_REQUIRED)
    if not save_as:
        return _result(False, error="save_as_required")
    visible = _bool(task.get("visible"))

    app, wb, err = _open_session(file_path, visible=visible, read_only=False)
    if err:
        _close_session(app, wb)
        return _result(False, error=err)
    try:
        err = com.save_workbook_as(wb, save_as)
        if err:
            return _result(False, data={"save_as": save_as}, error=err)
        return _result(True, data={"save_as": save_as, "saved": True})
    finally:
        _close_session(app, wb)


def _run_excel_probe_active_workbook(task: dict) -> dict:
    """실행 중인 Excel 의 활성 워크북 정보를 read-only 로 조회.

    GetActiveObject 기반으로 이미 실행 중인 Excel 만 대상.
    file_path 불필요. Save/Close/Quit 호출 없음.
    """
    out = com.probe_active_workbook_readonly()
    # connector 반환 dict 에서 success/error 를 분리하고 나머지는 data 로 노출.
    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error_code")}
    return _result(ok, data=data, error=out.get("error_code"))


def _run_excel_update_cell_by_header_copy(task: dict) -> dict:
    """헤더명 기준 셀을 찾아 값을 수정하고 복사본으로 저장.

    GetActiveObject 기반으로 이미 실행 중인 Excel 만 대상.
    file_path 불필요. 원본 Save 호출 없음, 복사본만 저장.

    Required params:
    - row_match_header: 행 식별용 헤더명
    - row_match_value: 행 식별용 셀값
    - target_header: 수정 대상 헤더명
    - new_value: 새 값
    - approval_token: 승인 토큰

    Optional params:
    - output_path: 복사본 저장 경로
    """
    # approval_token 검증
    approval_token = task.get("approval_token")
    if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
        return _result(False, error=_err.WRITE_APPROVAL_REQUIRED)

    row_match_header = task.get("row_match_header", "")
    row_match_value = task.get("row_match_value")
    target_header = task.get("target_header", "")
    new_value = task.get("new_value")
    output_path = task.get("output_path")

    if not row_match_header or not target_header or row_match_value is None:
        return _result(False, error="INVALID_PARAMS")

    out = com.update_cell_by_header_and_row_copy(
        row_match_header=row_match_header,
        row_match_value=row_match_value,
        target_header=target_header,
        new_value=new_value,
        output_path=output_path,
        approval_token=approval_token,
        allow_write=True,
    )

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_insert_row_by_header_copy(task: dict) -> dict:
    """헤더 기준으로 행을 찾아, 그 행 위/아래에 새 행을 추가하고 값을 입력한다.

    GetActiveObject 기반으로 이미 실행 중인 Excel 만 대상.
    file_path 불필요. 원본 Save 호출 없음, 복사본만 저장.

    Required params:
    - row_match_header: 행 식별용 헤더명
    - row_match_value: 행 식별용 셀값
    - approval_token: 승인 토큰

    Optional params:
    - position: "below" | "above" (기본값: "below")
    - values: {"header_name": value, ...}
    - output_path: 복사본 저장 경로
    """
    approval_token = task.get("approval_token")
    if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
        return _result(False, error=_err.WRITE_APPROVAL_REQUIRED)

    row_match_header = task.get("row_match_header", "")
    row_match_value = task.get("row_match_value")
    position = task.get("position", "below") or "below"
    values = task.get("values")
    output_path = task.get("output_path")

    if not row_match_header or row_match_value is None:
        return _result(False, error="INVALID_PARAMS")

    out = com.insert_row_by_header_copy(
        row_match_header=row_match_header,
        row_match_value=row_match_value,
        position=position,
        values=values,
        output_path=output_path,
        approval_token=approval_token,
        allow_write=True,
    )

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_insert_column_by_header_copy(task: dict) -> dict:
    """헤더 기준으로 열을 추가한다.

    GetActiveObject 기반으로 이미 실행 중인 Excel 만 대상.
    file_path 불필요. 원본 Save 호출 없음, 복사본만 저장.

    Required params:
    - anchor_header: 기준 헤더명
    - new_header: 새 헤더명
    - approval_token: 승인 토큰

    Optional params:
    - position: "right" | "left" (기본값: "right")
    - output_path: 복사본 저장 경로
    """
    approval_token = task.get("approval_token")
    if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
        return _result(False, error=_err.WRITE_APPROVAL_REQUIRED)

    anchor_header = task.get("anchor_header", "")
    new_header = task.get("new_header", "")
    position = task.get("position", "right") or "right"
    output_path = task.get("output_path")

    if not anchor_header or not new_header:
        return _result(False, error="INVALID_PARAMS")

    out = com.insert_column_by_header_copy(
        anchor_header=anchor_header,
        new_header=new_header,
        position=position,
        output_path=output_path,
        approval_token=approval_token,
        allow_write=True,
    )

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_analyze_workbook(task: dict) -> dict:
    """활성 Excel의 표 구조를 분석한다 (read-only).

    GetActiveObject 기반으로 이미 실행 중인 Excel만 대상.
    file_path 불필요, 승인 불필요 (read-only).

    Optional params: 없음
    """
    out = com.analyze_active_workbook()

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_analyze_active_sheet_structure(task: dict) -> dict:
    """활성 시트의 상세 구조를 분석한다 (read-only, EXCEL-PC-4A 고도화).

    병합셀, 숨김행/열, AutoFilter, 표 영역, 헤더/합계 행, 수식, 숫자텍스트 감지.
    GetActiveObject 기반으로 이미 실행 중인 Excel만 대상.
    file_path 불필요, 승인 불필요 (read-only).

    Optional params: 없음
    """
    out = com.analyze_active_sheet_structure()

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_plan_changes(task: dict) -> dict:
    """변경 계획을 수립한다 (dry-run, 절대 실제 수정 없음).

    GetActiveObject 기반으로 이미 실행 중인 Excel만 대상.
    file_path 불필요, 승인 불필요 (read-only planning).

    Required params:
        operations: [{"type": str, "sheet": str, "params": dict}, ...]

    Optional params: 없음
    """
    operations = task.get("operations")

    if not isinstance(operations, list):
        return _result(False, error="INVALID_OPERATIONS_FORMAT")

    out = com.plan_changes(operations=operations)

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_apply_change_plan_copy(task: dict) -> dict:
    """승인된 계획을 복사본으로 실행한다.

    GetActiveObject 기반으로 이미 실행 중인 Excel만 대상.
    file_path 불필요, 승인 필수 (write action).
    SaveCopyAs로만 저장 (원본 저장 금지).

    Required params:
        plan: ChangePlan dict
        output_path: 복사본 저장 경로
        approval_token: 승인 토큰

    Optional params: 없음
    """
    plan_dict = task.get("plan")
    output_path = task.get("output_path")
    approval_token = task.get("approval_token")

    # 승인 확인
    if not approval_token:
        return _result(False, error="APPROVAL_REQUIRED")

    if not isinstance(plan_dict, dict):
        return _result(False, error="INVALID_PLAN_FORMAT")

    if not output_path:
        return _result(False, error="OUTPUT_PATH_REQUIRED")

    out = com.apply_change_plan_copy(
        plan=plan_dict,
        output_path=output_path,
        approval_token=approval_token,
    )

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_validate_active_workbook(task: dict) -> dict:
    """활성 workbook을 자동 검증한다 (read-only).

    GetActiveObject 기반으로 이미 실행 중인 Excel만 대상.
    file_path 불필요, 승인 불필요 (read-only).

    Optional params:
        required_columns: [str, ...] 필수 열 목록
        total_row_indices: [int, ...] 합계 행 인덱스

    Optional params: 없음
    """
    out = com.validate_active_workbook()

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_validate_change_result(task: dict) -> dict:
    """변경 결과를 검증한다 (read-only).

    GetActiveObject 기반으로 이미 실행 중인 Excel만 대상.
    file_path 불필요, 승인 불필요 (read-only).

    Optional params:
        before_state: 변경 전 상태 dict
        change_log: 변경 로그 dict

    Optional params: 없음
    """
    before_state = task.get("before_state")
    change_log = task.get("change_log")

    out = com.validate_change_result(
        before_state=before_state,
        change_log=change_log,
    )

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_create_review_summary_sheet_copy(task: dict) -> dict:
    """AI 검토 요약 시트를 생성하고 복사본으로 저장한다.

    GetActiveObject 기반으로 이미 실행 중인 Excel만 대상.
    file_path 불필요, 승인 필수 (write action, sheet 추가).
    SaveCopyAs로만 저장 (원본 저장 금지).

    Required params:
        output_path: 복사본 저장 경로
        approval_token: 승인 토큰

    Optional params:
        change_log: 변경 로그 dict
        validation_report: 검증 보고서 dict

    Optional params: 없음
    """
    output_path = task.get("output_path")
    approval_token = task.get("approval_token")
    change_log = task.get("change_log")
    validation_report = task.get("validation_report")

    # 승인 확인
    if not approval_token:
        return _result(False, error="APPROVAL_REQUIRED")

    if not output_path:
        return _result(False, error="OUTPUT_PATH_REQUIRED")

    out = com.create_review_summary_sheet_copy(
        output_path=output_path,
        approval_token=approval_token,
        change_log=change_log,
        validation_report=validation_report,
    )

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_validate_data_quality(task: dict) -> dict:
    """활성 Excel의 데이터 품질을 검증한다 (read-only).

    GetActiveObject 기반으로 이미 실행 중인 Excel만 대상.
    file_path 불필요, 승인 불필요 (read-only).

    Optional params: 없음
    """
    out = com.validate_data_quality()

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_validate_formulas(task: dict) -> dict:
    """활성 Excel의 수식을 검증한다 (read-only).

    GetActiveObject 기반으로 이미 실행 중인 Excel만 대상.
    file_path 불필요, 승인 불필요 (read-only).

    Optional params: 없음
    """
    out = com.validate_formulas()

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_generate_analysis_report(task: dict) -> dict:
    """활성 Excel의 종합 분석 보고서를 생성한다 (read-only).

    GetActiveObject 기반으로 이미 실행 중인 Excel만 대상.
    file_path 불필요, 승인 불필요 (read-only).

    Optional params: 없음
    """
    out = com.generate_analysis_report()

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _run_excel_write_formula_by_header_copy(task: dict) -> dict:
    """헤더 기준으로 셀/열에 수식을 입력한다.

    GetActiveObject 기반으로 이미 실행 중인 Excel 만 대상.
    file_path 불필요. 원본 Save 호출 없음, 복사본만 저장.

    Required params:
    - target_header: 대상 헤더명
    - formula: 수식
    - approval_token: 승인 토큰

    Optional params:
    - start_row: 시작 행
    - end_row: 종료 행
    - output_path: 복사본 저장 경로
    """
    approval_token = task.get("approval_token")
    if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
        return _result(False, error=_err.WRITE_APPROVAL_REQUIRED)

    target_header = task.get("target_header", "")
    formula = task.get("formula", "")
    start_row = task.get("start_row")
    end_row = task.get("end_row")
    output_path = task.get("output_path")

    if not target_header or not formula:
        return _result(False, error="INVALID_PARAMS")

    out = com.write_formula_by_header_copy(
        target_header=target_header,
        formula=formula,
        start_row=start_row,
        end_row=end_row,
        output_path=output_path,
        approval_token=approval_token,
        allow_write=True,
    )

    ok = bool(out.get("success"))
    data = {k: v for k, v in out.items() if k not in ("success", "error")}
    return _result(ok, data=data, error=out.get("error"))


# ──────────────────────────────────────────────────────────────────
# CAD COM 핸들러
#
# 공통 설계 원칙 (POC 에서 검증된 것을 그대로 답습):
# - 단일 Dispatch: ``open_cad_app`` 한 번만 호출하고 이후 전체 흐름에서
#   재Dispatch 하지 않는다. is_cad_available() 을 POC 직전에 호출하면
#   AutoCAD 가 RPC_E_SERVERFAULT 를 던지는 경우가 있어, healthcheck
#   (cad.health) 외에는 is_cad_available 을 호출하지 않는다.
# - finally 정리: 예외든 실패든 open 된 doc/app 은 반드시 정리.
# - 표준 에러 코드: connector 가 이미 CAD_* / FILE_* 표준 코드를 반환하므로
#   executor 는 그대로 올려준다. 추가 변환은 하지 않는다.
# ──────────────────────────────────────────────────────────────────
def _run_cad_health(task: dict) -> dict:
    """file_path 없이도 호출 가능. Dispatch+Quit 을 내부에서 수행한다."""
    out = cad_com.is_cad_available()
    # connector 반환 dict 에서 ok/error 를 분리하고 나머지는 data 로 노출.
    ok = bool(out.get("ok"))
    data = {k: v for k, v in out.items() if k not in ("ok", "error")}
    return _result(ok, data=data, error=out.get("error"))


def _cad_open_session(
    file_path: str, *, visible: bool,
) -> tuple[Any, Any, Optional[str]]:
    """CAD Application + Document 열기. 실패 시 남은 자원 정리 후 반환."""
    app, err, _progid = cad_com.open_cad_app(visible=visible)
    if err or app is None:
        return None, None, err or _err.CAD_APP_NOT_FOUND
    doc, err = cad_com.open_document(app, file_path)
    if err or doc is None:
        cad_com.quit_cad(app)
        return app, None, err or _err.CAD_DOCUMENT_OPEN_FAILED
    return app, doc, None


def _cad_close_session(app: Any, doc: Any) -> None:
    if doc is not None:
        cad_com.close_document(doc, save_changes=False)
    if app is not None:
        cad_com.quit_cad(app)


def _run_cad_open_info(task: dict) -> dict:
    file_path = task.get("file_path", "")
    if not file_path:
        return _result(False, error=FILE_PATH_REQUIRED)
    visible = _bool(task.get("visible"))

    app, doc, err = _cad_open_session(file_path, visible=visible)
    if err:
        _cad_close_session(app, doc)
        return _result(False, error=err)
    try:
        info, err = cad_com.get_document_info(doc)
        if err:
            return _result(False, error=err)
        return _result(True, data=dict(info or {}))
    finally:
        _cad_close_session(app, doc)


def _validate_cad_write_args(task: dict) -> tuple[Optional[dict], Optional[str]]:
    """cad.add_text_save_as 인자 파싱/검증.

    성공 시 정규화된 dict 반환, 실패 시 (None, err_code).
    - text 는 str 이어야 하고 길이 상한을 넘지 않아야 함.
    - x/y/z/height 는 float 변환 가능해야 함. height>0.
    - save_as 와 file_path 동일 금지 (approval_policy 에서 이미 거르지만
      executor 단독 호출 시나리오까지 방어).
    """
    file_path = task.get("file_path", "")
    save_as = task.get("save_as") or None
    if not file_path:
        return None, FILE_PATH_REQUIRED
    if not save_as:
        return None, SAVE_AS_REQUIRED
    if file_path == save_as:
        return None, _err.CAD_OVERWRITE_FORBIDDEN

    text = task.get("text", "POC_OK")
    if text is None:
        text = "POC_OK"
    if not isinstance(text, str):
        return None, _err.CAD_INVALID_ARGUMENT
    if len(text) == 0 or len(text) > _CAD_TEXT_MAX_LEN:
        return None, _err.CAD_INVALID_ARGUMENT

    # ``or <default>`` 를 쓰면 0.0 을 falsy 로 오해해 기본값으로 덮어쓴다.
    # 좌표 0 은 유효하므로, "키 자체가 없거나 None" 일 때만 기본값으로 대체.
    def _num(raw, default):
        if raw is None:
            return default
        return float(raw)

    try:
        x = _num(task.get("x", 0.0), 0.0)
        y = _num(task.get("y", 0.0), 0.0)
        z = _num(task.get("z", 0.0), 0.0)
        height = _num(task.get("height", 2.5), 2.5)
    except (TypeError, ValueError):
        return None, _err.CAD_INVALID_ARGUMENT
    if height <= 0:
        return None, _err.CAD_INVALID_ARGUMENT

    return (
        {
            "file_path": file_path,
            "save_as": save_as,
            "text": text,
            "x": x, "y": y, "z": z, "height": height,
            "visible": _bool(task.get("visible")),
        },
        None,
    )


def _run_cad_add_text_save_as(task: dict) -> dict:
    args, err = _validate_cad_write_args(task)
    if err or args is None:
        return _result(False, error=err)

    app, doc, err = _cad_open_session(args["file_path"], visible=args["visible"])
    if err:
        _cad_close_session(app, doc)
        return _result(False, error=err)
    try:
        ent_info, err = cad_com.add_test_text(
            doc,
            text=args["text"],
            x=args["x"], y=args["y"], z=args["z"],
            height=args["height"],
        )
        if err:
            return _result(False, error=err)
        err = cad_com.save_document_as(doc, args["save_as"])
        if err:
            return _result(False, data={"save_as": args["save_as"]}, error=err)
        return _result(True, data={
            "document_opened": True,
            "added_entity": ent_info,
            "saved_as": args["save_as"],
            "closed": True,
            "quit": True,
        })
    finally:
        _cad_close_session(app, doc)



# ══════════════════════════════════════════════════════════════════════
# CAD API 액션 (3단계 편입).
#
# cad-quantity(cad-backend) REST API 42종을 orchestrator 의 /api/v1/cad/*
# 프록시를 경유해 호출한다. 스펙은 agent/cad_api_spec.py 의 단일 소스
# (CAD_API_ACTIONS) 에 있고, 여기서 handler 를 자동 생성해 dispatch 에
# 편입한다.
#
# 설계 원칙:
# - httpx.Client 1회 요청 — 단일 dispatch 이므로 Connection pool 없이 충분.
# - 인증: AGENT_CAD_PROXY_USER/PASSWORD 로 HTTP Basic. 누락시 요청 차단.
# - 쓰기 액션의 approval_token/task_id 는 orchestrator 프록시의 승인 게이트로
#   전달되어야 한다. task['id'] → X-Task-Id, task['approval_token']
#   → X-Approval-Token-Id 헤더.
# - 상류 오류는 agent/errors.py 의 표준 CAD_PROXY_* 코드로 정규화.
# - 바이너리 응답(download_export) 은 base64 로 하지 않고 {"content_type",
#   "size"} 만 반환한다 (대용량 바이너리를 agent 결과에 올리는 것을 피하기
#   위함 — 실제 다운로드가 필요하면 별도 파이프라인에서 처리).
# ══════════════════════════════════════════════════════════════════════

def _resolve_path(spec: CadApiAction, task: dict) -> tuple[Optional[str], Optional[str]]:
    """path_template 에 task 로부터 path param 을 채워 실제 경로 생성."""
    vals: dict[str, Any] = {}
    for k in spec.path_params:
        v = task.get(k)
        if v is None or v == "":
            return None, _err.CAD_MISSING_PARAM
        vals[k] = str(v)
    try:
        return spec.path_template.format(**vals), None
    except (KeyError, IndexError):
        return None, _err.CAD_MISSING_PARAM


def _collect_query(spec: CadApiAction, task: dict) -> dict:
    """task 에서 spec.query_keys 만 추려서 query dict 구성 (None/"" 제외).

    호환: task["query"] dict 가 주어지면 병합(dict override).
    """
    out: dict[str, Any] = {}
    for k in spec.query_keys:
        if k in task and task[k] not in (None, ""):
            out[k] = task[k]
    extra = task.get("query")
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v not in (None, ""):
                out[str(k)] = v
    return out


def _collect_body(spec: CadApiAction, task: dict) -> Any:
    """쓰기 액션의 JSON body 수집. task['body'] 우선, 없으면 None."""
    if spec.body_kind != "json":
        return None
    body = task.get("body")
    if body is None:
        # body=None 을 허용하는 API 도 있으므로(빈 PATCH 등) 그대로 전달.
        return None
    return body


def _approval_headers(task: dict) -> dict:
    """task 의 id / approval_token 을 cad_proxy 가 이해하는 헤더로 변환."""
    hdr: dict[str, str] = {}
    tid = task.get("id") or task.get("task_id")
    tok = task.get("approval_token")
    if isinstance(tid, str) and tid:
        hdr["X-Task-Id"] = tid
    if isinstance(tok, str) and tok:
        hdr["X-Approval-Token-Id"] = tok
    return hdr


def _cad_api_call(
    method: str,
    path: str,
    *,
    task: dict,
    body: Any = None,
    query: Optional[dict] = None,
    files: Any = None,
) -> dict:
    """orchestrator 의 /api/v1/cad/<path> 로 httpx 요청."""
    base = _cad_proxy_base()
    auth = _cad_proxy_auth()
    if auth is None:
        return _result(False, error=_err.CAD_PROXY_AUTH_MISSING)
    url = f"{base}/api/v1/cad/{path.lstrip('/')}"
    headers = _approval_headers(task)
    timeout = _cad_proxy_timeout()
    try:
        with httpx.Client(timeout=timeout, auth=auth) as hc:
            resp = hc.request(
                method=method,
                url=url,
                headers=headers,
                params=query or None,
                json=body if files is None else None,
                files=files,
            )
    except httpx.TimeoutException:
        logger.info("cad_api_call timeout: %s %s", method, path)
        return _result(False, data={"path": path}, error=_err.CAD_PROXY_TIMEOUT)
    except (httpx.ConnectError, httpx.NetworkError) as e:
        logger.info("cad_api_call unreachable: %s %s (%s)",
                    method, path, type(e).__name__)
        return _result(False, data={"path": path},
                       error=_err.CAD_PROXY_UNREACHABLE)

    # 응답 파싱: content-type 에 따라 JSON / 그 외(바이너리)
    ctype = (resp.headers.get("content-type") or "").lower()
    data: dict
    if "application/json" in ctype:
        try:
            parsed = resp.json()
        except Exception:  # noqa: BLE001
            parsed = {"raw_text_preview": resp.text[:500]}
        data = parsed if isinstance(parsed, dict) else {"items": parsed}
    else:
        # 바이너리/HTML/CSV 등 — 본문을 싣지 않고 메타만 반환.
        data = {
            "content_type": ctype or "unknown",
            "size": len(resp.content),
        }

    ok = 200 <= resp.status_code < 300
    err: Optional[str] = None
    if not ok:
        err = f"{_err.CAD_PROXY_UPSTREAM_ERROR}:{resp.status_code}"
    data["status_code"] = resp.status_code
    data["path"] = path
    return _result(ok, data=data, error=err)


def _make_cad_api_handler(spec: CadApiAction):
    """spec 1개를 받아 handler 함수를 생성."""
    def _handler(task: dict) -> dict:
        path, err = _resolve_path(spec, task)
        if err or path is None:
            return _result(False, data={"action": spec.action}, error=err)
        query = _collect_query(spec, task)
        body = _collect_body(spec, task)
        return _cad_api_call(
            spec.method, path, task=task, body=body, query=query,
        )
    _handler.__name__ = f"_run_{spec.action.replace('.', '_')}"
    _handler.__qualname__ = _handler.__name__
    return _handler


def _run_cad_upload_drawing(task: dict) -> dict:
    """cad.upload_drawing — multipart 업로드 (로컬 파일 필요).

    필수 task 필드:
      - project_id
      - file_path (AGENT_WORK_DIR 내 절대경로; approval_policy 가 이미 검증)
    """
    project_id = task.get("project_id")
    if not project_id:
        return _result(False, error=_err.CAD_MISSING_PARAM)
    file_path = task.get("file_path", "")
    if not file_path:
        return _result(False, error=FILE_PATH_REQUIRED)
    p = Path(file_path)
    if not p.is_absolute() or not p.exists() or not p.is_file():
        return _result(False, error=_err.FILE_NOT_FOUND)
    try:
        data = p.read_bytes()
    except OSError as e:
        logger.info("upload_drawing read failed: %s", e)
        return _result(False, error=_err.FILE_NOT_ALLOWED)
    files = {"files": (p.name, data, "application/octet-stream")}
    path = f"projects/{project_id}/drawings/upload"
    return _cad_api_call(
        "POST", path, task=task, files=files,
    )


_DISPATCH = {
    "excel.run_poc": _run_excel_poc,
    "excel.read_cell": _run_read_cell,
    "excel.write_cell": _run_write_cell,
    "excel.save_as": _run_save_as,
    "excel.probe_active_workbook": _run_excel_probe_active_workbook,
    "excel.update_cell_by_header_copy": _run_excel_update_cell_by_header_copy,
    "excel.insert_row_by_header_copy": _run_excel_insert_row_by_header_copy,
    "excel.insert_column_by_header_copy": _run_excel_insert_column_by_header_copy,
    "excel.write_formula_by_header_copy": _run_excel_write_formula_by_header_copy,
    "excel.analyze_workbook": _run_excel_analyze_workbook,
    "excel.analyze_active_sheet_structure": _run_excel_analyze_active_sheet_structure,
    "excel.plan_changes": _run_excel_plan_changes,
    "excel.apply_change_plan_copy": _run_excel_apply_change_plan_copy,
    "excel.validate_active_workbook": _run_excel_validate_active_workbook,
    "excel.validate_change_result": _run_excel_validate_change_result,
    "excel.create_review_summary_sheet_copy": _run_excel_create_review_summary_sheet_copy,
    "excel.validate_data_quality": _run_excel_validate_data_quality,
    "excel.validate_formulas": _run_excel_validate_formulas,
    "excel.generate_analysis_report": _run_excel_generate_analysis_report,
    "cad.health": _run_cad_health,
    "cad.open_info": _run_cad_open_info,
    "cad.add_text_save_as": _run_cad_add_text_save_as,
}

# CAD API 42종을 스펙 테이블에서 자동 등록.
for _spec in CAD_API_ACTIONS:
    if _spec.action == "cad.upload_drawing":
        _DISPATCH[_spec.action] = _run_cad_upload_drawing
    else:
        _DISPATCH[_spec.action] = _make_cad_api_handler(_spec)


def supported_actions() -> list[str]:
    return sorted(_DISPATCH.keys())


def execute_task(task: dict) -> dict:
    """task dict 를 받아 action 분기 실행."""
    if not isinstance(task, dict):
        return _result(False, error="task_must_be_dict")
    action = task.get("action")
    if not isinstance(action, str) or not action:
        return _result(False, error=ACTION_NOT_SUPPORTED)
    handler = _DISPATCH.get(action)
    if handler is None:
        logger.info("unsupported action: %s", action)
        return _result(False, data={"action": action}, error=ACTION_NOT_SUPPORTED)
    try:
        return handler(task)
    except Exception as e:  # noqa: BLE001
        logger.exception("task handler crashed: %s", e)
        return _result(False, data={"action": action},
                       error=f"handler_crashed:{type(e).__name__}")


__all__ = [
    "execute_task",
    "supported_actions",
    "ACTION_NOT_SUPPORTED",
    "FILE_PATH_REQUIRED",
    "SAVE_AS_REQUIRED",
]
