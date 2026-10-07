"""정적 import 점검에서 남아 있던 기존 항목의 재발 방지.

- BlogSEO 는 scripts/naver/blog/seo/seo.py 에 있고 seo/__init__ 이 별 import 로 다시 내보낸다. 별 재노출에 기대지 않고 실제 모듈에서 직접 import 한다.
- web_connector 는 연결(browser/cdp/connection.py)과 페이지 조작(browser/page/web_connector.py)으로 나뉘었다 — 옛 최상위 경로
  `scripts.web_connector` 를 import 하는 곳이 남지 않아야 하고, get_page 는 연결 쪽에서 가져온다.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SEO_USERS = (
    "scripts/naver/blog/__init__.py",
    "scripts/naver/blog/core/ai_writer.py",
    "scripts/naver/blog/core/writer_pro.py",
)


def test_blog_seo_is_imported_from_the_real_module():
    from scripts.naver.blog.seo.seo import BlogSEO

    assert BlogSEO.__module__ == "scripts.naver.blog.seo.seo"
    for rel in SEO_USERS:
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "from scripts.naver.blog.seo import BlogSEO" not in text, rel
        assert "from scripts.naver.blog.seo.seo import BlogSEO" in text, rel


def test_no_import_of_the_removed_top_level_web_connector():
    pat = re.compile(r"^\s*(from|import)\s+scripts\.web_connector\b", re.M)
    files = list((REPO / "scripts").rglob("*.py"))
    assert files, "검사 대상 0건이면 아래 검사가 공허해진다"
    hits = [str(p.relative_to(REPO)) for p in files if pat.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert not hits, hits
