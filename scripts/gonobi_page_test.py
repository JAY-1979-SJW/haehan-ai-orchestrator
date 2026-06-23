import sys

sys.path.insert(0, ".")
from scripts.naver.blog.gonobi.scraper import _fetch_post_list, _session

s = _session()

# 홈조명(128건 예상) 전 페이지 카운트
total = 0
seen = set()
for p in range(1, 20):
    nos = _fetch_post_list(s, "14", p)
    new = [n for n in nos if n not in seen]
    seen.update(new)
    print(f"page {p}: {len(new)}건 누적:{len(seen)}")
    if not new:
        print("종료")
        break
