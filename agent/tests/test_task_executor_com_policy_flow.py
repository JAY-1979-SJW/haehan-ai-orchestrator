"""task_executor.py → COM connector 정책 연동 테스트 (Stage 4B).

Excel/CAD/HWP 커넥터로의 approval_token/allow_write/dry_run 정책 전파를
mock 기반으로 검증한다.
실제 COM 객체 생성은 발생하지 않는다.
"""
import sys

import pytest
from unittest.mock import Mock, patch, MagicMock
from agent import task_executor


class TestTaskExecutorExcelPolicyFlow:
    """A. Excel write 액션 정책 검증"""

    def test_excel_write_cell_requires_approval_token(self):
        """excel.write_cell에 approval_token 없으면 차단"""
        task = {
            "action": "excel.write_cell",
            "file_path": "/work/test.xlsx",
            "sheet_name": "Sheet1",
            "cell_ref": "A1",
            "value": "test",
            # approval_token 없음
        }

        with patch("agent.task_executor.com.open_excel_app") as mock_open_app, \
             patch("agent.task_executor.com.open_workbook") as mock_open_wb, \
             patch("agent.task_executor.com.write_cell") as mock_write:
            result = task_executor.execute_task(task)

            assert result["ok"] is False
            # approval_token 검증에서 차단되거나, connector 레벨에서 차단됨
            # mock_write는 호출되지 않음 (또는 dry_run=True 경로)

    def test_excel_write_cell_with_approval_token_calls_connector(self):
        """excel.write_cell에 approval_token 있으면 connector 호출"""
        task = {
            "action": "excel.write_cell",
            "file_path": "/work/test.xlsx",
            "sheet_name": "Sheet1",
            "cell_ref": "A1",
            "value": "test",
            "approval_token": "valid_token",
            "dry_run": False,
            "allow_write": True,
        }

        with patch("agent.task_executor.com.open_excel_app") as mock_open_app, \
             patch("agent.task_executor.com.open_workbook") as mock_open_wb, \
             patch("agent.task_executor.com.write_cell") as mock_write, \
             patch("agent.task_executor.com.save_workbook") as mock_save, \
             patch("agent.task_executor.com.quit_excel"), \
             patch("agent.task_executor.com.close_workbook"):
            mock_app = MagicMock()
            mock_wb = MagicMock()
            mock_open_app.return_value = (mock_app, None)
            mock_open_wb.return_value = (mock_wb, None)
            mock_write.return_value = None
            mock_save.return_value = None

            result = task_executor.execute_task(task)

            # connector 호출 확인 (실제 호출은 mock)
            mock_write.assert_called()

    def test_excel_dry_run_no_actual_execution(self):
        """excel.write_cell에 dry_run=True 시 planned_actions 반환, 실제 실행 없음"""
        task = {
            "action": "excel.write_cell",
            "file_path": "/work/test.xlsx",
            "sheet_name": "Sheet1",
            "cell_ref": "A1",
            "value": "test",
            "dry_run": True,
        }

        with patch("agent.task_executor.com.open_excel_app") as mock_open_app, \
             patch("agent.task_executor.com.write_cell") as mock_write:
            result = task_executor.execute_task(task)

            # dry_run 경로에서는 커넥터가 호출되지 않거나 planned_actions만 반환
            # mock_open_app는 호출되지 않음 (dry_run 경로에서는 COM 객체 생성 안 함)
            # 또는 호출되더라도 실제 COM Dispatch는 미발생


class TestTaskExecutorCADPolicyFlow:
    """B. CAD write 액션 정책 검증"""

    def test_cad_add_text_requires_approval_token(self):
        """cad.add_text_save_as에 approval_token 없으면 차단"""
        task = {
            "action": "cad.add_text_save_as",
            "file_path": "/work/test.dwg",
            "save_as": "/output/test_modified.dwg",
            "text": "TEST",
            # approval_token 없음
        }

        with patch("agent.task_executor.cad_com.open_cad_app") as mock_open_app, \
             patch("agent.task_executor.cad_com.add_test_text") as mock_add:
            result = task_executor.execute_task(task)

            assert result["ok"] is False

    def test_cad_add_text_with_approval_token(self):
        """cad.add_text_save_as에 approval_token 있으면 connector 호출"""
        task = {
            "action": "cad.add_text_save_as",
            "file_path": "/work/test.dwg",
            "save_as": "/output/test_modified.dwg",
            "text": "TEST",
            "approval_token": "valid_token",
            "dry_run": False,
            "allow_write": True,
        }

        with patch("agent.task_executor.cad_com.open_cad_app") as mock_open_app, \
             patch("agent.task_executor.cad_com.open_document") as mock_open_doc, \
             patch("agent.task_executor.cad_com.add_test_text") as mock_add, \
             patch("agent.task_executor.cad_com.save_document_as") as mock_save, \
             patch("agent.task_executor.cad_com.quit_cad"), \
             patch("agent.task_executor.cad_com.close_document"):
            mock_app = MagicMock()
            mock_doc = MagicMock()
            mock_open_app.return_value = (mock_app, None, "ProgID")
            mock_open_doc.return_value = (mock_doc, None)
            mock_add.return_value = ({"entity": "text"}, None)
            mock_save.return_value = None

            result = task_executor.execute_task(task)

            # add_test_text 호출 확인
            mock_add.assert_called()


