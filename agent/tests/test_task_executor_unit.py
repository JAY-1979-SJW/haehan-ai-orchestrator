"""task_executor — mock 기반 단위 테스트.

실제 Excel COM 은 건드리지 않는다. excel_com_connector 함수들을
monkeypatch 로 대체해 dispatch 경로와 결과 포맷만 검증한다.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


@pytest.fixture()
def stub_com(monkeypatch):
    """excel_com_connector 를 통째로 stub 으로 교체."""
    from agent import task_executor as te

    calls: list[tuple[str, tuple, dict]] = []

    class _Stub:
        def run_basic_poc(self, **kw):
            calls.append(("run_basic_poc", (), kw))
            return {"ok": True, "file_path": kw.get("file_path"),
                    "read_value": "HELLO", "written_value": "POC_OK",
                    "saved": True, "error": None}

        def open_excel_app(self, visible=True):
            calls.append(("open_excel_app", (), {"visible": visible}))
            return object(), None

        def open_workbook(self, app, file_path, read_only=False):
            calls.append(("open_workbook", (), {
                "file_path": file_path, "read_only": read_only,
            }))
            return object(), None

        def read_cell(self, wb, sheet_name, cell_ref):
            calls.append(("read_cell", (sheet_name, cell_ref), {}))
            return "CELL_VAL", None

        def write_cell(self, wb, sheet_name, cell_ref, value):
            calls.append(("write_cell", (sheet_name, cell_ref, value), {}))
            return None

        def save_workbook(self, wb):
            calls.append(("save_workbook", (), {}))
            return None

        def save_workbook_as(self, wb, output_path):
            calls.append(("save_workbook_as", (output_path,), {}))
            return None

        def close_workbook(self, wb, save_changes=False):
            calls.append(("close_workbook", (), {"save_changes": save_changes}))

        def quit_excel(self, app):
            calls.append(("quit_excel", (), {}))

        def probe_active_workbook_readonly(self):
            calls.append(("probe_active_workbook_readonly", (), {}))
            return {
                "success": True,
                "excel_running": True,
                "error_code": None,
                "workbook_count": 1,
                "active_workbook": {
                    "name": "test.xlsx",
                    "sheet_count": 1,
                    "active_sheet": "Sheet1",
                    "used_range": "A1:B2",
                    "rows": 2,
                    "columns": 2,
                },
                "sample_cells": [],
                "read_only": True,
            }

    stub = _Stub()
    monkeypatch.setattr(te, "com", stub)
    return stub, calls


# ──────────────────────────────────────────────────────────────────
# dispatch 기본 동작
# ──────────────────────────────────────────────────────────────────
def test_unsupported_action_returns_clear_error(stub_com):
    from agent import task_executor as te
    out = te.execute_task({"action": "cad.run", "file_path": "x"})
    assert out["ok"] is False
    assert out["error"] == te.ACTION_NOT_SUPPORTED
    assert out["data"] == {"action": "cad.run"}


def test_task_must_be_dict():
    from agent import task_executor as te
    out = te.execute_task("not a dict")  # type: ignore[arg-type]
    assert out["ok"] is False
    assert out["error"] == "task_must_be_dict"


def test_missing_action():
    from agent import task_executor as te
    out = te.execute_task({"file_path": "x"})
    assert out["ok"] is False
    assert out["error"] == te.ACTION_NOT_SUPPORTED


def test_supported_actions_list():
    from agent import task_executor as te
    from agent.cad_api_spec import action_names as _cad_api_names

    # Excel 고도화 기준선 (EXCEL-PC stages 1-8B)
    excel_actions = {
        "excel.run_poc", "excel.read_cell", "excel.write_cell", "excel.save_as",
        "excel.probe_active_workbook",
        # Stage 1-2: 기본 작업
        "excel.analyze_workbook", "excel.analyze_active_sheet_structure",
        # Stage 3: 변경 계획
        "excel.plan_changes", "excel.apply_change_plan_copy",
        # Stage 2-4: 기본 워크플로우
        "excel.update_cell_by_header_copy", "excel.insert_row_by_header_copy",
        "excel.insert_column_by_header_copy", "excel.write_formula_by_header_copy",
        # Stage 4: 검증
        "excel.validate_active_workbook", "excel.validate_change_result",
        "excel.validate_data_quality", "excel.validate_formulas",
        # Stage 5: 보고서
        "excel.create_review_summary_sheet_copy",
        # Stage 6: PDF
        "excel.export_pdf_copy",
        # Stage 7: 팩
        "excel.pack.review_estimate_copy", "excel.pack.review_settlement_copy",
        "excel.pack.check_material_prices_copy",
        # Stage 8: 분석
        "excel.generate_analysis_report",
    }

    # Hancom 작업
    hancom_actions = {
        "hancom.convert_hwp_to_hwpx_copy",
    }

    expected = excel_actions | hancom_actions | {"cad.health", "cad.open_info", "cad.add_text_save_as"} | set(_cad_api_names())
    assert set(te.supported_actions()) == expected


# ──────────────────────────────────────────────────────────────────
# excel.run_poc
# ──────────────────────────────────────────────────────────────────
def test_run_poc_requires_file_path(stub_com):
    from agent import task_executor as te
    out = te.execute_task({"action": "excel.run_poc"})
    assert out["ok"] is False
    assert out["error"] == te.FILE_PATH_REQUIRED


def test_run_poc_delegates_to_com(stub_com):
    from agent import task_executor as te
    stub, calls = stub_com
    out = te.execute_task({
        "action": "excel.run_poc",
        "file_path": r"C:\tmp\s.xlsx",
        "sheet_name": "Sheet1",
        "visible": False,
        "save_as": r"C:\tmp\o.xlsx",
    })
    assert out["ok"] is True
    assert out["error"] is None
    assert out["data"]["saved"] is True
    names = [c[0] for c in calls]
    assert names == ["run_basic_poc"]
    kw = calls[0][2]
    assert kw["file_path"] == r"C:\tmp\s.xlsx"
    assert kw["save_as"] == r"C:\tmp\o.xlsx"
    assert kw["visible"] is False


# ──────────────────────────────────────────────────────────────────
# excel.read_cell
# ──────────────────────────────────────────────────────────────────
def test_read_cell_success(stub_com):
    from agent import task_executor as te
    stub, calls = stub_com
    out = te.execute_task({
        "action": "excel.read_cell",
        "file_path": r"C:\tmp\s.xlsx",
        "cell_ref": "A1",
    })
    assert out["ok"] is True
    assert out["data"]["value"] == "CELL_VAL"
    assert out["data"]["cell_ref"] == "A1"
    names = [c[0] for c in calls]
    # 열기/읽기/닫기/종료 순서 보장
    assert names == [
        "open_excel_app", "open_workbook",
        "read_cell", "close_workbook", "quit_excel",
    ]
    # read_only 로 열어야 함
    assert calls[1][2]["read_only"] is True


def test_read_cell_cleanup_on_failure(monkeypatch):
    from agent import task_executor as te

    class _Stub:
        def open_excel_app(self, visible=True):
            return object(), None

        def open_workbook(self, app, file_path, read_only=False):
            return object(), None

        def read_cell(self, wb, sheet_name, cell_ref):
            return None, "cell_read_failed"

        def close_workbook(self, wb, save_changes=False):
            self.closed = True

        def quit_excel(self, app):
            self.quit = True

    stub = _Stub()
    monkeypatch.setattr(te, "com", stub)
    out = te.execute_task({
        "action": "excel.read_cell",
        "file_path": r"C:\tmp\s.xlsx",
        "cell_ref": "A1",
    })
    assert out["ok"] is False
    assert out["error"] == "cell_read_failed"
    assert getattr(stub, "closed", False) is True
    assert getattr(stub, "quit", False) is True


def test_read_cell_open_workbook_failure(monkeypatch):
    from agent import task_executor as te

    class _Stub:
        def open_excel_app(self, visible=True):
            return object(), None

        def open_workbook(self, app, file_path, read_only=False):
            return None, "workbook_open_failed"

        def quit_excel(self, app):
            self.quit = True

        def close_workbook(self, wb, save_changes=False):
            pass

        def read_cell(self, *a, **k):  # 방어
            raise AssertionError("should not be called")

    stub = _Stub()
    monkeypatch.setattr(te, "com", stub)
    out = te.execute_task({
        "action": "excel.read_cell",
        "file_path": r"C:\tmp\s.xlsx",
        "cell_ref": "A1",
    })
    assert out["ok"] is False
    assert out["error"] == "workbook_open_failed"
    assert getattr(stub, "quit", False) is True


# ──────────────────────────────────────────────────────────────────
# excel.write_cell
# ──────────────────────────────────────────────────────────────────
def test_write_cell_requires_approval(stub_com):
    from agent import task_executor as te
    out = te.execute_task({
        "action": "excel.write_cell",
        "file_path": r"C:\tmp\s.xlsx",
        "save_as": r"C:\tmp\o.xlsx",
        "cell_ref": "B2",
        "value": "SRV_OK",
    })
    assert out["ok"] is False
    assert "approval" in out["error"].lower()


def test_write_cell_requires_save_as(stub_com):
    from agent import task_executor as te
    out = te.execute_task({
        "action": "excel.write_cell",
        "file_path": r"C:\tmp\s.xlsx",
        "approval_token": "test_token",
        "cell_ref": "B2",
        "value": 1,
    })
    assert out["ok"] is False
    assert out["error"] == "save_as_required"


def test_write_cell_with_approval_and_save_as(stub_com):
    from agent import task_executor as te
    stub, calls = stub_com
    out = te.execute_task({
        "action": "excel.write_cell",
        "file_path": r"C:\tmp\s.xlsx",
        "approval_token": "test_token",
        "save_as": r"C:\tmp\o.xlsx",
        "cell_ref": "B2",
        "value": "SRV_OK",
    })
    assert out["ok"] is True
    assert out["data"]["written_value"] == "SRV_OK"
    assert out["data"]["saved"] is True
    names = [c[0] for c in calls]
    assert names == [
        "open_excel_app", "open_workbook", "write_cell",
        "save_workbook_as", "close_workbook", "quit_excel",
    ]
    assert calls[1][2]["read_only"] is False


# ──────────────────────────────────────────────────────────────────
# excel.save_as
# ──────────────────────────────────────────────────────────────────
def test_save_as_requires_approval(stub_com):
    from agent import task_executor as te
    out = te.execute_task({
        "action": "excel.save_as",
        "file_path": r"C:\tmp\s.xlsx",
        "save_as": r"C:\tmp\o.xlsx",
    })
    assert out["ok"] is False
    assert "approval" in out["error"].lower()


def test_save_as_requires_output(stub_com):
    from agent import task_executor as te
    out = te.execute_task({
        "action": "excel.save_as",
        "file_path": r"C:\tmp\s.xlsx",
        "approval_token": "test_token",
    })
    assert out["ok"] is False
    assert out["error"] == "save_as_required"


def test_save_as_success(stub_com):
    from agent import task_executor as te
    stub, calls = stub_com
    out = te.execute_task({
        "action": "excel.save_as",
        "file_path": r"C:\tmp\s.xlsx",
        "approval_token": "test_token",
        "save_as": r"C:\tmp\o.xlsx",
    })
    assert out["ok"] is True
    assert out["data"]["save_as"] == r"C:\tmp\o.xlsx"
    names = [c[0] for c in calls]
    assert names == [
        "open_excel_app", "open_workbook", "save_workbook_as",
        "close_workbook", "quit_excel",
    ]


# ──────────────────────────────────────────────────────────────────
# excel.probe_active_workbook (read-only, no file_path required)
# ──────────────────────────────────────────────────────────────────
def test_probe_active_workbook_success(stub_com):
    from agent import task_executor as te
    stub, calls = stub_com
    out = te.execute_task({"action": "excel.probe_active_workbook"})
    assert out["ok"] is True
    assert out["data"]["excel_running"] is True
    assert out["data"]["active_workbook"]["name"] == "test.xlsx"
    assert out["error"] is None
    # Verify handler called probe_active_workbook_readonly
    names = [c[0] for c in calls]
    assert "probe_active_workbook_readonly" in names


def test_probe_active_workbook_no_excel_running(monkeypatch):
    from agent import task_executor as te
    from agent import errors as _err

    calls = []

    class _Stub:
        def probe_active_workbook_readonly(self):
            calls.append("probe_active_workbook_readonly")
            return {
                "success": False,
                "excel_running": False,
                "error_code": _err.EXCEL_APP_NOT_FOUND,
                "workbook_count": None,
                "active_workbook": None,
                "sample_cells": [],
                "read_only": True,
            }

    monkeypatch.setattr(te, "com", _Stub())
    out = te.execute_task({"action": "excel.probe_active_workbook"})
    assert out["ok"] is False
    assert out["error"] == _err.EXCEL_APP_NOT_FOUND
    assert out["data"]["excel_running"] is False


def test_probe_active_workbook_no_file_path_required(stub_com):
    """excel.probe_active_workbook does not require file_path field."""
    from agent import task_executor as te
    stub, calls = stub_com
    # Should work without file_path
    out = te.execute_task({
        "action": "excel.probe_active_workbook",
        # no file_path
    })
    assert out["ok"] is True


# ──────────────────────────────────────────────────────────────────
# 핸들러 내부 예외도 결과 dict 으로 전환
# ──────────────────────────────────────────────────────────────────
def test_handler_crash_converted(monkeypatch):
    from agent import task_executor as te

    class _Stub:
        def open_excel_app(self, visible=True):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(te, "com", _Stub())
    out = te.execute_task({
        "action": "excel.read_cell",
        "file_path": r"C:\tmp\s.xlsx",
    })
    assert out["ok"] is False
    assert out["error"].startswith("handler_crashed:")
    assert "RuntimeError" in out["error"]


# ──────────────────────────────────────────────────────────────────
# hancom.convert_hwp_to_hwpx_copy
# ──────────────────────────────────────────────────────────────────
def test_hancom_convert_requires_input_path(monkeypatch):
    from agent import task_executor as te

    out = te.execute_task({
        "action": "hancom.convert_hwp_to_hwpx_copy",
        "output_path": r"C:\tmp\o.hwpx",
    })
    assert out["ok"] is False
    assert out["error"] == "INPUT_OUTPUT_PATH_REQUIRED"


def test_hancom_convert_requires_output_path(monkeypatch):
    from agent import task_executor as te

    out = te.execute_task({
        "action": "hancom.convert_hwp_to_hwpx_copy",
        "input_path": r"C:\tmp\i.hwp",
    })
    assert out["ok"] is False
    assert out["error"] == "INPUT_OUTPUT_PATH_REQUIRED"


def test_hancom_convert_delegates_to_workflows(monkeypatch):
    from agent import task_executor as te

    calls = []

    def mock_convert(params):
        calls.append(params)
        return {
            "success": True,
            "input_path": params.get("input_path"),
            "output_path": params.get("output_path"),
            "output_size": 1024,
            "hwpx_valid": True,
            "hwpx_file_count": 5,
            "hwpx_sections": 1,
            "error": None,
        }

    import agent.hancom.hwp.workflows as workflows_mod
    monkeypatch.setattr(workflows_mod, "convert_hwp_to_hwpx_copy", mock_convert)

    out = te.execute_task({
        "action": "hancom.convert_hwp_to_hwpx_copy",
        "input_path": r"C:\tmp\i.hwp",
        "output_path": r"C:\tmp\o.hwpx",
        "visible": False,
    })

    assert out["ok"] is True
    assert out["error"] is None
    assert out["data"]["hwpx_valid"] is True
    assert out["data"]["hwpx_file_count"] == 5
    assert out["data"]["hwpx_sections"] == 1
    assert len(calls) == 1
    assert calls[0]["input_path"] == r"C:\tmp\i.hwp"
    assert calls[0]["output_path"] == r"C:\tmp\o.hwpx"


def test_hancom_convert_file_path_alias(monkeypatch):
    """file_path와 input_path 모두 지원."""
    from agent import task_executor as te

    calls = []

    def mock_convert(params):
        calls.append(params)
        return {
            "success": True,
            "input_path": params.get("input_path"),
            "output_path": params.get("output_path"),
            "output_size": 512,
            "hwpx_valid": True,
            "hwpx_file_count": 3,
            "hwpx_sections": 1,
            "error": None,
        }

    import agent.hancom.hwp.workflows as workflows_mod
    monkeypatch.setattr(workflows_mod, "convert_hwp_to_hwpx_copy", mock_convert)

    # file_path 사용 (input_path 대신)
    out = te.execute_task({
        "action": "hancom.convert_hwp_to_hwpx_copy",
        "file_path": r"C:\tmp\test.hwp",
        "save_as": r"C:\tmp\out.hwpx",
    })

    assert out["ok"] is True
    assert calls[0]["input_path"] == r"C:\tmp\test.hwp"
    assert calls[0]["output_path"] == r"C:\tmp\out.hwpx"


def test_hancom_convert_error_propagated(monkeypatch):
    """워크플로우 에러가 올바르게 전파됨."""
    from agent import task_executor as te

    def mock_convert(params):
        return {
            "success": False,
            "input_path": params.get("input_path"),
            "output_path": None,
            "output_size": None,
            "hwpx_valid": False,
            "hwpx_file_count": 0,
            "hwpx_sections": 0,
            "error": "INPUT_FILE_NOT_FOUND",
        }

    import agent.hancom.hwp.workflows as workflows_mod
    monkeypatch.setattr(workflows_mod, "convert_hwp_to_hwpx_copy", mock_convert)

    out = te.execute_task({
        "action": "hancom.convert_hwp_to_hwpx_copy",
        "input_path": r"C:\nonexistent\file.hwp",
        "output_path": r"C:\tmp\out.hwpx",
    })

    assert out["ok"] is False
    assert out["error"] == "INPUT_FILE_NOT_FOUND"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
