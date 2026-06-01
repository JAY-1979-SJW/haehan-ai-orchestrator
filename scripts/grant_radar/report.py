"""report.py — 스캔 결과를 사업 프로필 기준으로 적합도 산정 + 보고서 생성.

입력:  data/grant_radar/scan_latest.json
프로필: configs/grant_radar_profile.json
출력:  data/grant_radar/report_latest.json  (+ report_latest.md)

실행:
    python -m scripts.grant_radar.report
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 쓰기 데이터는 영속 경로(env), 읽기 전용 프로필은 번들 configs
_ENV_DATA = os.environ.get("HAEHAN_DATA_DIR")
DATA_DIR = (Path(_ENV_DATA) / "grant_radar") if _ENV_DATA else (ROOT / "data" / "grant_radar")
SCAN_FILE = DATA_DIR / "scan_latest.json"
REPORT_JSON = DATA_DIR / "report_latest.json"
REPORT_MD = DATA_DIR / "report_latest.md"
PROFILE_FILE = ROOT / "configs" / "grant_radar_profile.json"

# 신청기간 끝일 패턴: "~ 2026-06-26 15:00"
_DEADLINE_RE = re.compile(r"~\s*(\d{4}-\d{2}-\d{2})")
_DDAY_RE = re.compile(r"D-(\d+)")
# 담당자: 신청기간 뒤, 등록일(YYYY-MM-DD) 앞의 한글 이름 토큰
_MANAGER_RE = re.compile(r"(\d{2}:\d{2})\s+([가-힣]{2,4})\s+\d{4}-\d{2}-\d{2}")


def _load_profile() -> dict:
    try:
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"keywords": [], "keyword_weights": {}}


def _score(text: str, profile: dict) -> tuple[int, list[str]]:
    """프로필 키워드 매칭 점수 + 매칭 키워드 목록."""
    weights = profile.get("keyword_weights", {})
    score = 0
    hits: list[str] = []
    for kw in profile.get("keywords", []):
        if kw and kw in text:
            score += int(weights.get(kw, 1))
            hits.append(kw)
    return score, hits


def _parse_deadline(raw: str) -> str | None:
    m = _DEADLINE_RE.search(raw)
    return m.group(1) if m else None


def _parse_dday(raw: str) -> str | None:
    if "종료" in raw:
        return "종료"
    m = _DDAY_RE.search(raw)
    return f"D-{m.group(1)}" if m else None


def _parse_manager(raw: str) -> str | None:
    m = _MANAGER_RE.search(raw)
    return m.group(2) if m else None


def _summarize(item: dict) -> str:
    """LLM 한 줄 요약 (미설정 시 MOCK 폴백). 토큰 절약 위해 적합 항목에만 호출."""
    try:
        sys.path.insert(0, str(ROOT))
        from ai_orchestrator.openai_client import _call

        fallback = item["title"][:80]
        system = "당신은 정부 지원사업 분석가입니다. 공고를 한 줄로 핵심만 요약합니다."
        user = f"공고: {item['title']}\n원문: {item['raw'][:300]}\n한국어로 한 줄 요약."
        return _call(system, user, fallback)
    except Exception:
        return item["title"][:80]


def build_report() -> dict:
    try:
        scan = json.loads(SCAN_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"스캔 파일 없음: {e}", "items": []}

    profile = _load_profile()
    enriched: list[dict] = []
    for it in scan.get("items", []):
        raw = it.get("raw", "")
        score, hits = _score(raw, profile)
        enriched.append(
            {
                "title": it.get("title", ""),
                "url": it.get("url", ""),
                "portal": it.get("portal", ""),
                "portal_name": it.get("portal_name", ""),
                "deadline": _parse_deadline(raw),
                "dday": _parse_dday(raw),
                "manager": _parse_manager(raw),
                "score": score,
                "matched": hits,
            }
        )

    # 적합도 내림차순 정렬, 상위 항목만 LLM 요약(최대 8건)
    enriched.sort(key=lambda x: x["score"], reverse=True)
    for it in [e for e in enriched if e["score"] > 0][:8]:
        it["summary"] = _summarize({"title": it["title"], "raw": it["title"]})

    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": profile.get("company_label", ""),
        "source": "grant_radar",
        "scanned_at": scan.get("scanned_at"),
        "total": len(enriched),
        "relevant": len([e for e in enriched if e["score"] > 0]),
        "items": enriched,
    }
    return report


def _to_markdown(report: dict) -> str:
    lines = [
        "# 정부 지원사업 레이더 보고서",
        "",
        f"- 생성: {report.get('generated_at')}",
        f"- 프로필: {report.get('profile')}",
        f"- 전체 {report.get('total')}건 / 적합 {report.get('relevant')}건",
        "",
        "| 적합도 | 마감 | 사업 | 담당자 | 링크 |",
        "|--------|------|------|--------|------|",
    ]
    for it in report.get("items", []):
        if it["score"] <= 0:
            continue
        lines.append(
            f"| {it['score']} | {it.get('dday') or it.get('deadline') or '-'} "
            f"| {it['title'][:50]} | {it.get('manager') or '-'} | {it['url']} |"
        )
    return "\n".join(lines)


def main() -> int:
    report = build_report()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report.get("ok"):
        REPORT_MD.write_text(_to_markdown(report), encoding="utf-8")
    print(f"[report] 저장: {REPORT_JSON} (relevant={report.get('relevant', 0)}/{report.get('total', 0)})")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
