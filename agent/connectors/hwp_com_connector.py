"""Windows COM 기반 실제 한글(HWP) 제어 (B안 1단계 POC).

목적
-----
로컬 Windows PC 에 설치된 한글 데스크톱 앱을 ``win32com.client`` 로 실제
구동해
- 앱 실행 / 문서 열기 / 텍스트 미리보기 / 텍스트 삽입 / 다른 이름 저장
이 동작하는지 최소 범위로 검증한다.

설계 원칙
---------
- ``win32com.client`` / ``pythoncom`` 은 **지연 import**. 비 Windows 환경에서
  모듈 import 자체가 실패하지 않도록 한다.
- 플랫폼/Dispatch 실패는 ``agent.errors`` 의 표준 HWP_* 코드로 반환.
- 모든 실패 경로에서 문서/app 핸들을 ``finally`` 로 정리.
- 허용 경로 정책은 1·2단계 file_policy 와 독립적으로, 최소한 **절대경로만**
  받도록 가드.
- 보안 모듈(FilePathCheckDLL) 등록 호출은 래퍼로만 제공하고, 레지스트리
  설치 자동화는 이 단계의 범위 밖이다. 등록 호출의 성공/실패만 분리 가능한
  진단 로그로 남긴다.
- 기존 ``excel_com_connector`` 와 충돌 없이 독립된 네임스페이스로 운영.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional, Tuple

from .. import errors as _err

logger = logging.getLogger(__name__)

# 한글 Application COM progid.
_HWP_PROGID = "HWPFrame.HwpObject"

# 보안 모듈 등록 기본 모듈명 (현장 설치 상황에 따라 변경 가능).
# 실제 등록된 DLL 이름과 정확히 일치해야 한다. 관행적으로 아래 둘 중 하나.
_DEFAULT_SECURITY_MODULE_NAME = "FilePathCheckerModule"


# ── 보안: 승인/dry-run 게이트 ───────────────────────────────────────────
def _require_approval_for_write(
    action: str,
    approval_token: Optional[str],
    allow_write: bool,
) -> Optional[str]:
    """write 액션 승인 검증. 차단 시 에러 코드 반환, 통과 시 None."""
    if not allow_write:
        logger.warning("[HWP-WRITE-BLOCKED] action=%s allow_write=False", action)
        return _err.WRITE_NOT_ALLOWED
    if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
        logger.warning("[HWP-WRITE-BLOCKED] action=%s approval_token missing", action)
        return _err.WRITE_APPROVAL_REQUIRED
    return None


# ── 플랫폼 / 지연 import ────────────────────────────────────────────
def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _try_import_win32com() -> Tuple[Optional[Any], Optional[str]]:
    """``win32com.client`` 지연 import.

    반환: (module_or_None, error_or_None).
    테스트에서 monkeypatch 로 상태를 시뮬레이션하기 위해 분리.
    """
    if not _is_windows():
        return None, _err.HWP_COM_NOT_SUPPORTED
    try:
        import win32com.client as _win32com  # type: ignore
        return _win32com, None
    except ImportError:
        return None, _err.HWP_COM_DISPATCH_FAILED


# ── 가용성 점검 ─────────────────────────────────────────────────────
def is_hwp_available() -> dict:
    """플랫폼 / pywin32 / HWP 설치 세 층위를 순차적으로 진단.

    반환 예 (성공):
      {"ok": True, "platform": "win32", "hwp_available": True,
       "version": "...", "security_module_registered": False}

    반환 예 (실패):
      {"ok": False, "platform": "...", "hwp_available": False,
       "error": "hwp_com_not_supported" | ...}

    주의:
    - ``security_module_registered`` 는 이번 단계에서 Dispatch 후 단순히
      RegisterModule 호출이 가능한지 여부만 간접적으로 표기한다. 실제로
      레지스트리/DLL 설치 상태까지 검증하려면 추가 도구가 필요하다.
    """
    platform_name = sys.platform
    if not _is_windows():
        return {
            "ok": False,
            "platform": platform_name,
            "hwp_available": False,
            "error": _err.HWP_COM_NOT_SUPPORTED,
        }

    win32com_mod, err = _try_import_win32com()
    if err or win32com_mod is None:
        return {
            "ok": False,
            "platform": platform_name,
            "hwp_available": False,
            "error": err or _err.HWP_COM_DISPATCH_FAILED,
        }

    try:
        app = win32com_mod.Dispatch(_HWP_PROGID)
    except Exception as e:  # noqa: BLE001 - COM 예외 유형 다양
        logger.info(
            "%s Dispatch 실패: %s", _HWP_PROGID, type(e).__name__,
        )
        return {
            "ok": False,
            "platform": platform_name,
            "hwp_available": False,
            "error": _err.HWP_APP_NOT_FOUND,
            "detail": type(e).__name__,
        }

    version = ""
    try:
        version = str(getattr(app, "Version", ""))
    except Exception:  # noqa: BLE001
        version = ""

    security_registered: Optional[bool] = None
    try:
        # RegisterModule 메서드 존재 여부만 가볍게 확인. 실제 호출은
        # register_file_path_check_module() 에서 수행.
        security_registered = hasattr(app, "RegisterModule")
    except Exception:  # noqa: BLE001
        security_registered = None

    try:
        app.Quit()
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "platform": platform_name,
        "hwp_available": True,
        "version": version,
        "security_module_registered": security_registered,
    }


# ── 보안 모듈 등록 ──────────────────────────────────────────────────
def register_file_path_check_module(
    app: Any, module_name: Optional[str] = None,
) -> dict:
    """``RegisterModule("FilePathCheckDLL", <module_name>)`` 호출 래퍼.

    현재 단계에서는 **호출 성공/실패만** 명확히 드러내는 것이 목적이며,
    DLL 배포/레지스트리 설치까지 자동화하지 않는다. 반환 값:

      {"ok": true,  "module_name": "...", "return_value": ...}
      {"ok": false, "module_name": "...", "error": "..."}
    """
    name = module_name or _DEFAULT_SECURITY_MODULE_NAME
    if app is None:
        return {
            "ok": False, "module_name": name,
            "error": _err.HWP_APP_NOT_FOUND,
        }
    register = getattr(app, "RegisterModule", None)
    if register is None:
        return {
            "ok": False, "module_name": name,
            "error": _err.HWP_SECURITY_MODULE_REQUIRED,
        }
    try:
        rv = register("FilePathCheckDLL", name)
    except Exception as e:  # noqa: BLE001 - COM 예외 유형 다양
        logger.info(
            "RegisterModule 실패 (%s): %s", name, type(e).__name__,
        )
        return {
            "ok": False, "module_name": name,
            "error": _err.HWP_SECURITY_MODULE_REQUIRED,
            "detail": type(e).__name__,
        }
    return {"ok": True, "module_name": name, "return_value": rv}


# ── 핸들 관리 ──────────────────────────────────────────────────────
def open_hwp_app(visible: bool = True) -> Tuple[Optional[Any], Optional[str]]:
    """한글 Application COM 객체를 반환.

    - Visible 속성을 지원할 경우 적용 (HWP 버전에 따라 속성 위치가 다를 수
      있어 실패해도 무시).
    """
    win32com_mod, err = _try_import_win32com()
    if err or win32com_mod is None:
        return None, err or _err.HWP_COM_DISPATCH_FAILED
    try:
        app = win32com_mod.Dispatch(_HWP_PROGID)
    except Exception as e:  # noqa: BLE001
        logger.info("open_hwp_app Dispatch 실패: %s", type(e).__name__)
        return None, _err.HWP_APP_NOT_FOUND

    # HWP 는 Visible 속성을 직접 노출하지 않는 버전이 많다. 최대한
    # best-effort 로 설정하고 실패는 무시.
    try:
        xframe = getattr(app, "XHwpWindows", None)
        if xframe is not None:
            active = getattr(xframe, "Active_XHwpWindow", None)
            if active is not None:
                active.Visible = bool(visible)
    except Exception:  # noqa: BLE001
        pass
    try:
        # 일부 버전에서는 최상위에도 Visible 이 있을 수 있다.
        app.Visible = bool(visible)
    except Exception:  # noqa: BLE001
        pass
    return app, None


# ── 문서 열기 ──────────────────────────────────────────────────────
def open_document(
    app: Any, file_path: str,
) -> Optional[str]:
    """절대경로로 HWP/HWPX 문서를 연다.

    성공 시 ``None``, 실패 시 에러 코드 문자열을 반환한다.
    """
    if not isinstance(file_path, str) or not file_path.strip():
        return _err.FILE_PATH_REQUIRED
    try:
        p = Path(file_path).expanduser()
    except (OSError, ValueError):
        return _err.FILE_NOT_ALLOWED
    if not p.is_absolute():
        return _err.FILE_NOT_ALLOWED
    if not p.exists() or not p.is_file():
        return _err.FILE_NOT_FOUND
    try:
        # Open(Path, Format, Arg) — Format 비우면 확장자로 추론.
        app.Open(str(p), "", "")
    except Exception as e:  # noqa: BLE001
        logger.info("HWP Open 실패 (%s): %s", p, type(e).__name__)
        return _err.HWP_DOCUMENT_OPEN_FAILED
    return None


# ── 본문 읽기 ──────────────────────────────────────────────────────
def get_text_preview(app: Any, max_chars: int = 200) -> Tuple[Optional[str], Optional[str]]:
    """현재 문서 본문의 일부를 미리보기로 읽는다.

    전체 파싱보다 “문서 접근 가능” 증명을 우선한다. ``GetTextFile("TEXT", "")``
    가 실패하는 버전/문서도 있어 텍스트를 한 번 가져와 자르는 식으로만 처리.
    """
    if app is None:
        return None, _err.HWP_APP_NOT_FOUND
    try:
        text = app.GetTextFile("TEXT", "")
    except Exception as e:  # noqa: BLE001
        logger.info("GetTextFile 실패: %s", type(e).__name__)
        return None, _err.HWP_TEXT_READ_FAILED
    if text is None:
        return "", None
    try:
        text = str(text)
    except Exception:  # noqa: BLE001
        return None, _err.HWP_TEXT_READ_FAILED
    limit = max_chars if isinstance(max_chars, int) and max_chars > 0 else 200
    return text[:limit], None


# ── 본문 쓰기 ──────────────────────────────────────────────────────
def insert_text(
    app: Any,
    text: str,
    *,
    approval_token: Optional[str] = None,
    dry_run: bool = True,
    allow_write: bool = False,
) -> Optional[str]:
    """현재 커서 위치에 테스트 문자열을 삽입한다. 승인/dry-run 게이트 포함.

    기본 경로는 ``HAction("InsertText")`` + ``HParameterSet.HInsertText``.
    해당 경로가 실패하면 단순히 ``InsertText`` 메서드를 시도하는 폴백.
    """
    if app is None:
        return _err.HWP_APP_NOT_FOUND
    if not isinstance(text, str):
        return _err.HWP_TEXT_WRITE_FAILED
    if dry_run:
        logger.info("[HWP-DRY-RUN] insert_text would_write=True")
        return None
    approval_err = _require_approval_for_write("hwp.insert_text", approval_token, allow_write)
    if approval_err:
        return approval_err

    try:
        action = app.HAction
        pset = app.HParameterSet.HInsertText
        action.GetDefault("InsertText", pset.HSet)
        pset.Text = text
        action.Execute("InsertText", pset.HSet)
        return None
    except Exception as e:  # noqa: BLE001
        logger.info(
            "HAction InsertText 실패: %s — 폴백 시도", type(e).__name__,
        )

    try:
        app.InsertText(text)
        return None
    except Exception as e:  # noqa: BLE001
        logger.info("InsertText 폴백 실패: %s", type(e).__name__)
        return _err.HWP_TEXT_WRITE_FAILED


# ── 저장 / 종료 ────────────────────────────────────────────────────
def save_document_as(
    app: Any,
    output_path: str,
    *,
    overwrite: bool = False,
    approval_token: Optional[str] = None,
    dry_run: bool = True,
    allow_write: bool = False,
) -> Optional[str]:
    """다른 이름 저장. 절대경로 필수, 기본 overwrite 금지, 승인/dry-run 게이트 포함."""
    if app is None:
        return _err.HWP_APP_NOT_FOUND
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
        logger.info("[HWP-DRY-RUN] save_document_as path=%s would_write=True", output_path)
        return None
    approval_err = _require_approval_for_write("hwp.save_document_as", approval_token, allow_write)
    if approval_err:
        return approval_err
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return _err.OUTPUT_PATH_NOT_ALLOWED

    # 포맷 — 확장자에서 유추 (HWP / HWPX). 빈 문자열이면 내부적으로 추론하는
    # 버전도 있지만, 명시하는 편이 안전.
    suffix = p.suffix.lower().lstrip(".")
    fmt = suffix.upper() if suffix in ("hwp", "hwpx") else ""

    try:
        app.SaveAs(str(p), fmt, "")
    except Exception as e:  # noqa: BLE001
        logger.info(
            "HWP SaveAs 실패 (%s, fmt=%s): %s", p, fmt, type(e).__name__,
        )
        return _err.HWP_DOCUMENT_SAVE_FAILED
    return None


def close_document(app: Any, save_changes: bool = False) -> None:
    """현재 활성 문서를 닫는다. 어떤 실패도 삼켜 정리 경로를 보장."""
    if app is None:
        return
    try:
        # 가장 널리 쓰이는 경로.
        xdocs = getattr(app, "XHwpDocuments", None)
        if xdocs is not None:
            active = getattr(xdocs, "Active_XHwpDocument", None)
            if active is not None:
                active.Close(isDirty=bool(save_changes))
                return
    except Exception as e:  # noqa: BLE001
        logger.info("XHwpDocuments Close 실패: %s", type(e).__name__)

    try:
        # 일부 버전의 단순 Clear/Close.
        close = getattr(app, "Clear", None) or getattr(app, "Close", None)
        if close is not None:
            close(1 if save_changes else 3)
    except Exception as e:  # noqa: BLE001
        logger.info("HWP Clear/Close 폴백 실패: %s", type(e).__name__)


def quit_hwp(app: Any) -> None:
    """HWP 프로세스를 종료. 정리 경로에서 호출되므로 예외를 삼킨다."""
    if app is None:
        return
    try:
        app.Quit()
    except Exception as e:  # noqa: BLE001
        logger.info("Quit 실패 (정리 단계): %s", type(e).__name__)


# ── 통합 POC ───────────────────────────────────────────────────────
def run_basic_poc(
    file_path: str,
    *,
    visible: bool = True,
    save_as: Optional[str] = None,
    register_module: bool = False,
    module_name: Optional[str] = None,
    write_text: str = "POC_OK",
    preview_chars: int = 200,
    dry_run: bool = True,
    approval_token: Optional[str] = None,
    allow_write: bool = False,
) -> dict:
    """한글 실행 → (보안모듈 등록) → 열기 → 읽기 → 쓰기 → 저장 → 종료.

    - dry_run=True (기본): COM 객체 미생성, planned_actions만 반환
    - approval_token 필수 (쓰기용)
    - allow_write=True만 실제 쓰기 허용

    모든 단계의 진행 상황을 ``result`` dict 에 순차 기록해 실패 지점을
    분리 가능한 진단 로그로 반환한다.
    """
    result: dict = {
        "ok": False,
        "file_path": file_path,
        "visible": bool(visible),
        "save_as": save_as,
        "register_module": bool(register_module),
        "module_name": module_name,
        "dry_run": bool(dry_run),
        "allow_write": bool(allow_write),
        "planned_actions": [],
        "dispatched": False,
        "security_module": None,
        "document_opened": False,
        "text_preview": None,
        "written_text": None,
        "saved": False,
        "closed": False,
        "quit": False,
        "error": None,
    }

    if dry_run:
        result["planned_actions"] = [
            {"action": "hwp.open", "file_path": file_path},
            {"action": "hwp.get_text_preview", "requires_approval": False},
            {"action": "hwp.insert_text", "requires_approval": True},
            {"action": "hwp.save_as" if save_as else "hwp.save", "requires_approval": True},
        ]
        logger.info("[HWP-DRY-RUN] planned_actions=%d", len(result["planned_actions"]))
        result["ok"] = True
        return result

    avail = is_hwp_available()
    if not avail.get("ok"):
        result["error"] = avail.get("error") or _err.HWP_COM_NOT_SUPPORTED
        return result

    app, err = open_hwp_app(visible=visible)
    if err or app is None:
        result["error"] = err or _err.HWP_APP_NOT_FOUND
        return result
    result["dispatched"] = True

    try:
        if register_module:
            reg = register_file_path_check_module(app, module_name=module_name)
            result["security_module"] = reg
            # 보안 모듈 등록 실패해도 문서 열기는 시도한다(다이얼로그가
            # 뜨는 환경이라면 Open 자체가 실패할 것이며, 그 실패 원인이
            # 여기 기록된 security_module 과 조합되어 진단 단서가 된다).

        err = open_document(app, file_path)
        if err:
            result["error"] = err
            return result
        result["document_opened"] = True

        preview, err = get_text_preview(app, max_chars=preview_chars)
        if err:
            # 미리보기 실패는 치명 실패로 다루지 않고 기록만 남긴다.
            result["text_preview"] = None
            result["error"] = err
            return result
        result["text_preview"] = preview

        if isinstance(write_text, str) and write_text:
            err = insert_text(
                app, write_text,
                approval_token=approval_token, dry_run=False, allow_write=allow_write,
            )
            if err:
                result["error"] = err
                return result
            result["written_text"] = write_text

        if save_as:
            err = save_document_as(
                app, save_as,
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
        close_document(app, save_changes=False)
        result["closed"] = True
        quit_hwp(app)
        result["quit"] = True


__all__ = [
    "is_hwp_available",
    "register_file_path_check_module",
    "open_hwp_app",
    "open_document",
    "get_text_preview",
    "insert_text",
    "save_document_as",
    "close_document",
    "quit_hwp",
    "run_basic_poc",
]