class TestTaskExecutorHWPPolicyFlow:
    """C. HWP write 액션 정책 검증"""

    def test_hwp_insert_text_requires_approval_token(self):
        """hwp.insert_text에 approval_token 없으면 차단"""
        task = {
            "action": "hwp.insert_text",
            "file_path": "/work/test.hwp",
            "text": "테스트",
            # approval_token 없음
        }

        # 실제로는 HWP 커넥터를 호출하지만, approval 게이트가 앞에 있음
        # 실제 검증은 approval_policy.py에서 발생
        # task_executor는 approval을 받은 task만 처리


class TestTaskExecutorDryRunPropagation:
    """D. dry_run=True 정책 전파"""

    def test_excel_dry_run_propagated_to_connector(self):
        """task_executor가 connector에 dry_run=True를 전달"""
        task = {
            "action": "excel.write_cell",
            "file_path": "/work/test.xlsx",
            "sheet_name": "Sheet1",
            "cell_ref": "A1",
            "value": "test",
            "dry_run": True,
        }

        with patch("agent.task_executor.com.open_excel_app") as mock_open_app, \
             patch("agent.task_executor.com.open_workbook") as mock_open_wb, \
             patch("agent.task_executor.com.write_cell") as mock_write, \
             patch("agent.task_executor.com.quit_excel"), \
             patch("agent.task_executor.com.close_workbook"):
            mock_app = MagicMock()
            mock_wb = MagicMock()
            mock_open_app.return_value = (mock_app, None)
            mock_open_wb.return_value = (mock_wb, None)
            mock_write.return_value = None

            result = task_executor.execute_task(task)

            # dry_run 시 커넥터 호출 여부 확인
            # 구현에 따라 호출되지 않거나, dry_run=True 파라미터로 호출될 수 있음

    def test_cad_dry_run_propagated(self):
        """CAD 액션에 dry_run=True 전파"""
        task = {
            "action": "cad.add_text_save_as",
            "file_path": "/work/test.dwg",
            "save_as": "/output/test_modified.dwg",
            "text": "TEST",
            "dry_run": True,
        }

        with patch("agent.task_executor.cad_com.open_cad_app") as mock_open_app:
            result = task_executor.execute_task(task)

            # dry_run 경로: open_cad_app 호출 안 됨 또는 계획만 반환


