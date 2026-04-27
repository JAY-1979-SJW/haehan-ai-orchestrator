"""hwp_com_connector — 단위 테스트 (mock 기반).

실제 한글/Windows COM 없이도 돌아야 하므로 모든 pywin32 / Dispatch /
Application 객체는 MagicMock 으로 대체한다.

검증:
1) 비 Windows → hwp_com_not_supported
2) pywin32 import 실패 → hwp_com_dispatch_failed
3) Dispatch 자체 실패 → hwp_app_not_found
4) open_document 경로 가드 (empty/relative/missing)
5) open_document COM 실패 → hwp_document_open_failed
6) get_text_preview 성공/실패
7) insert_text 기본 경로 / 폴백 / 실패
8) save_document_as 가드 및 성공 흐름 (overwrite 금지 기본)
9) register_file_path_check_module 성공/실패 분기
10) run_basic_poc mocked 성공 — Close/Quit 호출 확인
11) run_basic_poc save_as 흐름 — SaveAs 호출 확인
12) run_basic_poc 중간 실패 시 finally 정리 호출
13) 에러 코드가 errors.ALL_CODES 에 등록되어 있음
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


# ──────────────────────────────────────────────────────────────────
# 1) 비 Windows 환경 — not supported
# ──────────────────────────────────────────────────────────────────
def test_is_hwp_available_non_windows(monkeypatch):
    from agent.connectors import hwp_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: False)
    out = com.is_hwp_available()
    assert out["ok"] is False
    assert out["hwp_available"] is False
    assert out["error"] == com._err.HWP_COM_NOT_SUPPORTED


def test_open_hwp_app_non_windows(monkeypatch):
    from agent.connectors import hwp_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: False)
    app, err = com.open_hwp_app()
    assert app is None
    assert err == com._err.HWP_COM_NOT_SUPPORTED


# ──────────────────────────────────────────────────────────────────
# 2) pywin32 import 실패
# ──────────────────────────────────────────────────────────────────
def test_is_hwp_available_dispatch_import_failed(monkeypatch):
    from agent.connectors import hwp_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(
        com, "_try_import_win32com",
        lambda: (None, com._err.HWP_COM_DISPATCH_FAILED),
    )
    out = com.is_hwp_available()
    assert out["ok"] is False
    assert out["error"] == com._err.HWP_COM_DISPATCH_FAILED


# ──────────────────────────────────────────────────────────────────
# 3) Dispatch 자체가 실패 (HWP 미설치 등)
# ──────────────────────────────────────────────────────────────────
def test_is_hwp_available_dispatch_raises(monkeypatch):
    from agent.connectors import hwp_com_connector as com

    fake_mod = MagicMock()
    fake_mod.Dispatch.side_effect = RuntimeError("CoCreateInstance failed")

    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))
    out = com.is_hwp_available()
    assert out["ok"] is False
    assert out["error"] == com._err.HWP_APP_NOT_FOUND
    assert out["detail"] == "RuntimeError"


def test_open_hwp_app_dispatch_raises(monkeypatch):
    from agent.connectors import hwp_com_connector as com

    fake_mod = MagicMock()
    fake_mod.Dispatch.side_effect = OSError("COM unavailable")
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))
    app, err = com.open_hwp_app()
    assert app is None
    assert err == com._err.HWP_APP_NOT_FOUND


def test_open_hwp_app_success(monkeypatch):
    from agent.connectors import hwp_com_connector as com

    fake_app = MagicMock()
    fake_mod = MagicMock()
    fake_mod.Dispatch.return_value = fake_app
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))

    app, err = com.open_hwp_app(visible=False)
    assert err is None
    assert app is fake_app


def test_is_hwp_available_success(monkeypatch):
    from agent.connectors import hwp_com_connector as com

    fake_app = MagicMock()
    fake_app.Version = "11.0.0.1"
    fake_mod = MagicMock()
    fake_mod.Dispatch.return_value = fake_app
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))

    out = com.is_hwp_available()
    assert out["ok"] is True
    assert out["hwp_available"] is True
    assert out["platform"] == sys.platform or out["platform"] == "win32"
    assert out["version"] == "11.0.0.1"
    # RegisterModule 이 MagicMock 상 attr 로 존재 → True 로 기록
    assert out["security_module_registered"] is True
    fake_app.Quit.assert_called_once()


# ──────────────────────────────────────────────────────────────────
# 4) open_document 경로 가드
# ──────────────────────────────────────────────────────────────────
def test_open_document_empty_path():
    from agent.connectors import hwp_com_connector as com
    err = com.open_document(MagicMock(), "")
    assert err == com._err.FILE_PATH_REQUIRED


def test_open_document_relative_path():
    from agent.connectors import hwp_com_connector as com
    err = com.open_document(MagicMock(), "relative/path.hwp")
    assert err == com._err.FILE_NOT_ALLOWED


def test_open_document_missing_file(tmp_path):
    from agent.connectors import hwp_com_connector as com
    target = tmp_path / "nope.hwp"
    err = com.open_document(MagicMock(), str(target))
    assert err == com._err.FILE_NOT_FOUND


def test_open_document_com_failure(tmp_path):
    from agent.connectors import hwp_com_connector as com
    f = tmp_path / "x.hwp"
    f.write_bytes(b"dummy")
    app = MagicMock()
    app.Open.side_effect = RuntimeError("COM: file locked")
    err = com.open_document(app, str(f))
    assert err == com._err.HWP_DOCUMENT_OPEN_FAILED


def test_open_document_success(tmp_path):
    from agent.connectors import hwp_com_connector as com
    f = tmp_path / "x.hwp"
    f.write_bytes(b"dummy")
    app = MagicMock()
    err = com.open_document(app, str(f))
    assert err is None
    app.Open.assert_called_once()
    args, _ = app.Open.call_args
    assert args[0] == str(f)


# ──────────────────────────────────────────────────────────────────
# 5) 본문 읽기
# ──────────────────────────────────────────────────────────────────
def test_get_text_preview_success():
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    app.GetTextFile.return_value = "HELLO_HWP_BODY " * 40
    text, err = com.get_text_preview(app, max_chars=20)
    assert err is None
    assert text is not None
    assert len(text) == 20


def test_get_text_preview_raises():
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    app.GetTextFile.side_effect = RuntimeError("boom")
    text, err = com.get_text_preview(app)
    assert text is None
    assert err == com._err.HWP_TEXT_READ_FAILED


def test_get_text_preview_none_returned():
    """GetTextFile 이 None 을 반환해도 ok(빈 문자열) 로 처리."""
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    app.GetTextFile.return_value = None
    text, err = com.get_text_preview(app)
    assert err is None
    assert text == ""


# ──────────────────────────────────────────────────────────────────
# 6) 본문 쓰기
# ──────────────────────────────────────────────────────────────────
def test_insert_text_haction_path_success():
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    # HAction 기본 경로가 예외 없이 통과하도록 둔다 (MagicMock 기본 동작).
    err = com.insert_text(app, "POC_OK", dry_run=False, approval_token="DUMMY", allow_write=True)
    assert err is None
    app.HAction.GetDefault.assert_called_once()
    app.HAction.Execute.assert_called_once()
    assert app.HParameterSet.HInsertText.Text == "POC_OK"


def test_insert_text_haction_failure_falls_back():
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    app.HAction.GetDefault.side_effect = RuntimeError("bad HAction")
    err = com.insert_text(app, "HELLO", dry_run=False, approval_token="DUMMY", allow_write=True)
    assert err is None
    app.InsertText.assert_called_once_with("HELLO")


def test_insert_text_both_paths_fail():
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    app.HAction.GetDefault.side_effect = RuntimeError("bad HAction")
    app.InsertText.side_effect = RuntimeError("bad InsertText")
    err = com.insert_text(app, "HELLO", dry_run=False, approval_token="DUMMY", allow_write=True)
    assert err == com._err.HWP_TEXT_WRITE_FAILED


def test_insert_text_null_app():
    from agent.connectors import hwp_com_connector as com
    assert com.insert_text(None, "x") == com._err.HWP_APP_NOT_FOUND


# ──────────────────────────────────────────────────────────────────
# 7) 저장 / 종료
# ──────────────────────────────────────────────────────────────────
def test_save_document_as_requires_absolute():
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    assert com.save_document_as(app, "") == com._err.OUTPUT_PATH_REQUIRED
    assert (
        com.save_document_as(app, "rel/out.hwp")
        == com._err.OUTPUT_PATH_NOT_ALLOWED
    )


def test_save_document_as_overwrite_blocked(tmp_path):
    from agent.connectors import hwp_com_connector as com
    out = tmp_path / "exists.hwp"
    out.write_bytes(b"exists")
    app = MagicMock()
    assert com.save_document_as(app, str(out)) == com._err.OUTPUT_FILE_EXISTS
    app.SaveAs.assert_not_called()


def test_save_document_as_success(tmp_path):
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    out = tmp_path / "out.hwp"
    assert com.save_document_as(app, str(out), dry_run=False, approval_token="DUMMY", allow_write=True) is None
    app.SaveAs.assert_called_once()
    args, _ = app.SaveAs.call_args
    assert args[0] == str(out)
    assert args[1] == "HWP"


def test_save_document_as_hwpx_format(tmp_path):
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    out = tmp_path / "out.hwpx"
    assert com.save_document_as(app, str(out), dry_run=False, approval_token="DUMMY", allow_write=True) is None
    args, _ = app.SaveAs.call_args
    assert args[1] == "HWPX"


def test_save_document_as_com_failure(tmp_path):
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    app.SaveAs.side_effect = RuntimeError("disk full")
    out = tmp_path / "out.hwp"
    assert com.save_document_as(app, str(out), dry_run=False, approval_token="DUMMY", allow_write=True) == com._err.HWP_DOCUMENT_SAVE_FAILED


def test_close_and_quit_never_raise():
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    app.XHwpDocuments.Active_XHwpDocument.Close.side_effect = RuntimeError("boom")
    # 폴백이 있어도 예외가 밖으로 새지 않아야 한다.
    com.close_document(app)
    app2 = MagicMock()
    app2.Quit.side_effect = RuntimeError("boom")
    com.quit_hwp(app2)
    # None 입력도 안전.
    com.close_document(None)
    com.quit_hwp(None)


# ──────────────────────────────────────────────────────────────────
# 8) 보안 모듈 등록
# ──────────────────────────────────────────────────────────────────
def test_register_security_module_success():
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    app.RegisterModule.return_value = 1
    out = com.register_file_path_check_module(app, module_name="MyModule")
    assert out["ok"] is True
    assert out["module_name"] == "MyModule"
    app.RegisterModule.assert_called_once_with("FilePathCheckDLL", "MyModule")


def test_register_security_module_default_name():
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    out = com.register_file_path_check_module(app)
    assert out["ok"] is True
    assert out["module_name"] == com._DEFAULT_SECURITY_MODULE_NAME


def test_register_security_module_com_failure():
    from agent.connectors import hwp_com_connector as com
    app = MagicMock()
    app.RegisterModule.side_effect = RuntimeError("reg fail")
    out = com.register_file_path_check_module(app, module_name="X")
    assert out["ok"] is False
    assert out["error"] == com._err.HWP_SECURITY_MODULE_REQUIRED
    assert out["detail"] == "RuntimeError"


def test_register_security_module_null_app():
    from agent.connectors import hwp_com_connector as com
    out = com.register_file_path_check_module(None)
    assert out["ok"] is False
    assert out["error"] == com._err.HWP_APP_NOT_FOUND


def test_register_security_module_missing_method():
    from agent.connectors import hwp_com_connector as com

    class Dummy:
        pass

    out = com.register_file_path_check_module(Dummy())
    assert out["ok"] is False
    assert out["error"] == com._err.HWP_SECURITY_MODULE_REQUIRED


# ──────────────────────────────────────────────────────────────────
# 9) run_basic_poc
# ──────────────────────────────────────────────────────────────────
def _install_successful_mocks(monkeypatch, com, *, preview_text="DOC_BODY"):
    fake_app = MagicMock()
    fake_app.GetTextFile.return_value = preview_text

    monkeypatch.setattr(
        com, "is_hwp_available",
        lambda: {"ok": True, "platform": "win32",
                 "hwp_available": True, "version": "11.0",
                 "security_module_registered": True},
    )
    monkeypatch.setattr(
        com, "open_hwp_app", lambda visible=True: (fake_app, None)
    )
    return fake_app


def test_run_basic_poc_non_windows(monkeypatch, tmp_path):
    from agent.connectors import hwp_com_connector as com
    monkeypatch.setattr(
        com, "is_hwp_available",
        lambda: {"ok": False, "platform": "linux",
                 "hwp_available": False,
                 "error": com._err.HWP_COM_NOT_SUPPORTED},
    )
    out = com.run_basic_poc(str(tmp_path / "x.hwp"), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.HWP_COM_NOT_SUPPORTED
    assert out["dispatched"] is False
    assert out["quit"] is False


def test_run_basic_poc_success_flow(monkeypatch, tmp_path):
    from agent.connectors import hwp_com_connector as com

    f = tmp_path / "sample.hwp"
    f.write_bytes(b"dummy")
    fake_app = _install_successful_mocks(monkeypatch, com)

    out = com.run_basic_poc(str(f), save_as=None, write_text="POC_OK", dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is True
    assert out["dispatched"] is True
    assert out["document_opened"] is True
    assert out["text_preview"] == "DOC_BODY"
    assert out["written_text"] == "POC_OK"
    # save_as 미지정이면 저장 skip — 원본 overwrite 금지 보장
    assert out["saved"] is False
    assert out["closed"] is True
    assert out["quit"] is True
    assert out["error"] is None

    fake_app.Open.assert_called_once()
    fake_app.HAction.Execute.assert_called_once()
    fake_app.Quit.assert_called_once()


def test_run_basic_poc_save_as_flow(monkeypatch, tmp_path):
    from agent.connectors import hwp_com_connector as com

    f = tmp_path / "sample.hwp"
    f.write_bytes(b"dummy")
    fake_app = _install_successful_mocks(monkeypatch, com)

    out_path = tmp_path / "out.hwp"
    out = com.run_basic_poc(str(f), save_as=str(out_path), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is True
    assert out["saved"] is True
    fake_app.SaveAs.assert_called_once()


def test_run_basic_poc_with_register_module(monkeypatch, tmp_path):
    from agent.connectors import hwp_com_connector as com

    f = tmp_path / "sample.hwp"
    f.write_bytes(b"dummy")
    fake_app = _install_successful_mocks(monkeypatch, com)
    fake_app.RegisterModule.return_value = 1

    out = com.run_basic_poc(
        str(f), register_module=True, module_name="FilePathCheckerModule",
        dry_run=False, approval_token="DUMMY", allow_write=True,
    )
    assert out["ok"] is True
    assert out["security_module"] is not None
    assert out["security_module"]["ok"] is True
    assert out["security_module"]["module_name"] == "FilePathCheckerModule"
    fake_app.RegisterModule.assert_called_once_with(
        "FilePathCheckDLL", "FilePathCheckerModule",
    )


def test_run_basic_poc_cleanup_on_failure(monkeypatch, tmp_path):
    """중간 단계가 실패해도 Close / Quit 가 호출되어야 한다."""
    from agent.connectors import hwp_com_connector as com

    f = tmp_path / "sample.hwp"
    f.write_bytes(b"dummy")
    fake_app = _install_successful_mocks(monkeypatch, com)
    # GetTextFile 이 실패하도록 — 읽기 단계에서 에러 반환.
    fake_app.GetTextFile.side_effect = RuntimeError("boom")

    out = com.run_basic_poc(str(f), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.HWP_TEXT_READ_FAILED
    # 정리 동작은 여전히 실행됨
    assert out["closed"] is True
    assert out["quit"] is True
    fake_app.Quit.assert_called_once()


def test_run_basic_poc_open_failure(monkeypatch, tmp_path):
    from agent.connectors import hwp_com_connector as com

    f = tmp_path / "sample.hwp"
    f.write_bytes(b"dummy")
    fake_app = _install_successful_mocks(monkeypatch, com)
    fake_app.Open.side_effect = RuntimeError("locked")

    out = com.run_basic_poc(str(f), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.HWP_DOCUMENT_OPEN_FAILED
    assert out["document_opened"] is False
    assert out["closed"] is True
    assert out["quit"] is True


# ──────────────────────────────────────────────────────────────────
# P0 안전장치: dry_run / 승인 게이트 회귀 테스트
# ──────────────────────────────────────────────────────────────────
def test_run_basic_poc_dry_run_default_true(monkeypatch, tmp_path):
    """기본 dry_run=True 검증. COM 객체 생성 안 됨."""
    from agent.connectors import hwp_com_connector as com
    f = tmp_path / "sample.hwp"
    f.write_bytes(b"dummy")
    out = com.run_basic_poc(str(f))
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert out["dispatched"] is False  # Dispatch 안 됨
    assert "planned_actions" in out
    assert len(out["planned_actions"]) > 0
    assert all("action" in a for a in out["planned_actions"])


def test_insert_text_dry_run_default_true(monkeypatch, tmp_path):
    """insert_text 기본 dry_run=True. COM 호출 안 됨."""
    from agent.connectors import hwp_com_connector as com
    fake_app = _install_successful_mocks(monkeypatch, com)
    result = com.insert_text(fake_app, "TEST")
    # 기본 dry_run=True이므로 None 반환 (계획 모드)
    assert result is None


def test_insert_text_blocked_without_approval_token(monkeypatch, tmp_path):
    """approval_token=None, allow_write=True, dry_run=False 일 때 WRITE_APPROVAL_REQUIRED."""
    from agent.connectors import hwp_com_connector as com
    fake_app = _install_successful_mocks(monkeypatch, com)
    err = com.insert_text(
        fake_app, "TEST",
        approval_token=None,
        allow_write=True,
        dry_run=False,
    )
    assert err == com._err.WRITE_APPROVAL_REQUIRED


def test_save_document_as_blocked_without_approval_token(monkeypatch, tmp_path):
    """save_document_as approval_token 없으면 차단."""
    from agent.connectors import hwp_com_connector as com
    fake_app = _install_successful_mocks(monkeypatch, com)
    output_path = str(tmp_path / "output.hwp")
    err = com.save_document_as(
        fake_app, output_path,
        approval_token=None,
        allow_write=True,
        dry_run=False,
    )
    assert err == com._err.WRITE_APPROVAL_REQUIRED


def test_insert_text_blocked_allow_write_false(monkeypatch, tmp_path):
    """allow_write=False 일 때 WRITE_NOT_ALLOWED."""
    from agent.connectors import hwp_com_connector as com
    fake_app = _install_successful_mocks(monkeypatch, com)
    err = com.insert_text(
        fake_app, "TEST",
        approval_token="token",
        allow_write=False,
        dry_run=False,
    )
    assert err == com._err.WRITE_NOT_ALLOWED


def test_insert_text_approval_token_not_exposed(monkeypatch, tmp_path, caplog):
    """approval_token 이 로그에 노출되지 않음."""
    import logging
    from agent.connectors import hwp_com_connector as com
    fake_app = _install_successful_mocks(monkeypatch, com)
    caplog.set_level(logging.WARNING)
    secret_token = "super_secret_token_12345"
    err = com.insert_text(
        fake_app, "TEST",
        approval_token=secret_token,
        allow_write=False,
        dry_run=False,
    )
    assert err == com._err.WRITE_NOT_ALLOWED
    for record in caplog.records:
        assert secret_token not in record.message


def test_run_basic_poc_planned_actions(monkeypatch, tmp_path):
    """run_basic_poc dry_run=True 시 planned_actions 구조 검증."""
    from agent.connectors import hwp_com_connector as com
    f = tmp_path / "sample.hwp"
    f.write_bytes(b"dummy")
    out = com.run_basic_poc(str(f), dry_run=True)
    assert out["ok"] is True
    planned = out.get("planned_actions", [])
    assert isinstance(planned, list)
    assert len(planned) >= 3  # open, read, insert, save
    assert planned[0]["action"] == "hwp.open"
    assert planned[1]["action"] == "hwp.get_text_preview"
    assert planned[2]["action"] == "hwp.insert_text"
    # token/secret 이 노출되지 않아야 함
    for action_dict in planned:
        assert "action" in action_dict
        assert isinstance(action_dict["action"], str)
        for key, val in action_dict.items():
            if isinstance(val, str):
                assert "token" not in val.lower()
                assert "secret" not in val.lower()


# ──────────────────────────────────────────────────────────────────
# 10) 에러 코드 등록 확인
# ──────────────────────────────────────────────────────────────────
def test_hwp_error_codes_registered():
    from agent import errors
    for name in (
        "HWP_COM_NOT_SUPPORTED",
        "HWP_COM_DISPATCH_FAILED",
        "HWP_APP_NOT_FOUND",
        "HWP_SECURITY_MODULE_REQUIRED",
        "HWP_DOCUMENT_OPEN_FAILED",
        "HWP_TEXT_READ_FAILED",
        "HWP_TEXT_WRITE_FAILED",
        "HWP_DOCUMENT_SAVE_FAILED",
    ):
        assert hasattr(errors, name), f"errors.{name} missing"
        assert getattr(errors, name) in errors.ALL_CODES, name
        assert errors.is_standard_code(getattr(errors, name))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
