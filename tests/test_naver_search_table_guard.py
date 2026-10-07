"""naver_search_queries 의 f-string SQL 테이블명 허용 목록 검사."""

from __future__ import annotations

import sqlite3

import pytest

from scripts.naver.shopping import naver_search_db as db_mod
from scripts.naver.shopping import naver_search_queries as q


@pytest.mark.parametrize("bad", ["users", "naver_blog_posts; DROP TABLE x", ""])
def test_unknown_table_rejected(bad):
    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="unknown table"):
        q._top_queries(conn, bad)
    with pytest.raises(ValueError, match="unknown table"):
        q._max_collected_at(conn, bad)


def test_known_tables_accepted():
    assert q._check_table(db_mod.TABLE_BLOG) == db_mod.TABLE_BLOG
    assert q._check_table(db_mod.TABLE_SHOP) == db_mod.TABLE_SHOP