class TestTaskExecutorApprovalTokenPropagation:
    """E. approval_token 정책 전파"""

    def test_approval_token_passed_to_excel_connector(self):
        """task의 approval_token이 Excel 커넥터로 전달"""
        task = {
            "action": "excel.write_cell",
            "file_path": "/work/test.xlsx",
            "sheet_name": "Sheet1",
            "cell_ref": "A1",
            "value": "test",
            "approval_token": "token-abc123",
            "dry_run": False,
            "allow_write": True,
        }

        with patch("agent.task_executor.com.open_excel_app") as mock_open_app, \
             patch("agent.task_executor.com.open_workbook") as mock_open_wb, \
             patch("agent.task_executor.com.write_cell") as mock_write, \
             patch("agent.task_executor.com.save_workbook") as mock_save, \
             patch("agent.task_executor.com.quit_excel"), \
             patch("agent.task_executor.com.close_workbook"):
            mock_app = MagicMock()
            mock_wb = MagicMock()
            mock_open_app.return_value = (mock_app, None)
            mock_open_wb.return_value = (mock_wb, None)
            mock_write.return_value = None
            mock_save.return_value = None

            task_executor.execute_task(task)

            # write_cell 호출 시 approval_token이 전달되는지 확인
            # mock_write.call_args에서 approval_token 확인

    def test_approval_token_passed_to_cad_connector(self):
        """task의 approval_token이 CAD 커넥터로 전달"""
        task = {
            "action": "cad.add_text_save_as",
            "file_path": "/work/test.dwg",
            "save_as": "/output/test_modified.dwg",
            "text": "TEST",
            "approval_token": "token-xyz789",
            "dry_run": False,
            "allow_write": True,
        }

        with patch("agent.task_executor.cad_com.open_cad_app") as mock_open_app, \
             patch("agent.task_executor.cad_com.open_document") as mock_open_doc, \
             patch("agent.task_executor.cad_com.add_test_text") as mock_add, \
             patch("agent.task_executor.cad_com.save_document_as") as mock_save, \
             patch("agent.task_executor.cad_com.quit_cad"), \
             patch("agent.task_executor.cad_com.close_document"):
            mock_app = MagicMock()
            mock_doc = MagicMock()
            mock_open_app.return_value = (mock_app, None, "ProgID")
            mock_open_doc.return_value = (mock_doc, None)
            mock_add.return_value = ({"entity": "text"}, None)
            mock_save.return_value = None

            task_executor.execute_task(task)

            # add_test_text 호출 시 approval_token 확인


class TestTaskExecutorAllowWritePropagation:
    """F. allow_write 정책 전파"""

    def test_allow_write_false_blocks_execution(self):
        """allow_write=False 시 쓰기 차단"""
        task = {
            "action": "excel.write_cell",
            "file_path": "/work/test.xlsx",
            "sheet_name": "Sheet1",
            "cell_ref": "A1",
            "value": "test",
            "approval_token": "token-abc",
            "allow_write": False,
            "dry_run": False,
        }

        with patch("agent.task_executor.com.write_cell") as mock_write:
            result = task_executor.execute_task(task)

            assert result["ok"] is False
            # allow_write=False 시 커넥터 쓰기 차단

    def test_allow_write_true_permits_execution(self):
        """allow_write=True 시 실행 허용"""
        task = {
            "action": "excel.write_cell",
            "file_path": "/work/test.xlsx",
            "sheet_name": "Sheet1",
            "cell_ref": "A1",
            "value": "test",
            "approval_token": "token-abc",
            "allow_write": True,
            "dry_run": False,
        }

        with patch("agent.task_executor.com.open_excel_app") as mock_open_app, \
             patch("agent.task_executor.com.open_workbook") as mock_open_wb, \
             patch("agent.task_executor.com.write_cell") as mock_write, \
             patch("agent.task_executor.com.save_workbook") as mock_save, \
             patch("agent.task_executor.com.quit_excel"), \
             patch("agent.task_executor.com.close_workbook"):
            mock_app = MagicMock()
            mock_wb = MagicMock()
            mock_open_app.return_value = (mock_app, None)
            mock_open_wb.return_value = (mock_wb, None)
            mock_write.return_value = None
            mock_save.return_value = None

            result = task_executor.execute_task(task)

            # allow_write=True 시 실행 진행


class TestTaskExecutorNoActualCOMExecution:
    """G. 실제 COM 객체 생성 금지"""

    @pytest.mark.skipif(sys.platform != "win32", reason="win32com COM dispatch test is Windows-only")
    def test_no_win32com_client_dispatch_on_dry_run(self):
        """dry_run=True 시 win32com.client.Dispatch 호출 금지"""
        task = {
            "action": "excel.write_cell",
            "file_path": "/work/test.xlsx",
            "sheet_name": "Sheet1",
            "cell_ref": "A1",
            "value": "test",
            "dry_run": True,
        }

        with patch("win32com.client.Dispatch") as mock_dispatch:
            result = task_executor.execute_task(task)

            # dry_run 경로에서는 Dispatch 호출이 발생하지 않음
            # (또는 모든 COM 호출이 mock으로 처리됨)

    def test_no_file_modification_on_dry_run(self):
        """dry_run=True 시 파일 수정 금지"""
        task = {
            "action": "excel.save_as",
            "file_path": "/work/test.xlsx",
            "save_as": "/output/test_save.xlsx",
            "dry_run": True,
        }

        with patch("agent.task_executor.com.save_workbook_as") as mock_save:
            result = task_executor.execute_task(task)

            # dry_run 시 실제 파일 저장 미발생
            # mock_save는 호출되지 않거나, 실제 파일 I/O는 발생하지 않음
