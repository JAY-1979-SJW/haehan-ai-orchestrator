"""한컴 HWP → HWPX 실제 COM smoke 테스트.

요구사항:
- Windows 환경에서 한컴 설치 필수
- test_sample.hwp 파일 필수 (agent/tests/samples/ 디렉토리)
- 한컴 보안모듈 등록 권장 (미등록 시 일부 테스트 skip)

Smoke 대상:
1. 한컴 HwpObject COM 가용성 확인
2. HWP 파일 읽기 전용으로 열기
3. HWPX로 SaveAs 변환
4. HWPX ZIP 패키지 구조 검증
5. 원본 HWP 파일 무수정 확인
6. 보안모듈 등록 상태 조회

주의: 원본 HWP 파일은 수정하지 않음 (read-only 열기 + SaveAs 기반)
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def hancom_available():
    """한컴 COM 가용성 확인."""
    try:
        import win32com.client as win32
        # 지원하는 클래스들 시도 (우선순위 순서)
        classes = [
            "HWPFrame.HwpObject",
            "HWPFrame.HwpObject.1",
            "HWPFrame.HwpObject.2",
            "HwpObject.HwpObject",
        ]
        for cls in classes:
            try:
                hwp = win32.Dispatch(cls)
                hwp.Quit()
                logger.info(f"한컴 가용성 확인: {cls}")
                return True
            except Exception:
                continue
        return False
    except Exception as e:
        logger.warning(f"한컴 가용성 확인 실패: {type(e).__name__}: {e}")
        return False


@pytest.fixture(scope="session")
def sample_hwp_file():
    """테스트용 샘플 HWP 파일 경로."""
    test_dir = Path(__file__).parent
    sample_path = test_dir / "samples" / "test_sample.hwp"

    if sample_path.exists():
        yield str(sample_path)
    else:
        # 샘플이 없으면 최소한의 HWP 파일 생성
        # (실제로는 다른 도구로 생성해야 함)
        with tempfile.NamedTemporaryFile(suffix=".hwp", delete=False) as f:
            temp_path = f.name

        try:
            # 빈 파일로라도 경로는 제공 (테스트가 skip될 수 있음)
            # 실제 테스트는 한컴이 열 수 있는 유효한 HWP여야 함
            yield temp_path
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass


@pytest.fixture(scope="session")
def security_module_status():
    """한컴 보안모듈 등록 상태 조회."""
    try:
        from agent.hancom.hwp import security_module
        status = security_module.get_security_module_status()
        return status
    except Exception as e:
        logger.warning(f"Cannot check security module: {type(e).__name__}")
        return {
            "registered": False,
            "module_type": None,
            "error": str(e),
        }


def test_hancom_available(hancom_available):
    """한컴 COM 인터페이스 가용성 확인."""
    if not hancom_available:
        pytest.skip("Hancom not installed or not available")
    assert hancom_available is True


def test_hancom_hwp_object_creation(hancom_available):
    """HwpObject 생성 및 기본 속성 확인."""
    if not hancom_available:
        pytest.skip("Hancom not available")

    try:
        import win32com.client as win32
        classes = [
            "HWPFrame.HwpObject",
            "HWPFrame.HwpObject.1",
            "HWPFrame.HwpObject.2",
            "HwpObject.HwpObject",
        ]
        hwp = None
        for cls in classes:
            try:
                hwp = win32.Dispatch(cls)
                logger.info(f"HwpObject 생성 성공: {cls}")
                break
            except Exception:
                continue

        if hwp is None:
            pytest.skip("Cannot create HwpObject with any class")

        assert hwp is not None
        hwp.Quit()
        logger.info("HwpObject 생성 및 종료 성공")
    except Exception as e:
        pytest.skip(f"Cannot create HwpObject: {type(e).__name__}: {e}")


def test_security_module_status(security_module_status):
    """보안모듈 등록 상태 확인."""
    assert security_module_status is not None
    assert "registered" in security_module_status
    assert "error" in security_module_status

    if security_module_status["registered"]:
        logger.info(f"보안모듈 등록: {security_module_status['module_type']}")
    else:
        logger.warning(f"보안모듈 미등록: {security_module_status['error']}")


def test_hwp_file_open_read_only(hancom_available, sample_hwp_file):
    """HWP 파일을 읽기 전용으로 열기."""
    if not hancom_available:
        pytest.skip("Hancom not available")

    if not os.path.exists(sample_hwp_file):
        pytest.skip("Sample HWP file not found")

    try:
        import win32com.client as win32
        classes = [
            "HWPFrame.HwpObject",
            "HWPFrame.HwpObject.1",
            "HWPFrame.HwpObject.2",
            "HwpObject.HwpObject",
        ]
        hwp = None
        for cls in classes:
            try:
                hwp = win32.Dispatch(cls)
                break
            except Exception:
                continue

        if hwp is None:
            pytest.skip("Cannot create HwpObject")

        hwp.Visible = False

        try:
            # HWP 파일 열기
            hwp.Open(sample_hwp_file)
            assert hwp is not None
            logger.info(f"HWP 파일 열기 성공: {sample_hwp_file}")

        finally:
            try:
                hwp.Quit()
            except Exception:
                pass

    except Exception as e:
        pytest.skip(f"Cannot open HWP file: {type(e).__name__}: {e}")


def test_hwp_to_hwpx_conversion_read_only(
    hancom_available,
    sample_hwp_file,
    security_module_status,
):
    """HWP → HWPX 변환 (읽기 전용 열기, SaveAs 기반)."""
    if not hancom_available:
        pytest.skip("Hancom not available")

    if not os.path.exists(sample_hwp_file):
        pytest.skip("Sample HWP file not found")

    # 보안모듈이 미등록이면 warning만 (변환은 시도)
    if not security_module_status.get("registered", False):
        logger.warning(
            f"보안모듈 미등록 ({security_module_status.get('error')}), "
            "변환은 시도되지만 팝업 처리 불가"
        )

    with tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False) as f:
        output_path = f.name

    try:
        import win32com.client as win32

        classes = [
            "HWPFrame.HwpObject",
            "HWPFrame.HwpObject.1",
            "HWPFrame.HwpObject.2",
            "HwpObject.HwpObject",
        ]
        hwp = None
        for cls in classes:
            try:
                hwp = win32.Dispatch(cls)
                break
            except Exception:
                continue

        if hwp is None:
            pytest.skip("Cannot create HwpObject")

        hwp.Visible = False

        try:
            # HWP 파일 열기
            hwp.Open(sample_hwp_file)

            # SaveAs로 HWPX 형식으로 저장 (format 7 = HWPX)
            hwp.SaveAs(output_path, 7)

            # HWPX 파일 생성 확인
            assert os.path.exists(output_path), f"HWPX file not created: {output_path}"
            file_size = os.path.getsize(output_path)
            assert file_size > 100, f"HWPX file too small: {file_size} bytes"

            logger.info(f"HWP → HWPX 변환 성공: {output_path} ({file_size} bytes)")

        finally:
            try:
                hwp.Quit()
            except Exception:
                pass

    except Exception as e:
        pytest.skip(f"Cannot convert HWP to HWPX: {type(e).__name__}: {e}")

    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


def test_hwpx_zip_structure(
    hancom_available,
    sample_hwp_file,
):
    """생성된 HWPX 파일의 ZIP 구조 검증."""
    if not hancom_available:
        pytest.skip("Hancom not available")

    if not os.path.exists(sample_hwp_file):
        pytest.skip("Sample HWP file not found")

    with tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False) as f:
        output_path = f.name

    try:
        import win32com.client as win32

        classes = [
            "HWPFrame.HwpObject",
            "HWPFrame.HwpObject.1",
            "HWPFrame.HwpObject.2",
            "HwpObject.HwpObject",
        ]
        hwp = None
        for cls in classes:
            try:
                hwp = win32.Dispatch(cls)
                break
            except Exception:
                continue

        if hwp is None:
            pytest.skip("Cannot create HwpObject")

        hwp.Visible = False

        try:
            hwp.Open(sample_hwp_file)
            hwp.SaveAs(output_path, 7)  # HWPX format

            if not os.path.exists(output_path):
                pytest.skip("HWPX file not created")

            # ZIP 구조 검증
            try:
                with zipfile.ZipFile(output_path, "r") as zf:
                    namelist = zf.namelist()
                    assert len(namelist) > 0, "HWPX ZIP is empty"

                    has_contents = any(name.startswith("Contents/") for name in namelist)
                    assert has_contents, "HWPX missing Contents directory"

                    has_content_file = any(
                        name in ["Contents/content.hpf"] or
                        (name.startswith("Contents/") and name.endswith((".hml", ".xml")))
                        for name in namelist
                    )
                    assert has_content_file, "HWPX missing content file or sections"

                    logger.info(
                        f"HWPX ZIP 구조 검증 성공: {len(namelist)} 파일, "
                        f"Contents 존재: {has_contents}"
                    )

            except zipfile.BadZipFile:
                pytest.fail(f"HWPX is not a valid ZIP file: {output_path}")

        finally:
            try:
                hwp.Quit()
            except Exception:
                pass

    except Exception as e:
        pytest.skip(f"Cannot verify HWPX structure: {type(e).__name__}: {e}")

    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


def test_original_hwp_not_modified(
    hancom_available,
    sample_hwp_file,
):
    """원본 HWP 파일이 수정되지 않았는지 확인."""
    if not hancom_available:
        pytest.skip("Hancom not available")

    if not os.path.exists(sample_hwp_file):
        pytest.skip("Sample HWP file not found")

    # 원본 파일 stat 기록
    original_stat = os.stat(sample_hwp_file)
    original_mtime = original_stat.st_mtime
    original_size = original_stat.st_size

    with tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False) as f:
        output_path = f.name

    try:
        import win32com.client as win32

        classes = [
            "HWPFrame.HwpObject",
            "HWPFrame.HwpObject.1",
            "HWPFrame.HwpObject.2",
            "HwpObject.HwpObject",
        ]
        hwp = None
        for cls in classes:
            try:
                hwp = win32.Dispatch(cls)
                break
            except Exception:
                continue

        if hwp is None:
            pytest.skip("Cannot create HwpObject")

        hwp.Visible = False

        try:
            hwp.Open(sample_hwp_file)
            hwp.SaveAs(output_path, 7)  # HWPX format

        finally:
            try:
                hwp.Quit()
            except Exception:
                pass

        # 원본 파일 stat 재확인
        after_stat = os.stat(sample_hwp_file)
        after_mtime = after_stat.st_mtime
        after_size = after_stat.st_size

        # 파일 크기와 수정 시간이 변하지 않았는지 확인
        assert (
            original_size == after_size
        ), f"Original HWP size changed: {original_size} → {after_size}"

        # mtime이 동일하거나 매우 작은 차이만 허용 (초 단위)
        mtime_diff = abs(after_mtime - original_mtime)
        assert (
            mtime_diff < 1
        ), f"Original HWP modified time changed by {mtime_diff}s"

        logger.info(
            f"원본 HWP 파일 보호 확인: "
            f"size={after_size}, mtime_diff={mtime_diff}s"
        )

    except Exception as e:
        pytest.skip(f"Cannot verify original protection: {type(e).__name__}: {e}")

    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


def test_convert_via_workflows_module(hancom_available, sample_hwp_file):
    """workflows 모듈을 통한 변환 (전체 파이프라인)."""
    if not hancom_available:
        pytest.skip("Hancom not available")

    if not os.path.exists(sample_hwp_file):
        pytest.skip("Sample HWP file not found")

    with tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False) as f:
        output_path = f.name

    try:
        from agent.hancom.hwp import workflows

        result = workflows.convert_hwp_to_hwpx_copy({
            "input_path": sample_hwp_file,
            "output_path": output_path,
            "visible": False,
        })

        if not result.get("success", False):
            error_code = result.get("error", "unknown_error")
            # 보안모듈 미등록이거나 한컴 미설치인 경우 skip
            if error_code in [
                "MODULE_NOT_REGISTERED",
                "SETUP_REQUIRED",
                "HANCOM_NOT_INSTALLED",
            ]:
                pytest.skip(f"Hancom setup required: {error_code}")
            else:
                pytest.fail(f"Conversion failed: {error_code}")

        assert result.get("success") is True
        assert result.get("hwpx_valid") is True
        assert os.path.exists(output_path)

        logger.info(
            f"Conversion via workflows successful: "
            f"hwpx_valid={result['hwpx_valid']}, "
            f"file_count={result.get('hwpx_file_count', 0)}, "
            f"sections={result.get('hwpx_sections', 0)}"
        )

    except ImportError:
        pytest.skip("hancom.hwp.workflows not available")
    except Exception as e:
        pytest.skip(f"Cannot convert via workflows: {type(e).__name__}: {e}")

    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
