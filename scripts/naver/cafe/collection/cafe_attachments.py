"""네이버 카페 첨부파일 탐색 및 다운로드 스크립트.

사용법:
    # 게시글 URL에서 첨부파일 목록 확인
    python scripts/local_agent/naver_cafe_attachments.py list \
        "https://cafe.naver.com/ArticleRead.nhn?clubid=10393532&articleid=12345"

    # 게시판 게시글 스캔 후 첨부파일 있는 것만 추출
    python scripts/local_agent/naver_cafe_attachments.py scan \
        --cafe https://cafe.naver.com/shop07 \
        --board "CAD 화일 자료실" \
        --pages 2

    # 특정 게시글 첨부파일 다운로드
    python scripts/local_agent/naver_cafe_attachments.py download \
        "https://cafe.naver.com/ArticleRead.nhn?clubid=10393532&articleid=12345" \
        --out data/downloads

    # 게시판 스캔 후 전체 다운로드
    python scripts/local_agent/naver_cafe_attachments.py scan \
        --cafe https://cafe.naver.com/shop07 \
        --board "CAD 화일 자료실" \
        --pages 2 --download --out data/downloads
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.common.browser_js_dir import JS_DIR

if TYPE_CHECKING:  # 엔진 ↔ 믹스인 import 순환을 피하려고 타입 힌트로만 쓰고 실제 사용은 main 안에서 불러온다(T4 C12a)
    from scripts.browser.agent.agent import BrowserAgent

_DEFAULT_DOWNLOAD_DIR = "data/downloads"


def _load_js(name: str) -> str:
    return (JS_DIR / name).read_text(encoding="utf-8")


def _extract_article_id(href: str) -> str:
    m = re.search(r"articles/(\d+)|articleid=(\d+)", href)
    return m.group(1) or m.group(2) if m else ""


def _ask_save_dir(default: str = _DEFAULT_DOWNLOAD_DIR, timeout_sec: int = 15) -> str:
    """저장 경로를 사용자에게 묻고 반환. 미입력 시 기본 경로 사용."""
    import threading

    abs_default = str(Path(default).resolve())
    print("\n┌─ 저장 경로 설정 ─────────────────────────────────────────")
    print(f"│  기본 경로: {abs_default}")
    print("│  다른 경로를 입력하거나 Enter를 누르면 기본 경로에 저장합니다.")
    print(f"│  ({timeout_sec}초 내 미입력 시 기본 경로 자동 선택)")
    print("└──────────────────────────────────────────────────────────")
    print("저장 경로> ", end="", flush=True)

    result = [default]
    answered = threading.Event()

    def _read():
        try:
            line = sys.stdin.readline().strip()
            result[0] = line if line else default
        except Exception:  # noqa: BLE001 - 표준입력 프롬프트 읽기 타임아웃 무시(기본값 사용), 첨부파일 스캔 중 개별 게시글 오류는 출력 후 계속 — 읽기전용 수집
            pass
        answered.set()

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    answered.wait(timeout=timeout_sec)

    chosen = result[0]
    abs_chosen = str(Path(chosen).resolve())

    if chosen == default:
        print(f"\n[알림] 기본 경로에 저장합니다: {abs_default}")
    else:
        print(f"\n[알림] 지정 경로에 저장합니다: {abs_chosen}")

    return chosen


_BUTTON_TEXTS = {"내pc 저장", "파일 다운로드", "다운로드", "download", "저장"}


def _is_real_filename(name: str) -> bool:
    """버튼 텍스트가 아닌 실제 파일명인지 확인."""
    if not name:
        return False
    return name.lower().strip() not in _BUTTON_TEXTS and "." in name


def _do_download(agent: BrowserAgent, att: dict, save_dir: str) -> None:
    """단일 첨부파일 다운로드 후 결과 출력."""
    raw_name = att.get("name", "")
    # 버튼 텍스트("내PC 저장" 등)는 파일명으로 사용하지 않음 → Content-Disposition 우선
    filename_hint = raw_name if _is_real_filename(raw_name) else ""
    display = raw_name or att.get("url", "").split("/")[-1] or "파일"
    ext_str = f"[{att['ext'].upper()}] " if att.get("ext") else ""
    print(f"다운로드: {ext_str}{display[:50]}")
    dl = agent.download_attachment(att["url"], save_dir=save_dir, filename=filename_hint)
    if dl["ok"]:
        p = Path(dl["path"])
        size_kb = p.stat().st_size // 1024 if p.exists() else 0
        print(f"  → 저장 완료: {dl['path']}  ({size_kb:,} KB)")
    else:
        print(f"  → 실패: {dl['error']}")


def cmd_list(agent: BrowserAgent, article_url: str, as_json: bool):
    """단일 게시글의 첨부파일 목록 출력."""
    print(f"게시글 이동 중: {article_url}")
    result = agent.read_article(article_url)
    attachments = result.get("attachments", [])

    if as_json:
        print(json.dumps(attachments, ensure_ascii=False, indent=2))
        return

    print(f"\n제목: {result['title']}")
    print(f"작성자: {result['author']}  {result['written_at']}")
    if not attachments:
        print("\n첨부파일 없음")
        return
    print(f"\n첨부파일 {len(attachments)}개:")
    for i, a in enumerate(attachments, 1):
        size_str = f"  ({a['size']})" if a["size"] else ""
        print(f"  {i}. [{a['ext'].upper():>4}] {a['name']}{size_str}")
        print(f"       {a['url'][:100]}")


def _find_menu_id(agent: BrowserAgent, cafe_url: str, board: str) -> str:
    """게시판 menuid 결정(못 찾으면 빈 문자열)."""
    menu_id = ""
    agent.go(cafe_url)
    time.sleep(2)
    links = agent.extract_links(filter_href="ArticleList")
    for lk in links:
        if board in lk["text"]:
            m = re.search(r"menuid=(\d+)", lk["href"])
            if m:
                menu_id = m.group(1)
                break
    return menu_id


def _article_list_url(club_id: str, menu_id: str, page_num: int) -> str:
    """게시판 목록 페이지 URL."""
    if menu_id:
        url = (
            f"https://cafe.naver.com/ArticleList.nhn?search.clubid={club_id}"
            f"&search.menuid={menu_id}&search.boardtype=L&search.page={page_num}"
        )
    else:
        url = (
            f"https://cafe.naver.com/ArticleList.nhn?search.clubid={club_id}"
            f"&search.boardtype=L&search.page={page_num}"
        )
    return url


def _scan_one_post(
    agent: BrowserAgent, post: dict, href: str, do_download: bool, save_dir: str, all_with_attach: list[dict]
) -> None:
    """게시글 1건을 읽어 첨부파일이 있으면 수집(오류는 출력 후 계속)."""
    try:
        result = agent.read_article(href)
        attachments = result.get("attachments", [])
        if attachments:
            print(f" → 첨부파일 {len(attachments)}개 발견!")
            post["attachments"] = attachments
            post["title_full"] = result["title"]
            all_with_attach.append(post)

            if do_download:
                for att in attachments:
                    _do_download(agent, att, save_dir)
        else:
            print(" → 첨부파일 없음")
    except Exception as e:  # noqa: BLE001 - 표준입력 프롬프트 읽기 타임아웃 무시(기본값 사용), 첨부파일 스캔 중 개별 게시글 오류는 출력 후 계속 — 읽기전용 수집
        print(f" → 오류: {e}")


def _print_scan_summary(all_with_attach: list[dict]) -> None:
    """스캔 완료 요약 출력."""
    print("\n\n=== 스캔 완료 ===")
    print(f"첨부파일 포함 게시글: {len(all_with_attach)}개")
    for p in all_with_attach:
        print(f"  - {p['title'][:50]}")
        for a in p.get("attachments", []):
            print(f"      [{a['ext'].upper():>4}] {a['name']}")


def cmd_scan(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
    agent: BrowserAgent, cafe_url: str, board: str, pages: int, do_download: bool, out_dir: str, as_json: bool
):
    """게시판 게시글을 스캔해 첨부파일이 있는 것만 수집."""
    from scripts.naver.cafe.cafe_scraper import scrape_posts_page

    # 다운로드 모드일 때만 사전에 경로 확인
    save_dir = out_dir
    if do_download:
        save_dir = _ask_save_dir(default=out_dir)

    club_id = agent._get_club_id(cafe_url)
    if not club_id:
        print("[오류] club_id를 찾지 못했습니다.")
        sys.exit(1)

    # 게시판 menuid 결정
    menu_id = _find_menu_id(agent, cafe_url, board)

    all_with_attach: list[dict] = []

    for page_num in range(1, pages + 1):
        url = _article_list_url(club_id, menu_id, page_num)

        print(f"\n[{page_num}/{pages}] 목록 수집: {url}")
        posts = scrape_posts_page(agent, url)
        print(f"  게시글 {len(posts)}개 확인")

        for i, post in enumerate(posts, 1):
            href = post.get("href", "")
            if not href:
                continue
            print(f"  [{i}/{len(posts)}] {post['title'][:40]}...", end="", flush=True)
            time.sleep(1.2)
            _scan_one_post(agent, post, href, do_download, save_dir, all_with_attach)

    _print_scan_summary(all_with_attach)

    if as_json:
        print("\nJSON 결과:")
        print(json.dumps(all_with_attach, ensure_ascii=False, indent=2))


def cmd_download(agent: BrowserAgent, article_url: str, out_dir: str):
    """단일 게시글의 첨부파일 모두 다운로드."""
    print(f"게시글 이동: {article_url}")
    result = agent.read_article(article_url)
    attachments = result.get("attachments", [])

    if not attachments:
        print("첨부파일 없음")
        return

    # 저장 경로 확인
    save_dir = _ask_save_dir(default=out_dir)

    print(f"\n첨부파일 {len(attachments)}개 다운로드 시작...")
    for i, att in enumerate(attachments, 1):
        print(f"  [{i}/{len(attachments)}] ", end="")
        _do_download(agent, att, save_dir)


def main():
    parser = argparse.ArgumentParser(
        description="네이버 카페 첨부파일 탐색 및 다운로드",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # list 명령
    p_list = sub.add_parser("list", help="게시글 첨부파일 목록")
    p_list.add_argument("article_url", help="게시글 URL")
    p_list.add_argument("--json", action="store_true", dest="as_json")

    # scan 명령
    p_scan = sub.add_parser("scan", help="게시판 스캔 후 첨부파일 게시글 수집")
    p_scan.add_argument("--cafe", required=True, help="카페 URL")
    p_scan.add_argument("--board", default="전체글보기", help="게시판명")
    p_scan.add_argument("--pages", type=int, default=1, help="스캔할 페이지 수")
    p_scan.add_argument("--download", action="store_true", help="발견 즉시 다운로드")
    p_scan.add_argument("--out", default="data/downloads", help="다운로드 저장 경로")
    p_scan.add_argument("--json", action="store_true", dest="as_json")

    # download 명령
    p_dl = sub.add_parser("download", help="게시글 첨부파일 다운로드")
    p_dl.add_argument("article_url", help="게시글 URL")
    p_dl.add_argument("--out", default="data/downloads", help="저장 경로")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    from scripts.browser.agent.agent import BrowserAgent

    with BrowserAgent() as agent:
        if args.command == "list":
            cmd_list(agent, args.article_url, args.as_json)
        elif args.command == "scan":
            cmd_scan(agent, args.cafe, args.board, args.pages, args.download, args.out, args.as_json)
        elif args.command == "download":
            cmd_download(agent, args.article_url, args.out)


if __name__ == "__main__":
    main()
