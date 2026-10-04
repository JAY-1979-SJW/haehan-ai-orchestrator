"""MK 카탈로그 전체 페이지 → 제품 메타데이터(CSV) 배치 추출.

사진 크롭 자동화는 정확도 문제로 보류(수동 검증 필요, detail_page_template.py 참고).
이 파이프라인은 텍스트 메타데이터(제품명/코드/공급가/규격)만 501페이지 전체에서 추출한다.

사용:
    python -m scripts.mk_catalog.pipeline --dir "<MK12 JPG 폴더>" --out data/mk_catalog/products.csv

산출:
    {out}         — 제품 1행 = variant 1개 (코드 1개당 1행), 공급가 파싱 포함
    {out}.errors.jsonl — 추출 실패/제품 0건 페이지 로그
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path

from .pricing import InvalidCodeError, parse_price
from .vision_extract import extract_products_from_page

_PAGE_NUM_RE = re.compile(r"p0*(\d+)", re.IGNORECASE)

CSV_FIELDS = [
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


def _file_page_number(path: Path) -> str:
    m = _PAGE_NUM_RE.search(path.stem)
    return m.group(1) if m else path.stem


def _flatten(products: list[dict], file_page: str, source_file: str) -> list[dict]:
    rows = []
    for p in products:
        name = p.get("name") or ""
        size = p.get("size") or ""
        led = p.get("led") or ""
        color_temp = p.get("color_temp") or ""
        if isinstance(color_temp, list):
            color_temp = ", ".join(color_temp)
        features = p.get("features") or []
        if isinstance(features, list):
            features = ", ".join(str(f) for f in features)

        variants = p.get("variants") or []
        if not variants and p.get("code"):
            variants = [{"code": p["code"], "color": p.get("color", "")}]

        for v in variants:
            code = (v.get("code") or "").strip()
            price = ""
            if code:
                try:
                    price = parse_price(code)
                except InvalidCodeError:
                    price = ""
            rows.append(
                {
                    "name": name,
                    "code": code,
                    "supply_price": price,
                    "color": v.get("color", ""),
                    "size": size,
                    "led": led,
                    "color_temp": color_temp,
                    "features": features,
                    "file_page": file_page,
                    "source_file": source_file,
                }
            )
    return rows


def run_pipeline(catalog_dir: str, out_csv: str, *, limit: int | None = None, sleep_s: float = 0.5) -> dict:
    """카탈로그 폴더의 모든 페이지 이미지을 순회하며 제품 메타데이터 CSV를 누적 생성.

    이미 처리된(out_csv에 file_page가 존재하는) 페이지는 건너뛰어 중단 후 재실행 가능.
    """
    src_dir = Path(catalog_dir)
    out_path = Path(out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    err_path = out_path.with_suffix(out_path.suffix + ".errors.jsonl")

    done_pages: set[str] = set()
    if out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done_pages.add(row["file_page"])

    write_header = not out_path.exists()
    pages = sorted(src_dir.glob("MK12_p*.jpg"), key=lambda p: int(_file_page_number(p)))
    if limit:
        pages = pages[:limit]

    total_rows = 0
    processed = 0
    skipped = 0
    errors = 0

    with out_path.open("a", newline="", encoding="utf-8") as fcsv, err_path.open("a", encoding="utf-8") as ferr:
        writer = csv.DictWriter(fcsv, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()

        for path in pages:
            file_page = _file_page_number(path)
            if file_page in done_pages:
                skipped += 1
                continue

            result = extract_products_from_page(path, page_label=file_page)
            if not result.get("ok"):
                errors += 1
                ferr.write(
                    json.dumps(
                        {"file_page": file_page, "source_file": str(path), "error": result.get("error")},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                ferr.flush()
                time.sleep(sleep_s)
                continue

            rows = _flatten(result["products"], file_page, str(path))
            for row in rows:
                writer.writerow(row)
            fcsv.flush()
            total_rows += len(rows)
            processed += 1
            time.sleep(sleep_s)

    return {
        "processed_pages": processed,
        "skipped_pages": skipped,
        "error_pages": errors,
        "total_rows": total_rows,
        "out_csv": str(out_path),
        "err_log": str(err_path),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="카탈로그 페이지 이미지 폴더")
    ap.add_argument("--out", default="data/mk_catalog/products.csv")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    result = run_pipeline(args.dir, args.out, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
