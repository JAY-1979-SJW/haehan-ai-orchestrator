"""cad_com_connector — 단위 테스트 (mock 기반).

실제 AutoCAD / Windows COM 없이 돌아야 하므로 모든 pywin32 / Dispatch /
Application 객체는 MagicMock 으로 대체한다.

검증:
1) 비 Windows → cad_com_not_supported
2) pywin32 import 실패 → cad_com_dispatch_failed
3) Dispatch 자체 실패 → cad_app_not_found
4) ProgID 폴백 동작 (버전 ProgID 실패 → unversioned 성공)
5) open_document 경로 가드 (empty / relative / missing) + COM 실패 분기
6) get_document_info 성공 / 실패
7) add_test_text 성공 / 실패 / 음수 높이 가드
8) save_document / save_document_as overwrite 금지 / COM 실패
9) close/quit 예외 삼킴 / None 안전
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
def test_is_cad_available_non_windows(monkeypatch):
    from agent.connectors import cad_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: False)
    out = com.is_cad_available()
    assert out["ok"] is False
    assert out["cad_available"] is False
    assert out["error"] == com._err.CAD_COM_NOT_SUPPORTED


def test_open_cad_app_non_windows(monkeypatch):
    from agent.connectors import cad_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: False)
    app, err, progid = com.open_cad_app()
    assert app is None
    assert err == com._err.CAD_COM_NOT_SUPPORTED
    assert progid is None


# ──────────────────────────────────────────────────────────────────
# 2) pywin32 import 실패
# ──────────────────────────────────────────────────────────────────
def test_is_cad_available_dispatch_import_failed(monkeypatch):
    from agent.connectors import cad_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(
        com, "_try_import_win32com",
        lambda: (None, com._err.CAD_COM_DISPATCH_FAILED),
    )
    out = com.is_cad_available()
    assert out["ok"] is False
    assert out["error"] == com._err.CAD_COM_DISPATCH_FAILED


# ──────────────────────────────────────────────────────────────────
# 3) Dispatch 자체가 실패 (AutoCAD 미설치 등) — 모든 progid 실패
# ──────────────────────────────────────────────────────────────────
def test_is_cad_available_dispatch_raises(monkeypatch):
    from agent.connectors import cad_com_connector as com

    fake_mod = MagicMock()
    fake_mod.Dispatch.side_effect = RuntimeError("CoCreateInstance failed")
    # early-binding 경로도 동일하게 실패하도록
    fake_mod.gencache.EnsureDispatch.side_effect = RuntimeError("no typelib")

    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))
    out = com.is_cad_available()
    assert out["ok"] is False
    assert out["error"] == com._err.CAD_APP_NOT_FOUND


def test_open_cad_app_dispatch_raises(monkeypatch):
    from agent.connectors import cad_com_connector as com

    fake_mod = MagicMock()
    fake_mod.Dispatch.side_effect = OSError("COM unavailable")
    fake_mod.gencache.EnsureDispatch.side_effect = OSError("no typelib")
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))
    app, err, progid = com.open_cad_app()
    assert app is None
    assert err == com._err.CAD_APP_NOT_FOUND
    assert progid is None


# ──────────────────────────────────────────────────────────────────
# 4) ProgID 폴백 — 버전 ProgID 실패 → unversioned 성공
# ──────────────────────────────────────────────────────────────────
def test_dispatch_autocad_falls_back_to_unversioned(monkeypatch):
    from agent.connectors import cad_com_connector as com

    fake_app = MagicMock()
    fake_mod = MagicMock()

    # gencache 경로는 모두 실패하도록 강제 → Dispatch 폴백만 테스트
    fake_mod.gencache.EnsureDispatch.side_effect = RuntimeError("no typelib")

    def side(progid):
        if progid == "AutoCAD.Application":
            return fake_app
        raise RuntimeError(f"no {progid}")

    fake_mod.Dispatch.side_effect = side
    app, progid, err = com._dispatch_autocad(fake_mod)
    assert err is None
    assert app is fake_app
    assert progid == "AutoCAD.Application"
    # 버전 progid 들을 먼저 시도했어야 한다
    assert fake_mod.Dispatch.call_count >= 2


def test_dispatch_autocad_prefers_ensuredispatch(monkeypatch):
    """gencache.EnsureDispatch 가 성공하면 plain Dispatch 는 호출되지 않는다."""
    from agent.connectors import cad_com_connector as com

    fake_app = MagicMock()
    fake_mod = MagicMock()
    fake_mod.gencache.EnsureDispatch.return_value = fake_app
    app, progid, err = com._dispatch_autocad(fake_mod)
    assert err is None
    assert app is fake_app
    # 첫 후보 progid 에서 바로 성공
    assert progid == com._CAD_PROGID_CANDIDATES[0]
    fake_mod.Dispatch.assert_not_called()


def test_is_cad_available_success(monkeypatch):
    from agent.connectors import cad_com_connector as com

    fake_app = MagicMock()
    fake_app.Version = "24.3"
    fake_app.ProductName = "AutoCAD"
    fake_mod = MagicMock()
    # early-binding 경로가 먼저 시도된다
    fake_mod.gencache.EnsureDispatch.return_value = fake_app
    fake_mod.Dispatch.return_value = fake_app
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))

    out = com.is_cad_available()
    assert out["ok"] is True
    assert out["cad_available"] is True
    assert out["prog_id"] == com._CAD_PROGID_CANDIDATES[0]
    assert out["version"] == "24.3"
    assert out["product_name"] == "AutoCAD"
    assert out["lt_or_limited"] is False
    fake_app.Quit.assert_called_once()


def test_is_cad_available_detects_lt():
    from agent.connectors import cad_com_connector as com
    # 케이스별 LT 감지
    assert com._detect_lt_or_limited("AutoCAD LT 2024") is True
    assert com._detect_lt_or_limited("AutoCAD") is False
    assert com._detect_lt_or_limited("") is False
    assert com._detect_lt_or_limited(None) is False  # type: ignore[arg-type]


def test_open_cad_app_success(monkeypatch):
    from agent.connectors import cad_com_connector as com
    fake_app = MagicMock()
    fake_mod = MagicMock()
    fake_mod.gencache.EnsureDispatch.return_value = fake_app
    fake_mod.Dispatch.return_value = fake_app
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (fake_mod, None))
    app, err, progid = com.open_cad_app(visible=False)
    assert err is None
    assert app is fake_app
    assert progid == com._CAD_PROGID_CANDIDATES[0]
    # Visible 설정이 호출됐는지
    assert fake_app.Visible is False


# ──────────────────────────────────────────────────────────────────
# 5) open_document 경로 가드
# ──────────────────────────────────────────────────────────────────
def test_open_document_null_app():
    from agent.connectors import cad_com_connector as com
    doc, err = com.open_document(None, "C:\\abs\\path.dwg")
    assert doc is None
    assert err == com._err.CAD_APP_NOT_FOUND


def test_open_document_empty_path():
    from agent.connectors import cad_com_connector as com
    doc, err = com.open_document(MagicMock(), "")
    assert doc is None
    assert err == com._err.FILE_PATH_REQUIRED


def test_open_document_relative_path():
    from agent.connectors import cad_com_connector as com
    doc, err = com.open_document(MagicMock(), "relative/path.dwg")
    assert doc is None
    assert err == com._err.FILE_NOT_ALLOWED


def test_open_document_missing_file(tmp_path):
    from agent.connectors import cad_com_connector as com
    target = tmp_path / "nope.dwg"
    doc, err = com.open_document(MagicMock(), str(target))
    assert doc is None
    assert err == com._err.FILE_NOT_FOUND


def test_open_document_com_failure(tmp_path):
    from agent.connectors import cad_com_connector as com
    f = tmp_path / "x.dwg"
    f.write_bytes(b"dummy")
    app = MagicMock()
    app.Documents.Open.side_effect = RuntimeError("COM: file locked")
    doc, err = com.open_document(app, str(f))
    assert doc is None
    assert err == com._err.CAD_DOCUMENT_OPEN_FAILED


def test_open_document_returns_none(tmp_path):
    from agent.connectors import cad_com_connector as com
    f = tmp_path / "x.dwg"
    f.write_bytes(b"dummy")
    app = MagicMock()
    app.Documents.Open.return_value = None
    doc, err = com.open_document(app, str(f))
    assert doc is None
    assert err == com._err.CAD_DOCUMENT_OPEN_FAILED


def test_open_document_success(tmp_path):
    from agent.connectors import cad_com_connector as com
    f = tmp_path / "x.dwg"
    f.write_bytes(b"dummy")
    app = MagicMock()
    fake_doc = MagicMock()
    app.Documents.Open.return_value = fake_doc
    doc, err = com.open_document(app, str(f))
    assert err is None
    assert doc is fake_doc
    args, _ = app.Documents.Open.call_args
    assert args[0] == str(f)


# ──────────────────────────────────────────────────────────────────
# 6) get_document_info
# ──────────────────────────────────────────────────────────────────
def test_get_document_info_success():
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    doc.Name = "sample.dwg"
    doc.FullName = "C:\\tmp\\sample.dwg"
    doc.ModelSpace.Count = 12
    doc.ActiveLayout.Name = "Model"
    info, err = com.get_document_info(doc)
    assert err is None
    assert info == {
        "name": "sample.dwg",
        "full_name": "C:\\tmp\\sample.dwg",
        "model_space_count": 12,
        "active_layout": "Model",
    }


def test_get_document_info_null_doc():
    from agent.connectors import cad_com_connector as com
    info, err = com.get_document_info(None)
    assert info is None
    assert err == com._err.CAD_DOCUMENT_INFO_FAILED


def test_get_document_info_raises():
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    # ModelSpace 접근 자체가 예외
    type(doc).ModelSpace = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    info, err = com.get_document_info(doc)
    assert info is None
    assert err == com._err.CAD_DOCUMENT_INFO_FAILED


# ──────────────────────────────────────────────────────────────────
# 7) add_test_text
# ──────────────────────────────────────────────────────────────────
def test_add_test_text_success(monkeypatch):
    from agent.connectors import cad_com_connector as com
    # 실제 구현은 pythoncom VT_ARRAY|VT_R8 VARIANT 로 래핑하지만, 테스트에서는
    # MagicMock 상 비교를 위해 평문 tuple 을 쓰도록 고정.
    monkeypatch.setattr(
        com, "_autocad_point",
        lambda x, y, z: (float(x), float(y), float(z)),
    )
    doc = MagicMock()
    fake_ent = MagicMock()
    fake_ent.Handle = "2A7"
    fake_ent.ObjectName = "AcDbText"
    doc.ModelSpace.AddText.return_value = fake_ent

    info, err = com.add_test_text(doc, "POC_OK", 1.0, 2.0, 3.0, height=2.5, dry_run=False, approval_token="DUMMY", allow_write=True)
    assert err is None
    assert info is not None
    assert info["type"] == "Text"
    assert info["text"] == "POC_OK"
    assert info["handle"] == "2A7"
    assert info["object_name"] == "AcDbText"

    args, _ = doc.ModelSpace.AddText.call_args
    assert args[0] == "POC_OK"
    assert args[1] == (1.0, 2.0, 3.0)
    assert args[2] == 2.5


def test_add_test_text_null_doc():
    from agent.connectors import cad_com_connector as com
    info, err = com.add_test_text(None)
    assert info is None
    assert err == com._err.CAD_ENTITY_ADD_FAILED


def test_add_test_text_invalid_height():
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    info, err = com.add_test_text(doc, "X", height=0)
    assert info is None
    assert err == com._err.CAD_ENTITY_ADD_FAILED
    doc.ModelSpace.AddText.assert_not_called()


def test_add_test_text_invalid_coordinate():
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    info, err = com.add_test_text(doc, "X", x="bad")  # type: ignore[arg-type]
    assert info is None
    assert err == com._err.CAD_ENTITY_ADD_FAILED


def test_add_test_text_com_failure():
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    doc.ModelSpace.AddText.side_effect = RuntimeError("AddText failed")
    info, err = com.add_test_text(doc, "POC_OK", dry_run=False, approval_token="DUMMY", allow_write=True)
    assert info is None
    assert err == com._err.CAD_ENTITY_ADD_FAILED


# ──────────────────────────────────────────────────────────────────
# 8) save_document / save_document_as
# ──────────────────────────────────────────────────────────────────
def test_save_document_success():
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    assert com.save_document(doc) is None
    doc.Save.assert_called_once()


def test_save_document_null():
    from agent.connectors import cad_com_connector as com
    assert com.save_document(None) == com._err.CAD_DOCUMENT_SAVE_FAILED


def test_save_document_com_failure():
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    doc.Save.side_effect = RuntimeError("disk full")
    assert com.save_document(doc) == com._err.CAD_DOCUMENT_SAVE_FAILED


def test_save_document_as_requires_absolute():
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    assert com.save_document_as(doc, "") == com._err.OUTPUT_PATH_REQUIRED
    assert (
        com.save_document_as(doc, "rel/out.dwg")
        == com._err.OUTPUT_PATH_NOT_ALLOWED
    )


def test_save_document_as_overwrite_blocked(tmp_path):
    from agent.connectors import cad_com_connector as com
    out = tmp_path / "exists.dwg"
    out.write_bytes(b"exists")
    doc = MagicMock()
    assert com.save_document_as(doc, str(out)) == com._err.OUTPUT_FILE_EXISTS
    doc.SaveAs.assert_not_called()


def test_save_document_as_success(tmp_path):
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    out = tmp_path / "out.dwg"
    assert com.save_document_as(doc, str(out), dry_run=False, approval_token="DUMMY", allow_write=True) is None
    doc.SaveAs.assert_called_once()
    args, _ = doc.SaveAs.call_args
    assert args[0] == str(out)


def test_save_document_as_com_failure(tmp_path):
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    doc.SaveAs.side_effect = RuntimeError("disk full")
    out = tmp_path / "out.dwg"
    assert com.save_document_as(doc, str(out), dry_run=False, approval_token="DUMMY", allow_write=True) == com._err.CAD_DOCUMENT_SAVE_FAILED


def test_save_document_as_null_doc(tmp_path):
    from agent.connectors import cad_com_connector as com
    out = tmp_path / "out.dwg"
    assert com.save_document_as(None, str(out)) == com._err.CAD_DOCUMENT_SAVE_FAILED


# ──────────────────────────────────────────────────────────────────
# 9) close/quit 정리 경로 — 예외 삼킴 / None 안전
# ──────────────────────────────────────────────────────────────────
def test_close_and_quit_never_raise():
    from agent.connectors import cad_com_connector as com
    doc = MagicMock()
    doc.Close.side_effect = RuntimeError("boom")
    com.close_document(doc)
    app = MagicMock()
    app.Quit.side_effect = RuntimeError("boom")
    com.quit_cad(app)
    # None 입력도 안전.
    com.close_document(None)
    com.quit_cad(None)


# ──────────────────────────────────────────────────────────────────
# 10) run_basic_poc
# ──────────────────────────────────────────────────────────────────
def _install_successful_mocks(monkeypatch, com, *, model_space_count=5):
    fake_doc = MagicMock()
    fake_doc.Name = "sample.dwg"
    fake_doc.FullName = "C:\\tmp\\cad_poc\\sample.dwg"
    fake_doc.ModelSpace.Count = model_space_count
    fake_doc.ActiveLayout.Name = "Model"
    # AddText 는 핸들·이름 붙은 엔터티를 반환
    fake_ent = MagicMock()
    fake_ent.Handle = "2A7"
    fake_ent.ObjectName = "AcDbText"
    fake_doc.ModelSpace.AddText.return_value = fake_ent

    fake_app = MagicMock()
    fake_app.Documents.Open.return_value = fake_doc

    # run_basic_poc 는 이제 _is_windows / _try_import_win32com 만 사전 점검하고
    # Dispatch 는 open_cad_app 한 곳에서만 수행한다.
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (MagicMock(), None))
    # extract_app_info 로 availability 를 뽑아낼 수 있게 Version/ProductName 준비
    fake_app.Version = "24.3"
    fake_app.ProductName = "AutoCAD"
    monkeypatch.setattr(
        com, "open_cad_app",
        lambda visible=True: (fake_app, None, "AutoCAD.Application.24.3"),
    )
    # VARIANT 래핑은 테스트 비교를 위해 평문 tuple 로 고정
    monkeypatch.setattr(
        com, "_autocad_point",
        lambda x, y, z: (float(x), float(y), float(z)),
    )
    return fake_app, fake_doc


def test_run_basic_poc_non_windows(monkeypatch, tmp_path):
    from agent.connectors import cad_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: False)
    out = com.run_basic_poc(str(tmp_path / "x.dwg"), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.CAD_COM_NOT_SUPPORTED
    assert out["dispatched"] is False
    assert out["quit"] is False


def test_run_basic_poc_import_failure(monkeypatch, tmp_path):
    from agent.connectors import cad_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(
        com, "_try_import_win32com",
        lambda: (None, com._err.CAD_COM_DISPATCH_FAILED),
    )
    out = com.run_basic_poc(str(tmp_path / "x.dwg"), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.CAD_COM_DISPATCH_FAILED
    assert out["dispatched"] is False
    assert out["quit"] is False


def test_run_basic_poc_app_failure(monkeypatch, tmp_path):
    from agent.connectors import cad_com_connector as com
    monkeypatch.setattr(com, "_is_windows", lambda: True)
    monkeypatch.setattr(com, "_try_import_win32com", lambda: (MagicMock(), None))
    monkeypatch.setattr(
        com, "open_cad_app",
        lambda visible=True: (None, com._err.CAD_APP_NOT_FOUND, None),
    )
    out = com.run_basic_poc(str(tmp_path / "x.dwg"), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.CAD_APP_NOT_FOUND
    assert out["dispatched"] is False


def test_run_basic_poc_success_flow(monkeypatch, tmp_path):
    from agent.connectors import cad_com_connector as com

    f = tmp_path / "sample.dwg"
    f.write_bytes(b"dummy")
    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)

    out = com.run_basic_poc(str(f), save_as=None, text="POC_OK", dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is True
    assert out["dispatched"] is True
    assert out["prog_id"] == "AutoCAD.Application.24.3"
    assert out["version"] == "24.3"
    assert out["product_name"] == "AutoCAD"
    assert out["lt_or_limited"] is False
    assert out["document_opened"] is True
    assert out["document_info"] is not None
    assert out["document_info"]["name"] == "sample.dwg"
    assert out["document_info"]["model_space_count"] == 5
    assert out["document_info"]["active_layout"] == "Model"
    assert out["added_entity"] is not None
    assert out["added_entity"]["type"] == "Text"
    assert out["added_entity"]["text"] == "POC_OK"
    # save_as 미지정이면 저장 skip — 원본 overwrite 금지 보장
    assert out["saved"] is False
    assert out["closed"] is True
    assert out["quit"] is True
    assert out["error"] is None

    fake_app.Documents.Open.assert_called_once()
    fake_doc.ModelSpace.AddText.assert_called_once()
    fake_doc.Close.assert_called_once()
    fake_app.Quit.assert_called_once()


def test_run_basic_poc_save_as_flow(monkeypatch, tmp_path):
    from agent.connectors import cad_com_connector as com

    f = tmp_path / "sample.dwg"
    f.write_bytes(b"dummy")
    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)

    out_path = tmp_path / "out.dwg"
    out = com.run_basic_poc(str(f), save_as=str(out_path), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is True
    assert out["saved"] is True
    fake_doc.SaveAs.assert_called_once()
    args, _ = fake_doc.SaveAs.call_args
    assert args[0] == str(out_path)


def test_run_basic_poc_save_as_overwrite_blocked(monkeypatch, tmp_path):
    from agent.connectors import cad_com_connector as com

    f = tmp_path / "sample.dwg"
    f.write_bytes(b"dummy")
    out_path = tmp_path / "out.dwg"
    out_path.write_bytes(b"existing")

    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)
    out = com.run_basic_poc(str(f), save_as=str(out_path), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.OUTPUT_FILE_EXISTS
    assert out["saved"] is False
    # 정리는 여전히 수행
    assert out["closed"] is True
    assert out["quit"] is True


def test_run_basic_poc_cleanup_on_open_failure(monkeypatch, tmp_path):
    """문서 열기 실패여도 Quit 은 호출되어야 한다 (doc 는 None 이라 Close 는 skip)."""
    from agent.connectors import cad_com_connector as com

    f = tmp_path / "sample.dwg"
    f.write_bytes(b"dummy")
    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)
    fake_app.Documents.Open.side_effect = RuntimeError("locked")

    out = com.run_basic_poc(str(f), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.CAD_DOCUMENT_OPEN_FAILED
    assert out["document_opened"] is False
    # doc 은 열리지 않았으므로 closed 는 False, quit 은 True
    assert out["closed"] is False
    assert out["quit"] is True
    fake_app.Quit.assert_called_once()


def test_run_basic_poc_cleanup_on_info_failure(monkeypatch, tmp_path):
    """중간 단계(정보 읽기) 실패에도 Close / Quit 호출."""
    from agent.connectors import cad_com_connector as com

    f = tmp_path / "sample.dwg"
    f.write_bytes(b"dummy")
    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)
    # ModelSpace 접근에서 예외 → get_document_info 실패
    type(fake_doc).ModelSpace = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    out = com.run_basic_poc(str(f), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.CAD_DOCUMENT_INFO_FAILED
    assert out["closed"] is True
    assert out["quit"] is True
    fake_app.Quit.assert_called_once()


def test_run_basic_poc_entity_add_failure(monkeypatch, tmp_path):
    from agent.connectors import cad_com_connector as com

    f = tmp_path / "sample.dwg"
    f.write_bytes(b"dummy")
    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)
    fake_doc.ModelSpace.AddText.side_effect = RuntimeError("not allowed")

    out = com.run_basic_poc(str(f), dry_run=False, approval_token="DUMMY", allow_write=True)
    assert out["ok"] is False
    assert out["error"] == com._err.CAD_ENTITY_ADD_FAILED
    assert out["added_entity"] is None
    assert out["closed"] is True
    assert out["quit"] is True


# ──────────────────────────────────────────────────────────────────
# P0 안전장치: dry_run / 승인 게이트 회귀 테스트
# ──────────────────────────────────────────────────────────────────
def test_run_basic_poc_dry_run_default_true(monkeypatch, tmp_path):
    """기본 dry_run=True 검증. COM 객체 생성 안 됨."""
    from agent.connectors import cad_com_connector as com
    f = tmp_path / "sample.dwg"
    f.write_bytes(b"dummy")
    out = com.run_basic_poc(str(f))
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert out["dispatched"] is False  # Dispatch 안 됨
    assert "planned_actions" in out
    assert len(out["planned_actions"]) > 0
    assert all("action" in a for a in out["planned_actions"])


def test_add_test_text_dry_run_default_true(monkeypatch, tmp_path):
    """add_test_text 기본 dry_run=True. COM 호출 안 됨."""
    from agent.connectors import cad_com_connector as com
    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)
    ent_info, err = com.add_test_text(fake_doc, text="TEST")
    # 기본 dry_run=True이므로 계획 정보와 None 반환
    assert err is None
    assert ent_info is not None
    assert ent_info.get("type") == "Text"
    fake_doc.ModelSpace.AddText.assert_not_called()


def test_add_test_text_blocked_without_approval_token(monkeypatch, tmp_path):
    """approval_token=None, allow_write=True, dry_run=False 일 때 WRITE_APPROVAL_REQUIRED."""
    from agent.connectors import cad_com_connector as com
    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)
    ent_info, err = com.add_test_text(
        fake_doc, text="TEST",
        approval_token=None,
        allow_write=True,
        dry_run=False,
    )
    assert err == com._err.WRITE_APPROVAL_REQUIRED
    assert ent_info is None
    fake_doc.ModelSpace.AddText.assert_not_called()


def test_save_document_as_blocked_without_approval_token(monkeypatch, tmp_path):
    """save_document_as approval_token 없으면 차단."""
    from agent.connectors import cad_com_connector as com
    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)
    output_path = str(tmp_path / "output.dwg")
    err = com.save_document_as(
        fake_doc, output_path,
        approval_token=None,
        allow_write=True,
        dry_run=False,
    )
    assert err == com._err.WRITE_APPROVAL_REQUIRED
    fake_doc.SaveAs.assert_not_called()


def test_add_test_text_blocked_allow_write_false(monkeypatch, tmp_path):
    """allow_write=False 일 때 WRITE_NOT_ALLOWED."""
    from agent.connectors import cad_com_connector as com
    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)
    ent_info, err = com.add_test_text(
        fake_doc, text="TEST",
        approval_token="token",
        allow_write=False,
        dry_run=False,
    )
    assert err == com._err.WRITE_NOT_ALLOWED
    assert ent_info is None
    fake_doc.ModelSpace.AddText.assert_not_called()


def test_add_test_text_approval_token_not_exposed(monkeypatch, tmp_path, caplog):
    """approval_token 이 로그에 노출되지 않음."""
    import logging
    from agent.connectors import cad_com_connector as com
    fake_app, fake_doc = _install_successful_mocks(monkeypatch, com)
    caplog.set_level(logging.WARNING)
    secret_token = "super_secret_token_12345"
    ent_info, err = com.add_test_text(
        fake_doc, text="TEST",
        approval_token=secret_token,
        allow_write=False,
        dry_run=False,
    )
    assert err == com._err.WRITE_NOT_ALLOWED
    assert ent_info is None
    for record in caplog.records:
        assert secret_token not in record.message


def test_run_basic_poc_planned_actions(monkeypatch, tmp_path):
    """run_basic_poc dry_run=True 시 planned_actions 구조 검증."""
    from agent.connectors import cad_com_connector as com
    f = tmp_path / "sample.dwg"
    f.write_bytes(b"dummy")
    out = com.run_basic_poc(str(f), dry_run=True)
    assert out["ok"] is True
    planned = out.get("planned_actions", [])
    assert isinstance(planned, list)
    assert len(planned) >= 4  # open, get_info, add_text, save
    assert planned[0]["action"] == "cad.open"
    assert planned[1]["action"] == "cad.get_document_info"
    assert planned[2]["action"] == "cad.add_test_text"
    # token/secret 이 노출되지 않아야 함
    for action_dict in planned:
        assert "action" in action_dict
        assert isinstance(action_dict["action"], str)
        for key, val in action_dict.items():
            if isinstance(val, str):
                assert "token" not in val.lower()
                assert "secret" not in val.lower()


# ──────────────────────────────────────────────────────────────────
# 11) 에러 코드 등록 확인
# ──────────────────────────────────────────────────────────────────
def test_cad_error_codes_registered():
    from agent import errors
    for name in (
        "CAD_COM_NOT_SUPPORTED",
        "CAD_COM_DISPATCH_FAILED",
        "CAD_APP_NOT_FOUND",
        "CAD_DOCUMENT_OPEN_FAILED",
        "CAD_DOCUMENT_INFO_FAILED",
        "CAD_ENTITY_ADD_FAILED",
        "CAD_DOCUMENT_SAVE_FAILED",
    ):
        assert hasattr(errors, name), f"errors.{name} missing"
        assert getattr(errors, name) in errors.ALL_CODES, name
        assert errors.is_standard_code(getattr(errors, name))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
