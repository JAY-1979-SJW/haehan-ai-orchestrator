"""fixture JSON에서 discovery candidate 목록을 생성하는 스크립트.

실제 브라우저 접속 없이, fixture 데이터(HTML 구조 기술)에서
DiscoveryCandidate 목록을 생성하고 JSON으로 출력한다.

Usage:
    python scripts/build_discovery_candidates_from_fixture.py \
        --site-id g2b \
        --fixture configs/site_policies/g2b.json \
        --output tmp/candidates_g2b.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_orchestrator.local_agent.browser_discovery_candidates import (
    build_candidate,
    CANDIDATE_MENU,
    CANDIDATE_PAGE_TITLE,
    CANDIDATE_TABLE_HEADER,
    CANDIDATE_DOWNLOAD_LINK,
    CANDIDATE_SUBMIT_BUTTON,
    CANDIDATE_BUTTON,
    CANDIDATE_FIELD,
)

# site별 내장 fixture 정의 (실제 사이트 구조 기반 예시)
_BUILTIN_FIXTURES: dict[str, list[dict]] = {
    "g2b": [
        {"candidate_type": CANDIDATE_MENU, "visible_label": "입찰공고", "role": "link", "source_path_key": "/bid"},
        {"candidate_type": CANDIDATE_MENU, "visible_label": "공사공고", "role": "link", "source_path_key": "/notice"},
        {"candidate_type": CANDIDATE_PAGE_TITLE, "visible_label": "나라장터 입찰공고 목록", "role": "heading", "source_path_key": "/bid"},
        {"candidate_type": CANDIDATE_TABLE_HEADER, "visible_label": "공고번호", "role": "columnheader", "source_path_key": "/bid"},
        {"candidate_type": CANDIDATE_TABLE_HEADER, "visible_label": "공고명", "role": "columnheader", "source_path_key": "/bid"},
        {"candidate_type": CANDIDATE_TABLE_HEADER, "visible_label": "공고기관", "role": "columnheader", "source_path_key": "/bid"},
        {"candidate_type": CANDIDATE_DOWNLOAD_LINK, "visible_label": "공고문 다운로드", "role": "link", "source_path_key": "/notice"},
        {"candidate_type": CANDIDATE_DOWNLOAD_LINK, "visible_label": "첨부파일 다운로드", "role": "link", "source_path_key": "/notice"},
        {"candidate_type": CANDIDATE_FIELD, "visible_label": "검색어", "role": "textbox", "source_path_key": "/search"},
        {"candidate_type": CANDIDATE_BUTTON, "visible_label": "검색", "role": "button", "source_path_key": "/search"},
        {"candidate_type": CANDIDATE_SUBMIT_BUTTON, "visible_label": "투찰 제출", "role": "button", "source_path_key": "/bid"},
    ],
    "hometax": [
        {"candidate_type": CANDIDATE_MENU, "visible_label": "공지사항", "role": "link", "source_path_key": "/announcement"},
        {"candidate_type": CANDIDATE_PAGE_TITLE, "visible_label": "홈택스 공지사항", "role": "heading", "source_path_key": "/announcement"},
        {"candidate_type": CANDIDATE_TABLE_HEADER, "visible_label": "제목", "role": "columnheader", "source_path_key": "/announcement"},
        {"candidate_type": CANDIDATE_TABLE_HEADER, "visible_label": "등록일", "role": "columnheader", "source_path_key": "/announcement"},
        {"candidate_type": CANDIDATE_DOWNLOAD_LINK, "visible_label": "첨부파일", "role": "link", "source_path_key": "/pubcDocument"},
        {"candidate_type": CANDIDATE_FIELD, "visible_label": "검색어", "role": "textbox", "source_path_key": "/announcement"},
    ],
    "mss": [
        {"candidate_type": CANDIDATE_MENU, "visible_label": "공고", "role": "link", "source_path_key": "/notice"},
        {"candidate_type": CANDIDATE_MENU, "visible_label": "정책", "role": "link", "source_path_key": "/policy"},
        {"candidate_type": CANDIDATE_PAGE_TITLE, "visible_label": "중소벤처기업부 공고 목록", "role": "heading", "source_path_key": "/notice"},
        {"candidate_type": CANDIDATE_TABLE_HEADER, "visible_label": "공고번호", "role": "columnheader", "source_path_key": "/notice"},
        {"candidate_type": CANDIDATE_TABLE_HEADER, "visible_label": "공고명", "role": "columnheader", "source_path_key": "/notice"},
        {"candidate_type": CANDIDATE_DOWNLOAD_LINK, "visible_label": "공고 첨부파일", "role": "link", "source_path_key": "/notice"},
        {"candidate_type": CANDIDATE_FIELD, "visible_label": "키워드 검색", "role": "textbox", "source_path_key": "/notice"},
        {"candidate_type": CANDIDATE_BUTTON, "visible_label": "검색", "role": "button", "source_path_key": "/notice"},
    ],
}


def load_fixture(site_id: str, fixture_path: Path | None) -> list[dict]:
    if fixture_path and fixture_path.exists():
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("discovery_fixture", [])
    return _BUILTIN_FIXTURES.get(site_id, [])


def build_candidates(site_id: str, items: list[dict]) -> list[dict]:
    results = []
    for item in items:
        res = build_candidate(
            candidate_type=item.get("candidate_type", ""),
            visible_label=item.get("visible_label", ""),
            role=item.get("role", ""),
            source_site_id=site_id,
            source_path_key=item.get("source_path_key", ""),
        )
        results.append(res)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="fixture → discovery candidate 생성")
    parser.add_argument("--site-id", required=True, help="사이트 ID (예: g2b)")
    parser.add_argument("--fixture", type=Path, default=None, help="커스텀 fixture JSON 경로")
    parser.add_argument("--output", type=Path, default=None, help="결과 JSON 저장 경로")
    args = parser.parse_args()

    items = load_fixture(args.site_id, args.fixture)
    if not items:
        print(f"[WARN] site_id={args.site_id}에 대한 fixture 항목이 없습니다")
        sys.exit(1)

    candidates = build_candidates(args.site_id, items)
    ok_count = sum(1 for c in candidates if c.get("ok"))
    blocked_count = len(candidates) - ok_count

    output = {
        "site_id": args.site_id,
        "total": len(candidates),
        "ok": ok_count,
        "blocked": blocked_count,
        "candidates": candidates,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"✅ 저장 완료: {args.output}  (총 {len(candidates)}건, OK={ok_count}, BLOCKED={blocked_count})")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
