"""task_executor — CAD 액션 (2단계 편입) 단위 테스트.

실제 AutoCAD 나 Windows COM 에 의존하지 않도록 ``cad_com_connector`` 의
함수들을 monkeypatch 로 통째로 대체한다. 여기서 검증하는 것:

1. action_registry 에 CAD 액션 3종이 등록되어 있다.
2. cad.health 는 file_path 없이도 정상 결과를 낸다.
3. cad.open_info 성공/실패 흐름과 finally 에서의 close/quit.
4. cad.add_text_save_as 성공 흐름 + save_as 없을 때의 표준 실패.
5. save_as == file_path 인 경우 CAD_OVERWRITE_FORBIDDEN 반환.
6. 잘못된 text/height/좌표 인자는 CAD_INVALID_ARGUMENT 로 거절.
7. connector 가 반환한 표준 에러 코드가 그대로 노출된다.
8. 핸들러 내부 예외는 결과 dict 의 standard 형태로 전환된다.
9. 새로 추가된 CAD_* executor 수준 코드가 errors.ALL_CODES 에 있다.
"""
from __future__ import annotations

import os
import sys
from typing import Any, List, Tuple

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


class _CadStub:
    """cad_com_connector 대체용 스텁.

    task_executor 는 ``from .connectors import cad_com_connector as cad_com``
    으로 모듈을 참조하므로, monkeypatch 로 ``te.cad_com`` 을 이 인스턴스로
    교체한다.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, tuple, dict]] = []
        # 기본값: 성공 경로
        self.health_return = {
            "ok": True, "platform": "win32", "cad_available": True,
            "prog_id": "AutoCAD.Application.24.3",
            "version": "24.3", "product_name": "AutoCAD",
            "lt_or_limited": False, "error": None,
        }
        self.open_cad_app_return: Tuple[Any, Any, Any] = (
            object(), None, "AutoCAD.Application.24.3",
        )
        self.open_document_return: Tuple[Any, Any] = (object(), None)
        self.get_document_info_return: Tuple[Any, Any] = (
            {"name": "sample.dwg", "full_name": "C:\\tmp\\cad_poc\\sample.dwg",
             "model_space_count": 0, "active_layout": "Model"},
            None,
        )
        self.add_test_text_return: Tuple[Any, Any] = (
            {"type": "Text", "text": "POC_OK", "handle": "8B",
             "object_name": "AcDbText"},
            None,
        )
        self.save_document_as_return: Any = None

    def is_cad_available(self):
        self.calls.append(("is_cad_available", (), {}))
        return dict(self.health_return)

    def open_cad_app(self, visible=True):
        self.calls.append(("open_cad_app", (), {"visible": visible}))
        return self.open_cad_app_return

    def open_document(self, app, file_path):
        self.calls.append(("open_document", (file_path,), {}))
        return self.open_document_return

    def get_document_info(self, doc):
        self.calls.append(("get_document_info", (), {}))
        return self.get_document_info_return

    def add_test_text(self, doc, *, text, x, y, z, height):
        self.calls.append(
            ("add_test_text", (), {"text": text, "x": x, "y": y, "z": z,
                                   "height": height}),
        )
        return self.add_test_text_return

    def save_document_as(self, doc, output_path):
        self.calls.append(("save_document_as", (output_path,), {}))
        return self.save_document_as_return

    def close_document(self, doc, save_changes=False):
        self.calls.append(("close_document", (), {"save_changes": save_changes}))

    def quit_cad(self, app):
        self.calls.append(("quit_cad", (), {}))


@pytest.fixture()
def stub_cad(monkeypatch):
    from agent import task_executor as te
    stub = _CadStub()
    monkeypatch.setattr(te, "cad_com", stub)
    return stub


# ══════════════════════════════════════════════════════════════════════
# 1) 등록 확인
# ══════════════════════════════════════════════════════════════════════
def test_cad_actions_registered():
    from agent import action_registry as reg
    for name in ("cad.health", "cad.open_info", "cad.add_text_save_as"):
        assert reg.is_known_action(name), f"{name} not registered"
        assert reg.category_of(name) == reg.CATEGORY_CAD


def test_cad_supported_by_executor():
    from agent import task_executor as te
    assert "cad.health" in te.supported_actions()
    assert "cad.open_info" in te.supported_actions()
    assert "cad.add_text_save_as" in te.supported_actions()


# ══════════════════════════════════════════════════════════════════════
# 2) cad.health
# ══════════════════════════════════════════════════════════════════════
def test_cad_health_success_without_file_path(stub_cad):
    from agent import task_executor as te
    out = te.execute_task({"action": "cad.health"})
    assert out["ok"] is True
    assert out["error"] is None
    # connector 가 반환한 info 는 data 로 나와야 한다
    assert out["data"]["prog_id"] == "AutoCAD.Application.24.3"
    assert out["data"]["cad_available"] is True
    assert out["data"]["platform"] == "win32"
    names = [c[0] for c in stub_cad.calls]
    assert names == ["is_cad_available"]


def test_cad_health_failure_maps_error(stub_cad):
    from agent import task_executor as te
    from agent import errors
    stub_cad.health_return = {
        "ok": False, "cad_available": False, "platform": "linux",
        "error": errors.CAD_COM_NOT_SUPPORTED,
    }
    out = te.execute_task({"action": "cad.health"})
    assert out["ok"] is False
    assert out["error"] == errors.CAD_COM_NOT_SUPPORTED
    # 실패여도 data 는 병합되어 내려감
    assert out["data"]["cad_available"] is False


# ══════════════════════════════════════════════════════════════════════
# 3) cad.open_info
# ══════════════════════════════════════════════════════════════════════
def test_cad_open_info_requires_file_path(stub_cad):
    from agent import task_executor as te
    out = te.execute_task({"action": "cad.open_info"})
    assert out["ok"] is False
    assert out["error"] == te.FILE_PATH_REQUIRED
    assert stub_cad.calls == []


def test_cad_open_info_success(stub_cad):
    from agent import task_executor as te
    out = te.execute_task({
        "action": "cad.open_info",
        "file_path": r"C:\tmp\cad_poc\sample.dwg",
        "visible": False,
    })
    assert out["ok"] is True
    assert out["error"] is None
    assert out["data"]["name"] == "sample.dwg"
    assert out["data"]["active_layout"] == "Model"
    names = [c[0] for c in stub_cad.calls]
    # 열기/정보/닫기/종료 순서
    assert names == [
        "open_cad_app", "open_document",
        "get_document_info", "close_document", "quit_cad",
    ]
    # visible=False 전파
    assert stub_cad.calls[0][2]["visible"] is False


def test_cad_open_info_open_cad_app_failure(stub_cad):
    from agent import task_executor as te
    from agent import errors
    stub_cad.open_cad_app_return = (None, errors.CAD_APP_NOT_FOUND, None)
    out = te.execute_task({
        "action": "cad.open_info",
        "file_path": r"C:\tmp\cad_poc\sample.dwg",
    })
    assert out["ok"] is False
    assert out["error"] == errors.CAD_APP_NOT_FOUND
    # doc 이 없으므로 open_document 는 호출되지 않는다
    names = [c[0] for c in stub_cad.calls]
    assert "open_document" not in names


def test_cad_open_info_document_open_failure_cleans_up(stub_cad):
    from agent import task_executor as te
    from agent import errors
    stub_cad.open_document_return = (None, errors.CAD_DOCUMENT_OPEN_FAILED)
    out = te.execute_task({
        "action": "cad.open_info",
        "file_path": r"C:\tmp\cad_poc\sample.dwg",
    })
    assert out["ok"] is False
    assert out["error"] == errors.CAD_DOCUMENT_OPEN_FAILED
    names = [c[0] for c in stub_cad.calls]
    # open_document 가 실패해도 quit_cad 는 실행되어 AutoCAD 프로세스를 정리
    assert "quit_cad" in names


def test_cad_open_info_info_failure_still_closes(stub_cad):
    from agent import task_executor as te
    from agent import errors
    stub_cad.get_document_info_return = (None, errors.CAD_DOCUMENT_INFO_FAILED)
    out = te.execute_task({
        "action": "cad.open_info",
        "file_path": r"C:\tmp\cad_poc\sample.dwg",
    })
    assert out["ok"] is False
    assert out["error"] == errors.CAD_DOCUMENT_INFO_FAILED
    names = [c[0] for c in stub_cad.calls]
    assert "close_document" in names
    assert "quit_cad" in names


# ══════════════════════════════════════════════════════════════════════
# 4) cad.add_text_save_as
# ══════════════════════════════════════════════════════════════════════
def test_cad_write_requires_file_path(stub_cad):
    from agent import task_executor as te
    out = te.execute_task({
        "action": "cad.add_text_save_as",
        "save_as": r"C:\tmp\cad_poc\out.dwg",
    })
    assert out["ok"] is False
    assert out["error"] == te.FILE_PATH_REQUIRED
    assert stub_cad.calls == []


def test_cad_write_requires_save_as(stub_cad):
    from agent import task_executor as te
    out = te.execute_task({
        "action": "cad.add_text_save_as",
        "file_path": r"C:\tmp\cad_poc\sample.dwg",
    })
    assert out["ok"] is False
    assert out["error"] == te.SAVE_AS_REQUIRED
    assert stub_cad.calls == []


def test_cad_write_rejects_save_as_equal_to_file_path(stub_cad):
    from agent import task_executor as te
    from agent import errors
    same = r"C:\tmp\cad_poc\sample.dwg"
    out = te.execute_task({
        "action": "cad.add_text_save_as",
        "file_path": same,
        "save_as": same,
    })
    assert out["ok"] is False
    assert out["error"] == errors.CAD_OVERWRITE_FORBIDDEN
    # 원본 overwrite 시도는 COM 호출 이전에 거절되어야 한다
    assert stub_cad.calls == []


@pytest.mark.parametrize(
    "task_overrides, expected_err_attr",
    [
        ({"text": 123}, "CAD_INVALID_ARGUMENT"),
        ({"text": ""}, "CAD_INVALID_ARGUMENT"),
        ({"text": "x" * 5000}, "CAD_INVALID_ARGUMENT"),
        ({"height": 0}, "CAD_INVALID_ARGUMENT"),
        ({"height": -1}, "CAD_INVALID_ARGUMENT"),
        ({"x": "nope"}, "CAD_INVALID_ARGUMENT"),
    ],
)
def test_cad_write_invalid_argument(stub_cad, task_overrides, expected_err_attr):
    from agent import task_executor as te
    from agent import errors
    task = {
        "action": "cad.add_text_save_as",
        "file_path": r"C:\tmp\cad_poc\sample.dwg",
        "save_as": r"C:\tmp\cad_poc\out.dwg",
    }
    task.update(task_overrides)
    out = te.execute_task(task)
    assert out["ok"] is False
    assert out["error"] == getattr(errors, expected_err_attr)
    # 검증 실패는 COM 호출 전에 일어나야 한다
    assert stub_cad.calls == []


def test_cad_write_success_flow(stub_cad):
    from agent import task_executor as te
    out = te.execute_task({
        "action": "cad.add_text_save_as",
        "file_path": r"C:\tmp\cad_poc\sample.dwg",
        "save_as": r"C:\tmp\cad_poc\out.dwg",
        "text": "POC_OK",
        "visible": False,
        "x": 1.0, "y": 2.0, "z": 0.0, "height": 2.5,
    })
    assert out["ok"] is True
    assert out["error"] is None
    assert out["data"]["saved_as"] == r"C:\tmp\cad_poc\out.dwg"
    assert out["data"]["added_entity"]["text"] == "POC_OK"
    assert out["data"]["added_entity"]["type"] == "Text"
    assert out["data"]["closed"] is True
    assert out["data"]["quit"] is True
    names = [c[0] for c in stub_cad.calls]
    # 열기 → 텍스트 추가 → save_as → 닫기 → 종료
    assert names == [
        "open_cad_app", "open_document", "add_test_text",
        "save_document_as", "close_document", "quit_cad",
    ]
    # add_test_text 인자 검증
    add_kw = stub_cad.calls[2][2]
    assert add_kw["text"] == "POC_OK"
    assert add_kw["x"] == 1.0
    assert add_kw["y"] == 2.0
    assert add_kw["height"] == 2.5
    # save_document_as 는 주어진 save_as 경로로 호출
    assert stub_cad.calls[3][1][0] == r"C:\tmp\cad_poc\out.dwg"


def test_cad_write_add_text_failure_cleans_up(stub_cad):
    from agent import task_executor as te
    from agent import errors
    stub_cad.add_test_text_return = (None, errors.CAD_ENTITY_ADD_FAILED)
    out = te.execute_task({
        "action": "cad.add_text_save_as",
        "file_path": r"C:\tmp\cad_poc\sample.dwg",
        "save_as": r"C:\tmp\cad_poc\out.dwg",
    })
    assert out["ok"] is False
    assert out["error"] == errors.CAD_ENTITY_ADD_FAILED
    names = [c[0] for c in stub_cad.calls]
    assert "save_document_as" not in names
    assert "close_document" in names
    assert "quit_cad" in names


def test_cad_write_save_as_failure_cleans_up(stub_cad):
    from agent import task_executor as te
    from agent import errors
    stub_cad.save_document_as_return = errors.CAD_DOCUMENT_SAVE_FAILED
    out = te.execute_task({
        "action": "cad.add_text_save_as",
        "file_path": r"C:\tmp\cad_poc\sample.dwg",
        "save_as": r"C:\tmp\cad_poc\out.dwg",
    })
    assert out["ok"] is False
    assert out["error"] == errors.CAD_DOCUMENT_SAVE_FAILED
    assert out["data"]["save_as"] == r"C:\tmp\cad_poc\out.dwg"
    names = [c[0] for c in stub_cad.calls]
    assert "close_document" in names
    assert "quit_cad" in names


# ══════════════════════════════════════════════════════════════════════
# 5) 핸들러 내부 예외 → 결과 dict 전환
# ══════════════════════════════════════════════════════════════════════
def test_cad_handler_crash_converted(monkeypatch):
    from agent import task_executor as te

    class _Boom:
        def open_cad_app(self, visible=True):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(te, "cad_com", _Boom())
    out = te.execute_task({
        "action": "cad.open_info",
        "file_path": r"C:\tmp\cad_poc\sample.dwg",
    })
    assert out["ok"] is False
    assert out["error"].startswith("handler_crashed:")
    assert "RuntimeError" in out["error"]


# ══════════════════════════════════════════════════════════════════════
# 6) 새 CAD executor-레벨 에러 코드가 표준 코드로 등록
# ══════════════════════════════════════════════════════════════════════
def test_new_cad_executor_error_codes_registered():
    from agent import errors
    for name in (
        "CAD_INVALID_PATH",
        "CAD_OVERWRITE_FORBIDDEN",
        "CAD_INVALID_ARGUMENT",
    ):
        assert hasattr(errors, name), f"errors.{name} missing"
        assert getattr(errors, name) in errors.ALL_CODES
        assert errors.is_standard_code(getattr(errors, name))


# ══════════════════════════════════════════════════════════════════════
# 7) approval_policy 와의 연결 — 정책 손대지 않고 그 위에서 동작 확인
# ══════════════════════════════════════════════════════════════════════
def test_approval_policy_allows_cad_health_without_file_path(monkeypatch, tmp_path):
    """cad.health 는 requires_file_path=False 라 경로 검사가 면제된다."""
    from agent import approval_policy, config as _cfg
    monkeypatch.setattr(_cfg, "AGENT_WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(_cfg, "AGENT_OUTPUT_DIR", tmp_path / "out")
    decision = approval_policy.evaluate({"action": "cad.health"})
    assert decision.allowed is True
    assert decision.error is None
    assert decision.category == "cad"
    assert decision.risk_level == "low"


def test_approval_policy_requires_file_path_for_cad_open_info(tmp_path, monkeypatch):
    from agent import approval_policy, config as _cfg
    monkeypatch.setattr(_cfg, "AGENT_WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(_cfg, "AGENT_OUTPUT_DIR", tmp_path / "out")
    decision = approval_policy.evaluate({"action": "cad.open_info"})
    assert decision.allowed is False
    # 기존 file_path 강제 규칙이 그대로 적용되어야 한다
    from agent import errors
    assert decision.error == errors.FILE_PATH_REQUIRED


def test_approval_policy_cad_write_requires_approval_token(tmp_path, monkeypatch):
    """cad.add_text_save_as 는 medium — 기존 정책상 approval_token 이 필수."""
    from agent import approval_policy, approval_policy as ap, config as _cfg
    work = tmp_path / "work"
    out_dir = tmp_path / "out"
    work.mkdir(); out_dir.mkdir()
    f = work / "sample.dwg"
    f.write_bytes(b"dummy")
    monkeypatch.setattr(_cfg, "AGENT_WORK_DIR", work)
    monkeypatch.setattr(_cfg, "AGENT_OUTPUT_DIR", out_dir)

    # token 없이 호출
    decision = approval_policy.evaluate({
        "action": "cad.add_text_save_as",
        "file_path": str(f),
        "save_as": str(out_dir / "out.dwg"),
    })
    assert decision.allowed is False
    assert decision.error == ap.APPROVAL_REQUIRED
    assert decision.risk_level == "medium"

    # token 주면 허용
    decision = approval_policy.evaluate({
        "action": "cad.add_text_save_as",
        "file_path": str(f),
        "save_as": str(out_dir / "out.dwg"),
        "approval_token": "ok",
        "approved_by": "alice",
    })
    assert decision.allowed is True
    assert decision.approved is True
    assert decision.approved_by == "alice"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
