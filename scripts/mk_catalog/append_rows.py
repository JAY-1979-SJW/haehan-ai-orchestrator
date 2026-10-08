"""판독한 제품 행을 CSV 에 추가 (중복 코드는 갱신).

배경 (2026-08-15):
    pipeline.py 가 외부 유료 비전 API 로 p2~p283 만 추출하고 쿼터 초과로 중단됐다.
    남은 220쪽(p127, p284~p502)은 **Claude Code 가 직접 페이지를 읽어** 채운다.
    유료 API 를 쓰지 않으므로 비용이 들지 않는다.

왜 append 도구가 필요한가:
    220쪽을 한 번에 처리하면 중간에 끊겼을 때 전부 잃는다.
    페이지 단위로 즉시 저장해 재시작 가능하게 한다.

제품코드 구조 (실측으로 확정):
    299-001-244-400
    └┬┘ └┬┘ └──┬──┘
     │   │     └─ 공급가 244,400원   (1,651건 100% 일치)
     │   └─────── 페이지 내 순번
     └─────────── 카탈로그 페이지번호 (1,643건 99.5% 일치)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # 단독 실행 시에도 scripts 패키지를 import 할 수 있게
    sys.path.insert(0, str(ROOT))
from scripts.common.app_paths import known_folder  # noqa: E402

OUT = ROOT / "data" / "mk_catalog" / "products_manual.csv"

FIELDS = [
    "name",
    "code",
    "supply_price",
    "color",
    "size",
    "led",
    "color_temp",
    "features",
    "file_page",
    "source_file",
]

_SRC = str(known_folder("downloads") / "MK12_페이지별" / "MK12_p{page}.pdf")


def price_from_code(code: str) -> str:
    """코드 뒤 6자리가 공급가다. 형식이 다르면 빈 값(추측하지 않는다)."""
    parts = (code or "").split("-")
    if len(parts) != 4:
        return ""
    try:
        return str(int(parts[2] + parts[3]))
    except ValueError:
        return ""


def page_from_code(code: str) -> str:
    """코드 첫 3자리가 카탈로그 페이지번호. 파일 페이지는 +1."""
    parts = (code or "").split("-")
    if not parts:
        return ""
    try:
        return str(int(parts[0]) + 1)
    except ValueError:
        return ""


def load_existing() -> dict[str, dict]:
    if not OUT.exists():
        return {}
    with OUT.open(encoding="utf-8", newline="") as f:
        return {r["code"]: r for r in csv.DictReader(f) if r.get("code")}


def append(rows: list[dict]) -> dict:
    """rows: {name, code, size, led, color, color_temp, features} 부분집합 허용."""
    existing = load_existing()
    added = updated = skipped = 0

    for r in rows:
        code = (r.get("code") or "").strip()
        if not code:
            skipped += 1
            continue
        fp = r.get("file_page") or page_from_code(code)
        rec = {
            "name": (r.get("name") or "").strip(),
            "code": code,
            "supply_price": r.get("supply_price") or price_from_code(code),
            "color": (r.get("color") or "").strip(),
            "size": (r.get("size") or "").strip(),
            "led": (r.get("led") or "").strip(),
            "color_temp": (r.get("color_temp") or "").strip(),
            "features": (r.get("features") or "").strip(),
            "file_page": fp,
            "source_file": r.get("source_file") or _SRC.format(page=str(fp).zfill(3)),
        }
        if code in existing:
            updated += 1
        else:
            added += 1
        existing[code] = rec

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for code in sorted(existing):
            w.writerow({k: existing[code].get(k, "") for k in FIELDS})

    pages = sorted(
        {r["file_page"] for r in existing.values() if r.get("file_page")},
        key=lambda x: int(x) if str(x).isdigit() else 0,
    )
    return {"added": added, "updated": updated, "skipped": skipped, "total": len(existing), "pages": len(pages)}


def main() -> None:
    """stdin 으로 JSON 배열을 받는다."""
    rows = json.load(sys.stdin)
    print(json.dumps(append(rows), ensure_ascii=False))


if __name__ == "__main__":
    main()
