"""네이버 블로그 자동 로그인 + 글 작성 통합 테스트 (임시저장 모드).

흐름:
  1. 새 탭 열기
  2. 자격증명으로 사람처럼 천천히 로그인
  3. 캡차 발생 시 사용자에게 위임 (최대 300초 대기)
  4. 블로그 글쓰기 페이지 진입 (blogId=skyjwsin)
  5. iframe(mainFrame) 진입
  6. 임시저장 복원 다이얼로그 자동 처리
  7. 제목 + 본문 작성
  8. ★ 임시저장 (발행 X — 안전)
  9. 결과 보고

실행:
  python scripts/naver/test_blog_write.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.web_connector import get_page
from scripts.naver.auth import login_naver, _load_credentials
from scripts.naver.blog.writer import BlogWriter
from scripts.login_detector import detect_login_state
from scripts.popup_detector import handle_page_popups


def main():
    print("=" * 70)
    print("  네이버 블로그 자동 로그인 + 글 작성 (임시저장)")
    print("=" * 70)
    print()

    # 1. 자격증명 확인
    nid, pw = _load_credentials()
    if not nid or not pw:
        print("✗ 자격증명 없음 — register_credentials.py 먼저 실행")
        sys.exit(1)
    print(f"  ID: {nid}  |  PW: {'*' * len(pw)}자")

    # 2. 새 탭 열기
    print("\n  [1] 새 탭 열기...")
    existing = get_page()
    ctx = existing.context
    page = ctx.new_page()
    print(f"  ✓ 새 탭 생성됨 (총 {len(ctx.pages)}개 탭)")

    # 3. 자동 로그인 (사람처럼)
    print("\n  [2] 자동 로그인 시도 (사람처럼 천천히)...")
    result = login_naver(page, wait_for_user_s=300)
    if not result["ok"]:
        print(f"  ✗ 로그인 실패: {result.get('reason')}")
        if result.get("captcha_required"):
            print("    → 캡차 발생. 브라우저에서 수동 처리 필요")
        sys.exit(1)
    print(f"  ✓ 로그인 성공: {result.get('user')}")

    # 4. 블로그 글쓰기 페이지 진입
    print("\n  [3] 블로그 글쓰기 페이지 진입 (blogId=skyjwsin)...")
    bw = BlogWriter(page)
    if not bw.open(blog_id="skyjwsin", auto_login=False):  # 이미 로그인됨
        print("  ✗ 편집기 열기 실패")
        # 진단: 현재 페이지 상태
        print(f"     현재 URL: {page.url}")
        print(f"     frame 목록:")
        for f in page.frames:
            print(f"       name='{f.name}' url={f.url[:80]}")
        sys.exit(1)

    print(f"  ✓ 편집기 진입 완료")
    print(f"     mainFrame: {bw.frame.name if bw.frame else 'None'}")

    # 5. 제목 입력
    test_title = f"[자동작성 테스트] {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    print(f"\n  [4] 제목 입력: {test_title}")
    if not bw.set_title(test_title):
        print("  ✗ 제목 입력 실패")
        sys.exit(1)
    print("  ✓ 제목 입력 완료")

    # 6. 본문 입력
    test_body = [
        "이 글은 해한 AI 오케스트레이터의 자동 작성 테스트입니다.",
        "iframe(mainFrame) 안의 SmartEditor 에디터에 접근하여 작성되었습니다.",
        f"작성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "이 글은 임시저장 상태이며 발행되지 않습니다.",
    ]
    print(f"\n  [5] 본문 입력 ({len(test_body)} 단락)...")
    if not bw.write_body(test_body):
        print("  ✗ 본문 입력 실패")
        sys.exit(1)
    print("  ✓ 본문 입력 완료")

    # 7. 임시저장 (★ 발행 안 함)
    print(f"\n  [6] 임시저장 (★ 발행 안 함)...")
    save_result = bw.save_draft()
    print(f"  결과: {save_result}")

    print()
    print("=" * 70)
    print("  완료. 브라우저에서 임시저장 결과 확인 가능.")
    print("  ※ 실제 발행은 사용자 승인 후 별도 진행 필요.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨")
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"\n실패: {e}")
        traceback.print_exc()
        sys.exit(1)
