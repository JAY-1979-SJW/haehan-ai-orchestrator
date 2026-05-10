"""네이버 블로그 작성 테스트.

사용법:
  python scripts/test_naver_blog.py

프로세스:
  1. 네이버 로그인 (사용자가 직접 수행)
     - 첫 실행: 로그인 화면 → 사용자 수동 로그인
     - 이후: 저장된 세션 자동 복원 (1회 로그인 후 반복 사용 가능)
  2. 블로그 이동
  3. 새 글 작성
  4. 저장
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.local_agent.browser.browser_session import open_user_session, wait_for_user_action


def test_naver_blog():
    """네이버 블로그 작성 테스트."""
    print("=" * 70)
    print("네이버 블로그 작성 테스트")
    print("=" * 70)

    profile_name = "naver_blog"
    session_dir = ROOT / "data" / "browser_sessions" / profile_name
    storage_file = session_dir / "state.json"
    is_first_run = not storage_file.is_file()

    print(f"\n📱 프로필: {profile_name}")
    if is_first_run:
        print("🆕 첫 실행: 로그인이 필요합니다")
        print("   → 브라우저에서 네이버에 로그인해주세요")
        print("   → 로그인 후 자동으로 진행됩니다")
        print("   → 로그인 정보는 자동으로 저장되어 다음 실행에서 재사용됩니다")
    else:
        print("♻️  기존 세션 복원: 자동으로 로그인 상태가 유지됩니다")

    print("\n[1단계] 브라우저 시작...")
    with open_user_session(
        profile_name=profile_name,
        start_url="https://www.naver.com/",
        save_storage=True,  # 중요: 로그인 세션 저장
    ) as context:
        page = context.new_page()
        print("✓ 브라우저 시작 완료")

        # 로그인 대기 또는 자동 진행
        if is_first_run:
            print("\n[2단계] 로그인 대기 중...")
            wait_for_user_action(seconds=120, message="네이버 로그인 진행 중")
        else:
            print("\n[2단계] 기존 세션으로 자동 진행")
            wait_for_user_action(seconds=3, message="페이지 로드 중")

        # 로그인 상태 확인
        print("\n[3단계] 로그인 상태 확인 중...")
        try:
            page.goto("https://www.naver.com/", timeout=60000, wait_until="domcontentloaded")
            body_text = page.inner_text("body")[:2000]
            if "로그인" in body_text and "아이디" in body_text:
                print("⚠️  로그인 화면이 보입니다. 로그인 후 계속하세요.")
                wait_for_user_action(seconds=60, message="로그인 진행 중")
            else:
                print("✓ 로그인 상태 확인됨")
        except Exception as e:
            print(f"⚠️  상태 확인 오류: {e}")

        # 블로그 이동
        print("\n[4단계] 블로그로 이동 중...")
        try:
            page.goto("https://section.blog.naver.com/BlogHome.naver", timeout=60000)
            wait_for_user_action(seconds=2, message="페이지 로드 중")
            print("✓ 블로그 홈 도착")
        except Exception as e:
            print(f"✗ 블로그 이동 실패: {e}")
            return False

        # 새 글 작성 페이지로 이동
        print("\n[5단계] 새 글 작성 페이지로 이동...")
        try:
            # 여러 가능한 새 글 작성 링크 시도
            write_url = "https://blog.naver.com/new"
            page.goto(write_url, timeout=60000)
            wait_for_user_action(seconds=3, message="글 작성 페이지 로드 중")
            print("✓ 글 작성 페이지 로드 완료")
        except Exception as e:
            print(f"⚠️  직접 이동 실패, 수동으로 '글 작성' 클릭 후 계속하세요")
            wait_for_user_action(seconds=30, message="글 작성 페이지 열기 대기")

        # 글 작성 안내
        print("\n[6단계] 글 작성 안내")
        print("""
가능한 작업:
  - 제목과 본문을 입력하세요
  - "임시저장" 또는 "발행" 버튼을 클릭하세요
  - 브라우저 창을 닫으면 자동으로 세션이 저장됩니다

다음 실행:
  - python scripts/test_naver_blog.py
  - 자동으로 로그인된 상태에서 시작됩니다 ✨
        """)

        # 최종 대기
        print("\n[7단계] 대기 중...")
        wait_for_user_action(seconds=120, message="글 작성 진행 중")

        print("\n[완료]")
        print("=" * 70)
        print("✓ 블로그 작성 테스트 완료")
        print("  → 세션이 자동으로 저장되었습니다")
        print("  → 다음 실행부터는 자동으로 로그인됩니다")
        print("=" * 70 + "\n")

        return True


if __name__ == "__main__":
    try:
        success = test_naver_blog()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n중단됨")
        sys.exit(1)
    except Exception as e:
        print(f"\n에러: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
