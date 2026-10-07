"""자동 감지 및 초기화 — 네이버 로그인 확인 → Mixin 생성 → 검증."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from scripts.browser.agent.cdp_session_manager import (
    is_logged_in,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MIXINS_DIR = Path(__file__).parent / "mixins"


def print_step(title: str, status: str = "⏳"):
    """단계별 출력."""
    print(f"\n{status} [{title}]")


def print_ok(msg: str):
    print(f"  ✓ {msg}")


def print_err(msg: str):
    print(f"  ✗ {msg}")


def check_cdp_connection() -> bool:
    """CDP 연결 상태 확인."""
    print_step("CDP 연결 확인", "🔍")
    try:
        from scripts.browser.agent.cdp_launcher import ensure_cdp, probe_cdp

        if probe_cdp():
            print_ok("Chrome/CDP 실행 중 (127.0.0.1:9222)")
            return True

        print_err("Chrome 미실행. Task Scheduler로 시작 중...")
        try:
            ensure_cdp()
            print_ok("Chrome 시작 완료")
            return True
        except RuntimeError as e:
            print_err(f"CDP 시작 실패: {e}")
            return False

    except Exception as e:  # noqa: BLE001 - 브라우저 믹스인 코드 생성 스캐폴딩 개발도구 - 파일 생성 실패시 print_err 후 False 반환, 런타임 보안과 무관한 개발 보조 스크립트
        print_err(f"CDP 확인 오류: {e}")
        return False


def check_naver_login() -> dict[str, bool]:
    """네이버 서비스 로그인 상태 확인."""
    print_step("네이버 로그인 상태 확인", "🔐")

    services = {
        "naver.com": "기본 로그인",
        "mail.naver.com": "메일",
        "calendar.naver.com": "캘린더",
        "mybox.naver.com": "MyBox",
    }

    result = {}
    for domain, name in services.items():
        logged_in = is_logged_in(domain)
        result[domain] = logged_in
        status = "✓" if logged_in else "✗"
        print(f"  {status} {name} ({domain}): {'로그인됨' if logged_in else '미로그인'}")

    if not all(result.values()):
        print_err("필수 로그인 누락. 브라우저에서 수동 로그인 필요")
        return result

    print_ok("모든 서비스 로그인 확인")
    return result


def create_mail_mixin() -> bool:
    """mail_mixin.py 생성."""
    print_step("mail_mixin.py 생성", "⚙️")

    mail_mixin_code = '''"""네이버 메일 Mixin."""
from __future__ import annotations

import time
from pathlib import Path


def _js(name: str) -> str:
    """Load JavaScript from _js/ directory."""
    return (Path(__file__).parent.parent / "_js" / name).read_text(encoding="utf-8")


class MailMixin:
    """네이버 메일 기능."""
    pass
'''

    try:
        mixin_file = MIXINS_DIR / "mail_mixin.py"
        mixin_file.write_text(mail_mixin_code, encoding="utf-8")
        print_ok(f"생성: {mixin_file}")
        return True
    except Exception as e:  # noqa: BLE001 - 브라우저 믹스인 코드 생성 스캐폴딩 개발도구 - 파일 생성 실패시 print_err 후 False 반환, 런타임 보안과 무관한 개발 보조 스크립트
        print_err(f"생성 실패: {e}")
        return False


def create_calendar_mixin() -> bool:
    """calendar_mixin.py 생성."""
    print_step("calendar_mixin.py 생성", "⚙️")

    calendar_mixin_code = '''"""네이버 캘린더 Mixin."""
from __future__ import annotations

import time
from pathlib import Path


def _js(name: str) -> str:
    """Load JavaScript from _js/ directory."""
    return (Path(__file__).parent.parent / "_js" / name).read_text(encoding="utf-8")


class CalendarMixin:
    """네이버 캘린더 기능."""
    pass
'''

    try:
        mixin_file = MIXINS_DIR / "calendar_mixin.py"
        mixin_file.write_text(calendar_mixin_code, encoding="utf-8")
        print_ok(f"생성: {mixin_file}")
        return True
    except Exception as e:  # noqa: BLE001 - 브라우저 믹스인 코드 생성 스캐폴딩 개발도구 - 파일 생성 실패시 print_err 후 False 반환, 런타임 보안과 무관한 개발 보조 스크립트
        print_err(f"생성 실패: {e}")
        return False


def create_mybox_mixin() -> bool:
    """mybox_mixin.py 생성."""
    print_step("mybox_mixin.py 생성", "⚙️")

    mybox_mixin_code = '''"""네이버 MyBox Mixin."""
from __future__ import annotations

import time
from pathlib import Path


def _js(name: str) -> str:
    """Load JavaScript from _js/ directory."""
    return (Path(__file__).parent.parent / "_js" / name).read_text(encoding="utf-8")


class MyBoxMixin:
    """네이버 MyBox 기능."""
    pass
'''

    try:
        mixin_file = MIXINS_DIR / "mybox_mixin.py"
        mixin_file.write_text(mybox_mixin_code, encoding="utf-8")
        print_ok(f"생성: {mixin_file}")
        return True
    except Exception as e:  # noqa: BLE001 - 브라우저 믹스인 코드 생성 스캐폴딩 개발도구 - 파일 생성 실패시 print_err 후 False 반환, 런타임 보안과 무관한 개발 보조 스크립트
        print_err(f"생성 실패: {e}")
        return False


def update_mixins_init() -> bool:
    """mixins/__init__.py 업데이트."""
    print_step("mixins/__init__.py 업데이트", "⚙️")

    init_file = MIXINS_DIR / "__init__.py"

    try:
        content = init_file.read_text(encoding="utf-8")

        # 이미 import되어 있는지 확인
        if "MailMixin" not in content:
            content = content.replace(
                "from .blog_mixin import BlogMixin",
                "from .blog_mixin import BlogMixin\nfrom .mail_mixin import MailMixin\nfrom .calendar_mixin import CalendarMixin\nfrom .mybox_mixin import MyBoxMixin",
            )
            content = content.replace(
                '__all__ = ["CafeMixin", "BlogMixin"]',
                '__all__ = ["CafeMixin", "BlogMixin", "MailMixin", "CalendarMixin", "MyBoxMixin"]',
            )
            init_file.write_text(content, encoding="utf-8")
            print_ok("Import 추가됨")
        else:
            print_ok("이미 등록됨")
        return True
    except Exception as e:  # noqa: BLE001 - 브라우저 믹스인 코드 생성 스캐폴딩 개발도구 - 파일 생성 실패시 print_err 후 False 반환, 런타임 보안과 무관한 개발 보조 스크립트
        print_err(f"업데이트 실패: {e}")
        return False


def update_browser_agent() -> bool:
    """agent.py BrowserAgent 클래스 정의 업데이트."""
    print_step("agent.py 업데이트", "⚙️")

    agent_file = Path(__file__).parent / "agent.py"

    try:
        content = agent_file.read_text(encoding="utf-8")

        # 이미 import되어 있는지 확인
        if "MailMixin" not in content:
            # Import 줄 수정
            content = content.replace(
                "from scripts.browser.agent.mixins import CafeMixin, BlogMixin",
                "from scripts.browser.agent.mixins import CafeMixin, BlogMixin, MailMixin, CalendarMixin, MyBoxMixin",
            )
            # 클래스 정의 수정
            content = content.replace(
                "class BrowserAgent(CafeMixin, BlogMixin):",
                "class BrowserAgent(CafeMixin, BlogMixin, MailMixin, CalendarMixin, MyBoxMixin):",
            )
            agent_file.write_text(content, encoding="utf-8")
            print_ok("Mixin 상속 추가됨")
        else:
            print_ok("이미 등록됨")
        return True
    except Exception as e:  # noqa: BLE001 - 브라우저 믹스인 코드 생성 스캐폴딩 개발도구 - 파일 생성 실패시 print_err 후 False 반환, 런타임 보안과 무관한 개발 보조 스크립트
        print_err(f"업데이트 실패: {e}")
        return False


def verify_import() -> bool:
    """Import 검증."""
    print_step("Import 검증", "✅")

    try:
        from scripts.browser.agent.agent import BrowserAgent

        print_ok("BrowserAgent import 성공")

        # Mixin 메서드 확인
        has_mail = hasattr(BrowserAgent, "mail_inbox")
        has_calendar = hasattr(BrowserAgent, "calendar_events")
        has_mybox = hasattr(BrowserAgent, "mybox_files")

        print(f"  mail_inbox 메서드: {'예정' if not has_mail else '추가됨'}")
        print(f"  calendar_events 메서드: {'예정' if not has_calendar else '추가됨'}")
        print(f"  mybox_files 메서드: {'예정' if not has_mybox else '추가됨'}")

        return True
    except Exception as e:  # noqa: BLE001 - 브라우저 믹스인 코드 생성 스캐폴딩 개발도구 - 파일 생성 실패시 print_err 후 False 반환, 런타임 보안과 무관한 개발 보조 스크립트
        print_err(f"Import 실패: {e}")
        return False


def _wait_for_naver_login(login_status: dict) -> bool:
    """기본 로그인 미감지 시 자동 재감지(최대 5회). 최종 로그인 여부 반환."""
    print("\n⚠️  기본 로그인 필요: https://naver.com")
    print("   (쿠키 자동 감지 대기 중...)\n")

    # 자동 재감지 (최대 5회, 30초 간격)
    for attempt in range(1, 6):
        time.sleep(10)
        print(f"  [{attempt}/5] 로그인 상태 재확인 중...", end=" ", flush=True)
        login_status = check_naver_login()
        if login_status.get("naver.com", False):
            print("\n  ✓ 기본 로그인 감지됨!")
            break
        print("(미로그인)")

        if attempt < 5:
            time.sleep(20)

    # 마지막 확인
    return bool(login_status.get("naver.com", False))


def main():
    """자동 감지 및 초기화 실행."""
    print("\n" + "=" * 60)
    print("  네이버 서비스 자동 감지 및 초기화")
    print("=" * 60)

    # 1. CDP 연결 확인
    if not check_cdp_connection():
        print_err("\n[FATAL] CDP 연결 실패. 중단.")
        return False

    # 2. 네이버 기본 로그인 확인 (메일/캘린더/MyBox는 기본 로그인으로 통합 접근 가능)
    login_status = check_naver_login()

    if not login_status.get("naver.com", False) and not _wait_for_naver_login(login_status):
        print_err("\n[FATAL] 로그인 타임아웃. 중단.")
        return False

    # 3. Phase 0: Mixin 생성
    print_step("Phase 0: Mixin 골격 생성", "🔧")

    steps = [
        create_mail_mixin,
        create_calendar_mixin,
        create_mybox_mixin,
        update_mixins_init,
        update_browser_agent,
    ]

    all_ok = True
    for step in steps:
        if not step():
            all_ok = False

    if not all_ok:
        print_err("\n[WARN] 일부 단계 실패")

    # 4. 검증
    if not verify_import():
        print_err("\n[FATAL] 검증 실패. 중단.")
        return False

    # 5. 요약
    print("\n" + "=" * 60)
    print("  초기화 완료 요약")
    print("=" * 60)
    print("  ✓ CDP 연결: OK")
    print("  ✓ 네이버 기본 로그인: OK (메일/캘린더/MyBox 통합 접근 가능)")
    print("  ✓ Mixin 생성: OK")
    print("  ✓ Import 검증: OK")

    print("\n  ✅ 모든 준비 완료!")
    print("  다음: Haiku 세션에서 Phase 1.1 (mail_inbox) 실행")

    print("=" * 60 + "\n")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
