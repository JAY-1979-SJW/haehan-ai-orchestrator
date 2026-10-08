"""제목 바로 아래에 영상을 넣고, 그 다음 본문을 쓰는 신규 발행 스크립트.

기존 write_mixed_content는 text/image만 지원해 video 블록을 못 넣는다.
BlogWriter 저수준 메서드(set_title, insert_video, write_body)를 직접
순서대로 호출해 "제목 → 영상 → 본문" 구조를 만든다.

사용:
  python scripts/naver/blog/cli/publish_with_video.py <draft.json> --publish
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.common.logger import get_logger  # noqa: E402
from scripts.naver.blog.core.writer import BlogWriter  # noqa: E402
from scripts.naver.blog.marketing import TARGET_BLOG_ID  # noqa: E402

_log = get_logger(__name__)


def _click_publish_and_report(page, bw, draft: dict) -> None:
    """발행 버튼 클릭 → 태그/공개설정 → 최종 발행 + 결과 출력."""
    time.sleep(1)
    page.get_by_role("button", name="발행", exact=True).click(timeout=5000)
    time.sleep(1.5)
    if draft.get("tags"):
        bw.set_tags(draft["tags"])
    bw.set_visibility("public")
    time.sleep(0.5)

    # 패널의 최종 발행 버튼(상단 "발행"과 셀렉터가 같아 .last로 구분)
    try:
        page.get_by_role("button", name="발행", exact=True).last.click(timeout=5000)
        page.wait_for_timeout(3000)
        if "PostView" in page.url:
            print("발행 완료:", page.url)
        else:
            print("발행 확인 필요 — 현재 URL:", page.url)
    except Exception as e:  # noqa: BLE001 - 네이버 블로그 발행 버튼 클릭 자동화 - 클릭 실패 시 메시지만 출력, 발행 여부는 별도로 현재 URL을 확인해 판단(성공을 임의로 단정하지 않음)
        print("발행 버튼 클릭 실패:", e)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("draft")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--video-path", default=None, help="로컬 영상 파일 경로(없으면 draft의 video_path 사용)")
    parser.add_argument("--port", type=int, default=9222)
    args = parser.parse_args()

    draft = json.loads(Path(args.draft).read_text(encoding="utf-8"))
    video_path = args.video_path or draft.get("video_path")
    video_title = draft.get("video_title", draft["title"])

    print(f"제목: {draft['title']}")
    print(f"영상: {video_path}")
    print(f"본문: {len(draft['body'])}자 | 태그: {len(draft['tags'])}개")

    if not args.publish:
        print("\n※ 실제 발행하려면 --publish")
        return

    from scripts.naver.blog.marketing.publish import connect_and_ensure_login

    pw, browser, page = connect_and_ensure_login(cdp_url=f"http://localhost:{args.port}", blog_id=TARGET_BLOG_ID)
    if page is None:
        print("로그인 실패, 중단")
        return

    bw = BlogWriter(page)
    if not bw.open():
        print("편집기 열기 실패")
        browser.close()
        pw.stop()
        return

    if not bw.set_title(draft["title"]):
        print("제목 입력 실패")
        browser.close()
        pw.stop()
        return

    if video_path and Path(video_path).exists():
        if not bw.insert_video(video_path, title=video_title):
            print("영상 삽입 실패 — 본문만이라도 계속 진행")
    else:
        print(f"영상 파일 없음: {video_path} — 본문만 진행")

    if not bw.write_body(draft["body"], append=True, verify=False):
        print("본문 입력 실패")
        browser.close()
        pw.stop()
        return

    _click_publish_and_report(page, bw, draft)

    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
