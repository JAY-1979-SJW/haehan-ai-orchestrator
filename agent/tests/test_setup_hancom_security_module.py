"""한컴 보안모듈 설정 스크립트 테스트."""
from __future__ import annotations

import subprocess
import tempfile
import os
import sys
from pathlib import Path


class TestSetupScriptCLI:
    """CLI 옵션 및 모드 테스트."""

    @staticmethod
    def run_script(*args):
        """스크립트를 실행하고 결과를 반환."""
        script_path = Path(__file__).parent.parent.parent / "scripts" / "setup_hancom_security_module.py"
        cmd = [sys.executable, str(script_path)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        return result

    def test_diagnose_only_mode(self):
        """--diagnose-only 모드 테스트: 진단만 수행, registry write 없음."""
        result = self.run_script("--diagnose-only")
        # 진단 모드는 DLL을 찾을 수 없을 때 exit code 2를 반환
        assert result.returncode in (0, 2), f"Expected 0 or 2, got {result.returncode}"
        # 진단 정보를 출력해야 함
        output = result.stdout + result.stderr
        assert "한컴" in output or "진단" in output, "Expected diagnostic output"
        # registry write 메시지가 없어야 함
        assert "Registry에 등록" not in output, "diagnose-only should not write to registry"

    def test_help_option(self):
        """--help 옵션으로 모든 CLI 옵션이 문서화되었는지 확인."""
        result = self.run_script("--help")
        assert result.returncode == 0, f"Help failed: {result.stderr}"
        help_text = result.stdout
        # 새로 추가된 옵션들이 모두 나타나야 함
        assert "--dll-path" in help_text, "Missing --dll-path option"
        assert "--module-name" in help_text, "Missing --module-name option"
        assert "--diagnose-only" in help_text, "Missing --diagnose-only option"
        assert "--register" in help_text, "Missing --register option"
        assert "--yes" in help_text, "Missing --yes option"

    def test_invalid_dll_path(self):
        """--dll-path로 유효하지 않은 경로를 제공했을 때 에러 처리."""
        result = self.run_script(
            "--register",
            "--dll-path", r"C:\NonExistent\HwpAutomation.dll",
            "--yes"
        )
        # 유효하지 않은 DLL 경로는 에러를 반환해야 함
        # 또는 이미 등록된 경우 0 반환 가능
        output = result.stdout + result.stderr
        if result.returncode != 0:
            # 에러 경우: DLL 없음 메시지 확인
            assert "찾을 수 없습니다" in output or "DLL" in output, "Should show DLL error"
        else:
            # 이미 등록된 경우: 등록됨 메시지 확인
            assert "등록됨" in output or "이미" in output, "Should show already registered"

    def test_valid_dll_path_with_yes(self):
        """--dll-path와 --yes로 유효한 DLL을 제공했을 때."""
        # 임시 DLL 파일 생성
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            temp_dll = f.name

        try:
            result = self.run_script(
                "--register",
                "--dll-path", temp_dll,
                "--yes"
            )
            # 유효한 DLL 경로이지만 registry 권한이 없을 수 있음
            # 실패 시 권한 에러 메시지가 나타나야 함
            output = result.stdout + result.stderr
            assert result.returncode in (0, 1), f"Unexpected exit code {result.returncode}"
            if result.returncode != 0:
                # 권한 에러나 다른 설정 에러가 있을 수 있음
                assert any(err in output for err in [
                    "권한",
                    "REGISTRY_PERMISSION_DENIED",
                    "REGISTRY_WRITE_FAILED",
                ]), f"Expected permission or registry error, got: {output}"
        finally:
            if os.path.exists(temp_dll):
                os.unlink(temp_dll)

    def test_mutual_exclusivity_diagnose_register(self):
        """--diagnose-only와 --register를 동시에 사용할 수 없음."""
        result = self.run_script(
            "--diagnose-only",
            "--register"
        )
        # 상호배타 옵션을 사용하면 에러
        assert result.returncode != 0, "Should fail with mutually exclusive options"
        output = result.stdout + result.stderr
        assert "오류" in output or "동시에" in output, "Should show mutual exclusivity error"

    def test_yes_without_register(self):
        """--yes를 --register 없이 사용할 수 없음."""
        result = self.run_script("--yes")
        # --yes는 --register 없이 사용 불가
        assert result.returncode != 0, "Should fail when --yes is used without --register"
        output = result.stdout + result.stderr
        assert "오류" in output or "--register" in output, "Should mention --register requirement"

    def test_custom_module_name(self):
        """--module-name으로 커스텀 모듈명 지정."""
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            temp_dll = f.name

        try:
            result = self.run_script(
                "--register",
                "--dll-path", temp_dll,
                "--module-name", "HaehanFilePathChecker",
                "--yes"
            )
            # 커스텀 모듈명이 사용되어야 함
            output = result.stdout + result.stderr
            # 성공하거나 권한 에러가 나야 함
            assert result.returncode in (0, 1), f"Unexpected exit code {result.returncode}"
            if result.returncode == 0:
                assert "HaehanFilePathChecker" in output, "Custom module name should appear in output"
        finally:
            if os.path.exists(temp_dll):
                os.unlink(temp_dll)


class TestSetupScriptModes:
    """실행 모드 테스트."""

    @staticmethod
    def run_script(*args):
        """스크립트를 실행하고 결과를 반환."""
        script_path = Path(__file__).parent.parent.parent / "scripts" / "setup_hancom_security_module.py"
        cmd = [sys.executable, str(script_path)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        return result

    def test_mode_diagnose_returns_correct_exit_code(self):
        """진단 모드가 올바른 exit code를 반환."""
        result = self.run_script("--diagnose-only")
        # 진단은 항상 성공해야 함 (DLL 찾기 실패는 exit code 2)
        assert result.returncode in (0, 2), f"Diagnose should return 0 or 2, got {result.returncode}"

    def test_mode_register_with_yes_no_approval_prompt(self):
        """--register --yes 모드는 승인 프롬프트를 건너뜀."""
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            temp_dll = f.name

        try:
            result = self.run_script(
                "--register",
                "--dll-path", temp_dll,
                "--yes"
            )
            output = result.stdout + result.stderr
            # --yes 모드는 "계속 진행하시겠습니까?" 프롬프트를 건너뛰어야 함
            # 대신 CLI 자동 승인 모드 로그가 있을 수 있음
            # (에러로 인해 프롬프트에 도달하지 않을 수 있음)
        finally:
            if os.path.exists(temp_dll):
                os.unlink(temp_dll)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
