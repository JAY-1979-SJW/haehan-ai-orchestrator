#!/usr/bin/env python
"""한컴 로컬 설치/COM/보안모듈 진단 스크립트.

사용법:
  python scripts/diagnose_hancom_installation.py

한컴 설치, COM 등록, 보안모듈 상태를 read-only로 진단합니다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.hancom.discovery.diagnostics import diagnose_hancom_installation, print_diagnosis_report


def main():
    """한컴 설치 상태 진단."""
    print()
    print("=" * 70)
    print("한컴 로컬 설치 진단")
    print("=" * 70)
    print()

    result = diagnose_hancom_installation()
    print_diagnosis_report(result)

    # 최종 판정에 따라 exit code 반환
    if result["installed"]:
        if result["security_module"]["registered"]:
            print("✅ 한컴이 완전히 설치되었으며 보안모듈도 등록되어 있습니다.")
            print("   HWP → HWPX 변환 가능합니다.")
            return 0
        else:
            print("⚠️  한컴이 설치되었지만 보안모듈이 미등록입니다.")
            print("   `python scripts/setup_hancom_security_module.py` 실행으로 보안모듈을 등록하세요.")
            return 1
    else:
        print("❌ 한컴이 설치되지 않았습니다.")
        print("   https://developers.hancom.com/ 에서 한컴을 설치하세요.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
