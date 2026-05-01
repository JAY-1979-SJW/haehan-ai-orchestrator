#!/usr/bin/env python
"""한컴 보안모듈 자동 등록 스크립트.

사용법:
  python scripts/setup_hancom_security_module.py

또는 명시적으로 DLL 경로 지정:
  python scripts/setup_hancom_security_module.py --dll-path "C:\\path\\to\\HwpAutomation.dll"

요구사항:
  - 관리자 권한 (registry write)
  - 한컴 설치됨
  - win32 모듈
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 부모 디렉토리를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.hancom.hwp import security_module
from agent.hancom.discovery import diagnostics, dll_resolver

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """한컴 보안모듈 자동 등록."""
    parser = argparse.ArgumentParser(
        description="한컴 보안모듈을 자동으로 등록합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  # 자동 탐색으로 등록
  python setup_hancom_security_module.py

  # 명시적 DLL 경로로 등록
  python setup_hancom_security_module.py --dll-path "C:\\Program Files\\HNC\\한글2014\\Bin\\HwpAutomation.dll"

  # 모듈명 지정 (기본값: FilePathCheckerModuleExample)
  python setup_hancom_security_module.py --module-name "MySecurityModule"
        """,
    )

    parser.add_argument(
        "--dll-path",
        help="한컴 DLL 파일 경로 (기본값: 자동 탐색)",
        default=None,
    )

    parser.add_argument(
        "--module-name",
        help=f"보안모듈 이름 (기본값: {security_module.DEFAULT_SECURITY_MODULE_NAME})",
        default=None,
    )

    parser.add_argument(
        "--verify",
        action="store_true",
        help="등록 후 확인만 하고 등록하지 않음",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("한컴 보안모듈 자동 등록")
    print("=" * 70)
    print()

    # 1단계: 현재 등록 상태 확인
    print("[1단계] 현재 보안모듈 상태 확인...")
    current_status = security_module.get_security_module_details(args.module_name)
    print(f"  등록 여부: {'✅ 등록됨' if current_status['registered'] else '❌ 미등록'}")
    if current_status["registered"]:
        print(f"  모듈명: {current_status['module_name']}")
        print(f"  DLL 경로: {current_status['dll_path']}")
        print(f"  DLL 존재: {'✅' if current_status['dll_exists'] else '❌'}")
        print()
        print("이미 보안모듈이 등록되어 있습니다.")
        return 0

    print()

    # 1-2단계: 한컴 설치 상태 진단 (discovery)
    print("[1-2단계] 한컴 설치 상태 진단...")
    diag = diagnostics.diagnose_hancom_installation()
    print(f"  설치 상태: {diag['summary']}")
    if not diag["installed"]:
        print()
        print("❌ 한컴이 설치되지 않았습니다.")
        print("   https://developers.hancom.com/ 에서 한컴을 설치하세요.")
        return 2

    print()

    # 1-3단계: DLL 경로 해석
    print("[1-3단계] DLL 경로 해석...")
    resolved_dll, status_msg = dll_resolver.resolve_dll_path(args.dll_path)
    candidates = dll_resolver.get_dll_candidates()

    print(f"  {status_msg}")
    if resolved_dll:
        print(f"  ✓ 선택된 경로: {resolved_dll}")
    else:
        print(f"  ✗ 유효한 DLL을 찾을 수 없습니다")
        if candidates:
            print()
            print("  [DLL 후보]")
            for dll_path, status in candidates.items():
                status_icon = "✓" if "valid" in status else "✗"
                print(f"    {status_icon} {dll_path}")

    print()

    # DLL이 없으면 중단
    if not resolved_dll:
        print()
        print("❌ DLL을 찾을 수 없습니다.")
        print()
        print("💡 해결책:")
        print("   1. 한컴 설치를 확인하세요")
        print("   2. 또는 --dll-path로 경로를 명시 지정하세요")
        print()
        print("예:")
        print('   python scripts/setup_hancom_security_module.py --dll-path "C:\\Program Files\\HNC\\한글2014\\Bin\\HwpAutomation.dll"')
        print()
        return 2

    print()

    # 2단계: 사용자 승인 확인
    if not args.verify:
        print("[2단계] 사용자 승인 확인...")
        print()
        print(f"다음 DLL을 등록하시겠습니까?")
        print(f"  {resolved_dll}")
        print()
        print("보안모듈을 Registry에 등록합니다.")
        print("(이 작업은 관리자 권한이 필요할 수 있습니다.)")
        print()

        response = input("계속 진행하시겠습니까? (y/n): ").strip().lower()
        if response != "y":
            print("\n❌ 취소되었습니다.")
            return 1

    print()
    print("[3단계] 보안모듈 자동 등록 중...")
    print()

    # 등록 실행 (DLL 경로는 dll_resolver에서 확인한 경로 사용)
    result = security_module.setup_security_module_registry(
        module_name=args.module_name,
        dll_path=resolved_dll,
    )

    print(result["message"])
    print()

    if result["success"]:
        print("[4단계] 등록 확인...")
        verified = security_module.get_security_module_details(result["module_name"])
        if verified["registered"]:
            print(f"  ✅ 보안모듈 확인됨: {verified['module_name']}")
            print(f"  ✅ DLL 경로 확인됨: {verified['dll_path']}")
            print()
            print("=" * 70)
            print("✅ 보안모듈 등록이 완료되었습니다.")
            print("=" * 70)
            print()
            print("이제 HWP → HWPX 변환 시 보안팝업이 뜨지 않습니다.")
            print()
            return 0
        else:
            print("⚠️  등록 확인 중 문제가 발생했습니다.")
            print(f"   오류: {verified.get('error_code')}")
            return 1
    else:
        print("=" * 70)
        print("❌ 보안모듈 등록 실패")
        print("=" * 70)
        print()
        if result["error_code"] == "REGISTRY_PERMISSION_DENIED":
            print("💡 해결책: 관리자 권한으로 실행하세요.")
            print()
            print("방법 1: PowerShell (관리자)")
            print("  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser")
            print("  python scripts/setup_hancom_security_module.py")
            print()
            print("방법 2: 명령 프롬프트 (관리자)")
            print("  python scripts/setup_hancom_security_module.py")
            print()
        elif result["error_code"] == "DLL_PATH_NOT_FOUND":
            print("💡 해결책: 한컴이 설치된 경로를 찾아서 명시적으로 지정하세요.")
            print()
            print("예:")
            print('  python scripts/setup_hancom_security_module.py --dll-path "C:\\Program Files\\HNC\\한글2014\\Bin\\HwpAutomation.dll"')
            print()
        print(f"오류: {result['error_code']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
