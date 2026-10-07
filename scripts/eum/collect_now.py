"""EUM 신규현장 수집 + 영업 타겟 준비."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.browser.agent.agent import BrowserAgent
from scripts.eum.install_targets import collect_all_install_targets

agent = BrowserAgent()
agent.connect()

print("EUM 신규현장 수집 시작...")
result = collect_all_install_targets(agent._page, max_pages=50)

print(f"수집 완료: {result.get('total')}건 / {result.get('pages_visited')}페이지")

rows = json.loads(Path("data/eum_new_sites_install_targets.json").read_text(encoding="utf-8"))
email_rows = [r for r in rows if r.get("이메일") or r.get("email") or r.get("담당자이메일")]
phone_rows = [r for r in rows if r.get("연락처") or r.get("phone") or r.get("담당자연락처")]

print(f"이메일 확보: {len(email_rows)}건")
print(f"연락처 확보: {len(phone_rows)}건")
print()
print("=== 샘플 5건 ===")
for r in rows[:5]:
    keys = list(r.keys())
    print(f"  공사명: {r.get('공사명', '')[:35]}")
    print(f"  업체:   {r.get('업체명', '') or r.get('공사업체', '')}")
    print(f"  이메일: {r.get('이메일', '') or r.get('email', '없음')}")
    print(f"  연락처: {r.get('연락처', '') or r.get('phone', '없음')}")
    print()

print("전체 필드명:", list(rows[0].keys()) if rows else "없음")
