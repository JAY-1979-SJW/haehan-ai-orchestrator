"""32번(gongmu-tax) 프로젝트의 조세판례 raw 인덱스(tax_precedents_index.json)를 읽어,
law.go.kr → 국세청 국세법령정보시스템(taxlaw.nts.go.kr) 리다이렉트를 태워 요지·
판결내용을 긁는다.

law.go.kr DRF API(target=prec)는 세금 판례 상세조회에서 항상 "일치하는 판례가
없습니다"를 반환한다(검증 완료, API 버그/제약으로 추정) — 반면 사람이 보는 페이지
(precInfoP.do?precSeq=)는 자동으로 taxlaw.nts.go.kr로 리다이렉트되며 요지가 있다.
공식 Open API가 없는 도메인이라 CDP 브라우저 자동화가 정당한 경로다(CLAUDE.md의
"[0] 벤더 공식 API가 없을 때만 CDP" 원칙).

사용법:
  python -m ai_orchestrator.gongmu.fetch_tax_precedent_summary <tax_precedents_index.json 경로> [--limit N]  (저장소 루트에서)

출력: 같은 디렉터리에 <파일명>_with_summary.json — 원본 각 항목에 summary,
judgment_note, source_ntstDcmId, fetched_ok 필드를 추가한다.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

from ai_orchestrator.gongmu.fetch_nts_interpretations import VISITS_DIR, latest_html_after, run_in_repo


def _extract_summary(html_path: str) -> tuple[str, str]:
    soup = BeautifulSoup(Path(html_path).read_text(encoding="utf-8"), "html.parser")

    def _section(label: str) -> str:
        h4 = next((h for h in soup.find_all("h4") if h.get_text().strip() == label), None)
        sib = h4.find_next_sibling() if h4 else None
        return sib.get_text(" ", strip=True) if sib else ""

    return _section("요지"), _section("판결내용")


def fetch_one(prec_seq: str) -> dict:
    before = {str(p) for p in VISITS_DIR.glob("*.html")}
    run_in_repo(
        ["python", "scripts/entry/cdp_cli.py", "goto", f"https://www.law.go.kr/LSW/precInfoP.do?precSeq={prec_seq}&mode=0"]
    )
    run_in_repo(["python", "scripts/entry/cdp_cli.py", "snapshot"])
    html_path = latest_html_after(before)
    if not html_path:
        return {"fetched_ok": False, "error": "no_snapshot"}
    if "ntstDcmId" not in html_path:
        return {"fetched_ok": False, "error": "no_nts_redirect", "html_path": html_path}
    summary, judgment_note = _extract_summary(html_path)
    ntst_id = html_path.split("ntstDcmId_")[1].split("__")[0]
    return {
        "fetched_ok": bool(summary),
        "summary": summary,
        "judgment_note": judgment_note,
        "source_ntstDcmId": ntst_id,
    }


def main() -> None:
    src = Path(sys.argv[1])
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    data = json.loads(src.read_text(encoding="utf-8"))
    precedents = data["precedents"]
    if limit:
        precedents = precedents[:limit]

    ok, fail = 0, 0
    for i, p in enumerate(precedents, 1):
        seq = p["case_serial"]
        print(f"[{i}/{len(precedents)}] {seq} {p.get('case_no', '')}")
        result = fetch_one(seq)
        p.update(result)
        if result.get("fetched_ok"):
            ok += 1
            print(f"   -> 요지: {result['summary'][:60]}")
        else:
            fail += 1
            print(f"   -> 실패: {result.get('error')}")
        time.sleep(0.5)

    out_path = src.parent / (src.stem + "_with_summary.json")
    data["precedents"] = precedents
    data["summary_fetch_ok"] = ok
    data["summary_fetch_fail"] = fail
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료: ok={ok} fail={fail} -> {out_path}")


if __name__ == "__main__":
    main()
