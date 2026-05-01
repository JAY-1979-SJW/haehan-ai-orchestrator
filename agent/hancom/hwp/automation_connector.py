"""한컴 HwpObject 자동화 커넥터.

HwpObject 생성, COM 가용성 확인, 저수준 파일 조작.

제약:
- 원본 HWP는 read-only로만 열기
- SaveAs만 사용 (원본 저장 금지)
- Visible 제어 (UI 팝업 최소화)
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 지원하는 HwpObject COM 클래스들 (우선순위 순서)
_HWPOBJECT_CLASSES = [
    "HWPFrame.HwpObject",        # 최신 한컴
    "HWPFrame.HwpObject.1",      # 버전명시
    "HWPFrame.HwpObject.2",
    "HwpObject.HwpObject",       # 호환성
    "HwpAutomationApp2.HwpAutomation",  # 자동화
    "HwpAutomationApp2.HwpAutomation.1",
]


def _check_registry_installed() -> bool:
    """Windows 레지스트리에서 한컴 설치 여부 확인."""
    try:
        import winreg

        # HKLM\SOFTWARE\Classes\HWPFrame.HwpObject 확인
        for cls in _HWPOBJECT_CLASSES:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"SOFTWARE\\Classes\\{cls}"):
                    logger.debug(f"한컴 레지스트리 발견: {cls}")
                    return True
            except FileNotFoundError:
                continue

        return False
    except Exception as e:
        logger.debug(f"레지스트리 확인 실패: {type(e).__name__}")
        return False


def _get_working_hwpobject_class() -> Optional[str]:
    """작동하는 HwpObject COM 클래스를 찾는다."""
    try:
        import win32com.client as win32

        for cls in _HWPOBJECT_CLASSES:
            try:
                hwp = win32.Dispatch(cls)
                try:
                    hwp.Quit()
                except Exception:
                    pass
                logger.info(f"작동하는 HwpObject 클래스: {cls}")
                return cls
            except Exception:
                continue

        return None
    except ImportError:
        return None


def check_hancom_available() -> Tuple[bool, Optional[str]]:
    """한컴 COM 객체가 사용 가능한지 확인.

    레지스트리 + COM 직접 생성 시도로 설치 여부 확인.

    Returns:
        (가용성, error_or_None)
    """
    try:
        import win32com.client as win32

        # 1단계: 레지스트리 확인 (빠른 설치 여부 판단)
        if not _check_registry_installed():
            logger.error("한컴이 Windows 레지스트리에 등록되지 않음")
            return False, "HANCOM_NOT_INSTALLED"

        # 2단계: 작동하는 COM 클래스 찾기
        working_class = _get_working_hwpobject_class()
        if not working_class:
            logger.error("작동하는 HwpObject COM 클래스를 찾을 수 없음")
            return False, "HANCOM_NOT_INSTALLED"

        # 3단계: 실제 COM 객체 생성 시도
        hwp = win32.Dispatch(working_class)
        try:
            # 기본 속성 확인
            if hasattr(hwp, "Version"):
                version = hwp.Version
                logger.info(f"한컴 COM 사용 가능: {working_class}, version={version}")
                return True, None
            elif hasattr(hwp, "Visible"):
                logger.info(f"한컴 COM 사용 가능: {working_class}")
                return True, None
            else:
                return False, "HANCOM_OBJECT_INCOMPLETE"
        finally:
            try:
                hwp.Quit()
            except Exception:
                pass

    except ImportError:
        logger.error("win32com not available")
        return False, "WIN32COM_NOT_AVAILABLE"
    except Exception as e:
        logger.error(f"한컴 COM 확인 실패: {type(e).__name__}")
        return False, "HANCOM_NOT_INSTALLED"


def create_hwp_object(visible: bool = False) -> Tuple[Optional[object], Optional[str]]:
    """HwpObject를 생성한다.

    Args:
        visible: UI 표시 여부 (기본값: False - 숨김)

    Returns:
        (hwp_object, error_or_None)
    """
    try:
        import win32com.client as win32

        # 작동하는 클래스 찾기
        working_class = _get_working_hwpobject_class()
        if not working_class:
            logger.error("작동하는 HwpObject COM 클래스를 찾을 수 없음")
            return None, "HANCOM_NOT_INSTALLED"

        hwp = win32.Dispatch(working_class)

        # Visible 제어 (보안 팝업 최소화)
        try:
            hwp.Visible = visible
        except Exception as e:
            logger.warning(f"Visible 제어 실패: {type(e).__name__}")

        logger.info(f"HwpObject 생성됨: {working_class} (visible={visible})")
        return hwp, None

    except ImportError:
        logger.error("win32com not available")
        return None, "WIN32COM_NOT_AVAILABLE"
    except Exception as e:
        logger.error(f"HwpObject 생성 실패: {type(e).__name__}")
        return None, "HANCOM_NOT_INSTALLED"


def open_hwp_file(
    hwp,
    file_path: str,
    read_only: bool = True,
) -> Tuple[bool, Optional[str]]:
    """HWP 파일을 연다.

    Args:
        hwp: HwpObject 인스턴스
        file_path: 열 파일 경로
        read_only: 읽기 전용 여부 (기본값: True)

    Returns:
        (성공여부, error_or_None)
    """
    if hwp is None:
        return False, "HWPOBJECT_NOT_INITIALIZED"

    try:
        # HwpObject.Open(filename, template, encoding, ...)
        # EditMode: 0=view, 1=edit (read_only=True이면 view)
        edit_mode = 0 if read_only else 1

        hwp.Open(file_path, "", "", edit_mode)  # type: ignore
        logger.info(f"Opened: {file_path} (read_only={read_only})")
        return True, None

    except Exception as e:
        logger.error(f"Open failed: {type(e).__name__}")
        return False, "FILE_OPEN_FAILED"


def close_hwp_file(hwp, save_changes: bool = False) -> Tuple[bool, Optional[str]]:
    """HWP 파일을 닫는다.

    Args:
        hwp: HwpObject 인스턴스
        save_changes: 변경사항 저장 여부 (기본값: False)

    Returns:
        (성공여부, error_or_None)
    """
    if hwp is None:
        return True, None

    try:
        hwp.Close(save_changes)  # type: ignore
        logger.info(f"Closed (save_changes={save_changes})")
        return True, None

    except Exception as e:
        logger.error(f"Close failed: {type(e).__name__}")
        return False, "FILE_CLOSE_FAILED"


def save_hwp_as(
    hwp,
    output_path: str,
    file_format: str = "HWPX",
) -> Tuple[bool, Optional[str]]:
    """HWP 파일을 다른 형식으로 저장한다 (SaveAs).

    Args:
        hwp: HwpObject 인스턴스
        output_path: 출력 경로
        file_format: 저장 형식 ("HWP", "HWPX", "ODP", "DOCX" 등)

    Returns:
        (성공여부, error_or_None)

    주의:
    - SaveAs는 현재 열린 파일의 경로를 변경하므로 주의
    - 원본 보호: 반드시 read-only로 열어야 함
    """
    if hwp is None:
        return False, "HWPOBJECT_NOT_INITIALIZED"

    try:
        # FileSaveAs_S 사용 (한컴 자동화 공식 방식)
        # SaveAs(filename, format)
        hwp.FileSaveAs_S(output_path, file_format)  # type: ignore
        logger.info(f"SaveAs: {output_path} ({file_format})")
        return True, None

    except AttributeError:
        # FileSaveAs_S가 없으면 SaveAs 시도
        try:
            hwp.SaveAs(output_path, file_format)  # type: ignore
            logger.info(f"SaveAs: {output_path} ({file_format})")
            return True, None
        except Exception as e:
            logger.error(f"SaveAs failed: {type(e).__name__}")
            return False, "FILE_SAVE_AS_FAILED"

    except Exception as e:
        logger.error(f"FileSaveAs_S failed: {type(e).__name__}")
        return False, "FILE_SAVE_AS_FAILED"


def quit_hwp(hwp) -> Tuple[bool, Optional[str]]:
    """HwpObject를 종료한다.

    Args:
        hwp: HwpObject 인스턴스

    Returns:
        (성공여부, error_or_None)
    """
    if hwp is None:
        return True, None

    try:
        hwp.Quit()  # type: ignore
        logger.info("HwpObject quit")
        return True, None

    except Exception as e:
        logger.error(f"Quit failed: {type(e).__name__}")
        return False, "QUIT_FAILED"
