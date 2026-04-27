"""Windows COM 기반 실제 AutoCAD 제어 (B안 1단계 POC).

목적
-----
로컬 Windows PC 에 설치된 정식 AutoCAD 데스크톱 앱을 ``win32com.client`` 로
실제 구동해
- 앱 실행 / DWG 문서 열기 / 문서 정보 읽기 / 테스트 엔터티 추가 /
  다른 이름 저장 / 종료
가 동작하는지 최소 범위로 증명한다.

설계 원칙
---------
- ``win32com.client`` 는 **지연 import**. 비 Windows 환경에서 모듈 import
  자체가 실패하지 않도록 한다.
- 플랫폼/Dispatch 실패는 ``agent.errors`` 의 표준 CAD_* 코드로 반환.
- 모든 실패 경로에서 문서/app 핸들을 ``finally`` 로 정리.
- 허용 경로 정책은 1·2단계 file_policy 와 독립적으로, 최소한 **절대경로만**
  받도록 가드.
- AutoCAD LT / Mac 은 이번 단계 지원 대상이 아니다 (LT 는 ActiveX 가
  제한되거나 차단됨). LT 여부는 ProductName 에서 감지해 플래그로 노출만
  한다.
- 기존 ``excel_com_connector`` / ``hwp_com_connector`` 와 네임스페이스
  충돌 없이 독립 운영.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

from .. import errors as _err

logger = logging.getLogger(__name__)

# AutoCAD ActiveX 호출 시 AutoCAD 가 초기화/모달 상태이면 HRESULT 로
# RPC_E_CALL_REJECTED (0x80010001) 혹은 RPC_E_SERVERCALL_RETRYLATER
# (0x8001010A) 를 돌려주는 경우가 많다. 짧은 backoff 후 재시도해야
# 실전에서 안정적이다.
_RPC_E_CALL_REJECTED = -2147418111
_RPC_E_SERVERCALL_RETRYLATER = -2147417846
_RETRYABLE_HRESULTS = frozenset({_RPC_E_CALL_REJECTED, _RPC_E_SERVERCALL_RETRYLATER})

_DEFAULT_RETRY_TRIES = 20
_DEFAULT_RETRY_DELAY = 0.5


# ── 보안: 승인/dry-run 게이트 ───────────────────────────────────────────
def _require_approval_for_write(
    action: str,
    approval_token: Optional[str],
    allow_write: bool,
) -> Optional[str]:
    """write 액션 승인 검증. 차단 시 에러 코드 반환, 통과 시 None."""
    if not allow_write:
        logger.warning("[CAD-WRITE-BLOCKED] action=%s allow_write=False", action)
        return _err.WRITE_NOT_ALLOWED
    if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
        logger.warning("[CAD-WRITE-BLOCKED] action=%s approval_token missing", action)
        return _err.WRITE_APPROVAL_REQUIRED
    return None

# AutoCAD Application COM progid 후보. 버전 의존 progid 를 먼저 시도하고
# 실패 시 unversioned progid 로 폴백한다. Autodesk 공식 문서 기준으로
# AutoCAD 2020 = 23.1, 2021 = 24.0, 2022 = 24.1, 2023 = 24.2, 2024 = 24.3,
# 2025 = 25.0 식으로 버전이 증가한다.
_CAD_PROGID_CANDIDATES: Tuple[str, ...] = (
    "AutoCAD.Application.25.0",
    "AutoCAD.Application.24.3",
    "AutoCAD.Application.24.2",
    "AutoCAD.Application.24.1",
    "AutoCAD.Application.24.0",
    "AutoCAD.Application.23.1",
    "AutoCAD.Application",
)


# ── 플랫폼 / 지연 import ────────────────────────────────────────────
def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _try_import_win32com() -> Tuple[Optional[Any], Optional[str]]:
    """``win32com.client`` 지연 import.

    반환: (module_or_None, error_or_None).
    테스트에서 monkeypatch 로 상태를 시뮬레이션하기 위해 분리.
    """
    if not _is_windows():
        return None, _err.CAD_COM_NOT_SUPPORTED
    try:
        import win32com.client as _win32com  # type: ignore
        return _win32com, None
    except ImportError:
        return None, _err.CAD_COM_DISPATCH_FAILED


def _dispatch_autocad(win32com_mod: Any) -> Tuple[Optional[Any], Optional[str], Optional[str]]:
    """후보 ProgID 를 순차 시도해 최초 성공한 핸들과 progid 를 반환.

    AutoCAD ActiveX 는 late-binding 에서 ``Documents.Open`` 등 일부 메서드가
    ``GetIDsOfNames`` 로 해석되지 않는 증상이 있어, 우선 ``gencache.EnsureDispatch``
    로 early-binding 핸들을 받는다. 실패 시 plain ``Dispatch`` 로 폴백.

    반환: (app_or_None, progid_or_None, error_or_None).
    """
    # gencache 는 win32com.client 의 하위 모듈. 테스트에서 MagicMock 이
    # 넘어오는 경우까지 고려해 best-effort 로 가져온다.
    gencache = getattr(win32com_mod, "gencache", None)
    if gencache is None:
        try:
            from win32com.client import gencache as _gencache  # type: ignore
            gencache = _gencache
        except ImportError:
            gencache = None

    for progid in _CAD_PROGID_CANDIDATES:
        # 1) early-binding 먼저
        if gencache is not None:
            try:
                app = gencache.EnsureDispatch(progid)
                return app, progid, None
            except Exception as e:  # noqa: BLE001 - COM 예외 유형 다양
                logger.info(
                    "%s EnsureDispatch 실패: %s", progid, type(e).__name__,
                )
        # 2) late-binding 폴백
        try:
            app = win32com_mod.Dispatch(progid)
            return app, progid, None
        except Exception as e:  # noqa: BLE001
            logger.info(
                "%s Dispatch 실패: %s", progid, type(e).__name__,
            )
            continue
    return None, None, _err.CAD_APP_NOT_FOUND


def _call_with_retry(
    fn: Callable[[], Any],
    *,
    tries: int = _DEFAULT_RETRY_TRIES,
    delay: float = _DEFAULT_RETRY_DELAY,
) -> Any:
    """AutoCAD 가 RPC_E_CALL_REJECTED / RETRYLATER 를 돌려줄 때 짧게 재시도.

    다른 HRESULT 나 비-COM 예외는 즉시 전파한다 (실패 분기를 숨기지 않기
    위함). 테스트에서는 MagicMock 이 예외를 내지 않으므로 첫 호출에서
    바로 결과를 받는다.
    """
    last_exc: Optional[BaseException] = None
    for _ in range(max(1, int(tries))):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - 재시도 가능 여부만 판정
            hr = None
            args = getattr(e, "args", None) or ()
            if args:
                first = args[0]
                if isinstance(first, int):
                    hr = first
            if hr in _RETRYABLE_HRESULTS:
                last_exc = e
                time.sleep(delay)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retries exhausted")


def _autocad_point(x: float, y: float, z: float) -> Any:
    """``(x, y, z)`` 를 AutoCAD ActiveX 가 요구하는 VT_ARRAY|VT_R8 VARIANT
    로 래핑.

    pywin32 / pythoncom 이 없는 환경(테스트/Linux)에서는 일반 tuple 을
    반환해 MagicMock 기반 단위 테스트가 깨지지 않도록 한다.
    """
    try:
        import pythoncom  # type: ignore
        from win32com.client import VARIANT  # type: ignore
    except ImportError:
        return (float(x), float(y), float(z))
    return VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8,
        (float(x), float(y), float(z)),
    )


def _detect_lt_or_limited(product_name: str) -> bool:
    """ProductName 문자열에서 LT / 제한 버전을 감지.

    LT 는 ActiveX 가 차단되어 이 POC 대상이 아니므로, Dispatch 가 성공해도
    LT 로 보이면 경고용 플래그만 올린다.
    """
    if not isinstance(product_name, str):
        return False
    pn = product_name.lower()
    return ("lt" in pn.split()) or ("autocad lt" in pn)


# ── 가용성 점검 ─────────────────────────────────────────────────────
def is_cad_available() -> dict:
    """플랫폼 / pywin32 / AutoCAD 설치 세 층위를 순차적으로 진단.

    반환 예 (성공):
      {"ok": True, "platform": "win32", "cad_available": True,
       "prog_id": "AutoCAD.Application.24.3", "version": "24.3",
       "product_name": "AutoCAD", "lt_or_limited": False}

    반환 예 (실패):
      {"ok": False, "platform": "...", "cad_available": False,
       "error": "cad_com_not_supported" | ...}
    """
    platform_name = sys.platform
    if not _is_windows():
        return {
            "ok": False,
            "platform": platform_name,
            "cad_available": False,
            "error": _err.CAD_COM_NOT_SUPPORTED,
        }

    win32com_mod, err = _try_import_win32com()
    if err or win32com_mod is None:
        return {
            "ok": False,
            "platform": platform_name,
            "cad_available": False,
            "error": err or _err.CAD_COM_DISPATCH_FAILED,
        }

    app, progid, err = _dispatch_autocad(win32com_mod)
    if err or app is None:
        return {
            "ok": False,
            "platform": platform_name,
            "cad_available": False,
            "error": err or _err.CAD_APP_NOT_FOUND,
        }

    version = ""
    try:
        version = str(getattr(app, "Version", ""))
    except Exception:  # noqa: BLE001
        version = ""

    product_name = ""
    try:
        product_name = str(getattr(app, "ProductName", "") or "")
    except Exception:  # noqa: BLE001
        product_name = ""

    lt_or_limited = _detect_lt_or_limited(product_name)

    try:
        app.Quit()
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "platform": platform_name,
        "cad_available": True,
        "prog_id": progid,
        "version": version,
        "product_name": product_name,
        "lt_or_limited": lt_or_limited,
    }


# ── 핸들 관리 ──────────────────────────────────────────────────────
def open_cad_app(
    visible: bool = True,
) -> Tuple[Optional[Any], Optional[str], Optional[str]]:
    """AutoCAD Application COM 객체와 최초 성공한 ProgID 를 반환.

    - Visible 기본 True (POC 단계에서는 눈으로 확인이 중요).
    - LT 감지 시에는 일단 앱 핸들을 돌려주되 이후 ModelSpace 접근에서 실패
      할 수 있다.
    - 반환: ``(app, err, prog_id)``. ``err`` 가 None 이면 ``app`` 과
      ``prog_id`` 가 유효.
    """
    win32com_mod, err = _try_import_win32com()
    if err or win32com_mod is None:
        return None, err or _err.CAD_COM_DISPATCH_FAILED, None
    app, progid, err = _dispatch_autocad(win32com_mod)
    if err or app is None:
        return None, err or _err.CAD_APP_NOT_FOUND, None
    try:
        app.Visible = bool(visible)
    except Exception:  # noqa: BLE001
        pass
    return app, None, progid


def extract_app_info(app: Any, prog_id: Optional[str] = None) -> dict:
    """이미 Dispatch 된 AutoCAD Application 에서 identity 정보를 추출.

    Quit 하지 않으며, 어떤 접근이 실패해도 부분 결과만 채운 dict 를
    반환한다. ``run_basic_poc`` 가 단일 Dispatch 결과에서 availability
    정보를 합성하는 데 사용된다.
    """
    info: dict = {
        "prog_id": prog_id,
        "version": "",
        "product_name": "",
        "lt_or_limited": False,
    }
    if app is None:
        return info
    try:
        info["version"] = str(getattr(app, "Version", "") or "")
    except Exception:  # noqa: BLE001
        pass
    try:
        info["product_name"] = str(getattr(app, "ProductName", "") or "")
    except Exception:  # noqa: BLE001
        pass
    info["lt_or_limited"] = _detect_lt_or_limited(info["product_name"])
    return info


# ── 문서 열기 ──────────────────────────────────────────────────────
def open_document(
    app: Any, file_path: str,
) -> Tuple[Optional[Any], Optional[str]]:
    """절대경로로 DWG 문서를 연다.

    성공 시 (doc, None), 실패 시 (None, err_code).
    """
    if app is None:
        return None, _err.CAD_APP_NOT_FOUND
    if not isinstance(file_path, str) or not file_path.strip():
        return None, _err.FILE_PATH_REQUIRED
    try:
        p = Path(file_path).expanduser()
    except (OSError, ValueError):
        return None, _err.FILE_NOT_ALLOWED
    if not p.is_absolute():
        return None, _err.FILE_NOT_ALLOWED
    if not p.exists() or not p.is_file():
        return None, _err.FILE_NOT_FOUND
    try:
        doc = _call_with_retry(lambda: app.Documents.Open(str(p)))
    except Exception as e:  # noqa: BLE001
        logger.info("AutoCAD Documents.Open 실패 (%s): %s", p, type(e).__name__)
        return None, _err.CAD_DOCUMENT_OPEN_FAILED
    if doc is None:
        return None, _err.CAD_DOCUMENT_OPEN_FAILED
    return doc, None


# ── 문서 정보 ──────────────────────────────────────────────────────
def get_document_info(doc: Any) -> Tuple[Optional[dict], Optional[str]]:
    """최소 정보: name / full_name / model_space_count / active_layout.

    AutoCAD COM 객체 접근이 한 단계라도 실패하면 ``cad_document_info_failed``
    로 반환한다. 모든 접근을 묶어 실패를 단일 코드로 정규화.
    """
    if doc is None:
        return None, _err.CAD_DOCUMENT_INFO_FAILED
    try:
        name = str(_call_with_retry(lambda: getattr(doc, "Name", "") or ""))
        full_name = str(_call_with_retry(lambda: getattr(doc, "FullName", "") or ""))
        ms = _call_with_retry(lambda: doc.ModelSpace)
        count = int(_call_with_retry(lambda: getattr(ms, "Count", 0) or 0))
        layout_name = ""
        active_layout = _call_with_retry(lambda: getattr(doc, "ActiveLayout", None))
        if active_layout is not None:
            layout_name = str(
                _call_with_retry(lambda: getattr(active_layout, "Name", "") or "")
            )
    except Exception as e:  # noqa: BLE001
        logger.info("get_document_info 실패: %s", type(e).__name__)
        return None, _err.CAD_DOCUMENT_INFO_FAILED
    return (
        {
            "name": name,
            "full_name": full_name,
            "model_space_count": count,
            "active_layout": layout_name,
        },
        None,
    )


# ── 엔터티 추가 ────────────────────────────────────────────────────
def add_test_text(
    doc: Any,
    text: str = "POC_OK",
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    height: float = 2.5,
    *,
    approval_token: Optional[str] = None,
    dry_run: bool = True,
    allow_write: bool = False,
) -> Tuple[Optional[dict], Optional[str]]:
    """ModelSpace 에 단일 Text 엔터티 하나를 추가. dry-run 게이트 포함.

    ``AddText(TextString, InsertionPoint, Height)`` 가 AutoCAD 표준 API.
    InsertionPoint 는 길이 3 의 double 배열(VARIANT) 이어야 해 win32com 의
    VARIANT 변환을 거치는데, pywin32 는 파이썬 tuple 을 자동으로 safearray
    로 변환하는 편이 안정적이다. 실패 시 MText 폴백 없이 단일 실패로 처리.
    """
    if doc is None:
        return None, _err.CAD_ENTITY_ADD_FAILED
    if not isinstance(text, str):
        return None, _err.CAD_ENTITY_ADD_FAILED
    try:
        h = float(height)
        point = _autocad_point(x, y, z)
    except (TypeError, ValueError):
        return None, _err.CAD_ENTITY_ADD_FAILED
    if h <= 0:
        return None, _err.CAD_ENTITY_ADD_FAILED

    if dry_run:
        logger.info("[CAD-DRY-RUN] add_test_text would_modify=True")
        return {"type": "Text", "text": text}, None

    approval_err = _require_approval_for_write("cad.add_test_text", approval_token, allow_write)
    if approval_err:
        return None, approval_err

    try:
        ms = _call_with_retry(lambda: doc.ModelSpace)
        ent = _call_with_retry(lambda: ms.AddText(text, point, h))
    except Exception as e:  # noqa: BLE001
        logger.info("AddText 실패: %s", type(e).__name__)
        return None, _err.CAD_ENTITY_ADD_FAILED

    info: dict = {"type": "Text", "text": text}
    try:
        handle = getattr(ent, "Handle", None)
        if handle is not None:
            info["handle"] = str(handle)
    except Exception:  # noqa: BLE001
        pass
    try:
        obj_name = getattr(ent, "ObjectName", None)
        if obj_name:
            info["object_name"] = str(obj_name)
    except Exception:  # noqa: BLE001
        pass
    return info, None


# ── 저장 / 종료 ────────────────────────────────────────────────────
def save_document(doc: Any) -> Optional[str]:
    """현재 문서를 현재 경로로 저장."""
    if doc is None:
        return _err.CAD_DOCUMENT_SAVE_FAILED
    try:
        _call_with_retry(lambda: doc.Save())
    except Exception as e:  # noqa: BLE001
        logger.info("AutoCAD Save 실패: %s", type(e).__name__)
        return _err.CAD_DOCUMENT_SAVE_FAILED
    return None


def save_document_as(
    doc: Any,
    output_path: str,
    *,
    overwrite: bool = False,
    approval_token: Optional[str] = None,
    dry_run: bool = True,
    allow_write: bool = False,
) -> Optional[str]:
    """다른 이름 저장. 절대경로 필수, 기본 overwrite 금지, 승인/dry-run 게이트 포함."""
    if doc is None:
        return _err.CAD_DOCUMENT_SAVE_FAILED
    if not isinstance(output_path, str) or not output_path.strip():
        return _err.OUTPUT_PATH_REQUIRED
    try:
        p = Path(output_path).expanduser()
    except (OSError, ValueError):
        return _err.OUTPUT_PATH_NOT_ALLOWED
    if not p.is_absolute():
        return _err.OUTPUT_PATH_NOT_ALLOWED
    if p.exists() and not overwrite:
        return _err.OUTPUT_FILE_EXISTS
    if dry_run:
        logger.info("[CAD-DRY-RUN] save_document_as path=%s would_write=True", output_path)
        return None
    approval_err = _require_approval_for_write("cad.save_document_as", approval_token, allow_write)
    if approval_err:
        return approval_err
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return _err.OUTPUT_PATH_NOT_ALLOWED

    try:
        # AutoCAD 의 Document.SaveAs(FullFileName) — 포맷 인자는 생략 시
        # 확장자에서 추론된다. DWG 기본.
        _call_with_retry(lambda: doc.SaveAs(str(p)))
    except Exception as e:  # noqa: BLE001
        logger.info("AutoCAD SaveAs 실패 (%s): %s", p, type(e).__name__)
        return _err.CAD_DOCUMENT_SAVE_FAILED
    return None


def close_document(doc: Any, save_changes: bool = False) -> None:
    """현재 문서를 닫는다. 정리 경로이므로 예외는 삼킨다."""
    if doc is None:
        return
    try:
        doc.Close(bool(save_changes))
    except Exception as e:  # noqa: BLE001
        logger.info("Document.Close 실패 (정리 단계): %s", type(e).__name__)


def quit_cad(app: Any) -> None:
    """AutoCAD 프로세스를 종료. 정리 경로에서 호출되므로 예외를 삼킨다."""
    if app is None:
        return
    try:
        app.Quit()
    except Exception as e:  # noqa: BLE001
        logger.info("AutoCAD Quit 실패 (정리 단계): %s", type(e).__name__)


# ── 통합 POC ───────────────────────────────────────────────────────
def run_basic_poc(
    file_path: str,
    *,
    visible: bool = True,
    save_as: Optional[str] = None,
    text: str = "POC_OK",
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    height: float = 2.5,
    dry_run: bool = True,
    approval_token: Optional[str] = None,
    allow_write: bool = False,
) -> dict:
    """AutoCAD 실행 → 열기 → 정보 → 엔터티 추가 → 저장 → 종료.

    - dry_run=True (기본): COM 객체 미생성, planned_actions만 반환
    - approval_token 필수 (수정용)
    - allow_write=True만 실제 수정 허용

    각 단계 진행 상황을 ``result`` dict 에 순차 기록해 실패 지점을 분리
    가능한 진단 로그로 반환한다.
    """
    result: dict = {
        "ok": False,
        "file_path": file_path,
        "visible": bool(visible),
        "save_as": save_as,
        "dry_run": bool(dry_run),
        "allow_write": bool(allow_write),
        "planned_actions": [],
        "dispatched": False,
        "prog_id": None,
        "version": "",
        "product_name": "",
        "lt_or_limited": False,
        "document_opened": False,
        "document_info": None,
        "added_entity": None,
        "saved": False,
        "closed": False,
        "quit": False,
        "error": None,
    }

    if dry_run:
        result["planned_actions"] = [
            {"action": "cad.open", "file_path": file_path},
            {"action": "cad.get_document_info", "requires_approval": False},
            {"action": "cad.add_test_text", "requires_approval": True},
            {"action": "cad.save_as" if save_as else "cad.save", "requires_approval": True},
        ]
        logger.info("[CAD-DRY-RUN] planned_actions=%d", len(result["planned_actions"]))
        result["ok"] = True
        return result

    # 플랫폼/pywin32 사전 점검. AutoCAD Dispatch 자체는 아래에서 **한 번만**
    # 수행한다. 이전에는 is_cad_available() 로 Dispatch+Quit 하고 곧바로
    # open_cad_app() 로 재Dispatch 했는데, AutoCAD 는 재Dispatch 직후 한동안
    # 서버 예외(RPC_E_SERVERFAULT) 를 돌려주므로 이 경로를 막기 위한 리팩터.
    if not _is_windows():
        result["error"] = _err.CAD_COM_NOT_SUPPORTED
        return result
    _mod, import_err = _try_import_win32com()
    if import_err:
        result["error"] = import_err
        return result

    app, err, prog_id = open_cad_app(visible=visible)
    if err or app is None:
        result["error"] = err or _err.CAD_APP_NOT_FOUND
        return result
    result["dispatched"] = True
    # 동일 Dispatch 에서 availability 정보 추출 (Quit 하지 않음).
    info = extract_app_info(app, prog_id)
    result["prog_id"] = info.get("prog_id")
    result["version"] = info.get("version", "")
    result["product_name"] = info.get("product_name", "")
    result["lt_or_limited"] = bool(info.get("lt_or_limited"))

    doc = None
    try:
        doc, err = open_document(app, file_path)
        if err or doc is None:
            result["error"] = err or _err.CAD_DOCUMENT_OPEN_FAILED
            return result
        result["document_opened"] = True

        info, err = get_document_info(doc)
        if err:
            result["error"] = err
            return result
        result["document_info"] = info

        ent_info, err = add_test_text(
            doc, text=text, x=x, y=y, z=z, height=height,
            approval_token=approval_token, dry_run=False, allow_write=allow_write,
        )
        if err:
            result["error"] = err
            return result
        result["added_entity"] = ent_info

        if save_as:
            err = save_document_as(
                doc, save_as,
                approval_token=approval_token, dry_run=False, allow_write=allow_write,
            )
            if err:
                result["error"] = err
                return result
            result["saved"] = True
        # save_as 미지정 시 원본 overwrite 금지 — 저장 단계 skip.

        result["ok"] = True
        return result
    finally:
        if doc is not None:
            close_document(doc, save_changes=False)
            result["closed"] = True
        quit_cad(app)
        result["quit"] = True


__all__ = [
    "is_cad_available",
    "open_cad_app",
    "extract_app_info",
    "open_document",
    "get_document_info",
    "add_test_text",
    "save_document",
    "save_document_as",
    "close_document",
    "quit_cad",
    "run_basic_poc",
]
