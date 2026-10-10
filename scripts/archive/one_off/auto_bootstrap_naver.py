"""자동 감지 및 초기화 실행 — 오류 시 자동 해결."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_bootstrap():
    """Bootstrap 실행."""
    print("\n▶ Bootstrap 시작...\n")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.archive.one_off.browser_agent_bootstrap"],
            cwd=REPO_ROOT,
            capture_output=False,
            text=True,
            timeout=30,
            encoding="utf-8",
        )

        if result.returncode != 0:
            print("\n⚠️  Bootstrap 부분 실패. 수정 중...\n")
            return fix_and_retry()

        print("\n✓ Bootstrap 완료!\n")
        return True

    except subprocess.TimeoutExpired:
        print("\n⚠️  시간 초과. 재시도 중...\n")
        return False
    except Exception as e:  # noqa: BLE001 - 네이버 부트스트랩 1회성 스크립트(archive) -- 실행 오류 시 재시도 로직 호출, 수정 실패는 False 반환(자동 승인/우회 없음)
        print(f"\n⚠️  오류: {e}\n")
        return fix_and_retry()


def fix_and_retry():
    """오류 수정 및 재시도."""
    print("🔧 자동 수정 중...\n")

    try:
        # Mixin 파일들이 존재하는지 확인
        mixins_dir = REPO_ROOT / "ai_orchestrator" / "local_agent" / "browser" / "mixins"
        required_files = ["mail_mixin.py", "calendar_mixin.py", "mybox_mixin.py"]

        for fname in required_files:
            fpath = mixins_dir / fname
            if not fpath.exists():
                print(f"  생성 중: {fname}")
                # Bootstrap 함수를 직접 호출하는 대신, 파일을 직접 생성
                if fname == "mail_mixin.py":
                    from scripts.archive.one_off.browser_agent_bootstrap import create_mail_mixin

                    create_mail_mixin()
                elif fname == "calendar_mixin.py":
                    from scripts.archive.one_off.browser_agent_bootstrap import create_calendar_mixin

                    create_calendar_mixin()
                elif fname == "mybox_mixin.py":
                    from scripts.archive.one_off.browser_agent_bootstrap import create_mybox_mixin

                    create_mybox_mixin()

        # __init__.py 업데이트
        print("  업데이트 중: __init__.py")
        from scripts.archive.one_off.browser_agent_bootstrap import update_mixins_init

        update_mixins_init()

        # agent.py 업데이트
        print("  업데이트 중: agent.py")
        from scripts.archive.one_off.browser_agent_bootstrap import update_browser_agent

        update_browser_agent()

        # 검증
        print("  검증 중...")
        from scripts.archive.one_off.browser_agent_bootstrap import verify_import

        if verify_import():
            print("\n✓ 수정 완료!\n")
            return True

    except Exception as e:  # noqa: BLE001 - 네이버 부트스트랩 1회성 스크립트(archive) -- 실행 오류 시 재시도 로직 호출, 수정 실패는 False 반환(자동 승인/우회 없음)
        print(f"  ✗ 수정 실패: {e}\n")

    return False


def main():
    """메인 진입점."""
    print("\n" + "=" * 70)
    print("  [자동화] 네이버 서비스 감지 및 초기화")
    print("=" * 70)

    if run_bootstrap():
        print("=" * 70)
        print("  [완료] 모든 자동화 완료!")
        print("=" * 70 + "\n")
        return 0
    else:
        print("=" * 70)
        print("  [오류] 자동화 실패. 수동 개입 필요.")
        print("=" * 70 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
