"""CSV/Excel → 스마트스토어 일괄 등록.

표준 컬럼 (한글/영문 모두 지원):
  name|상품명, price|판매가, stock|재고, category|카테고리,
  brand|브랜드, manufacturer|제조사, model_name|모델명,
  main_image|대표이미지, description|상세설명, vat_type|부가세,
  product_status|상품상태, minor_purchase|미성년자, gift|사은품,
  event_text|이벤트문구

사용:
  from scripts.naver.smartstore.automation.csv_import import CSVImporter
  ci = CSVImporter(page)
  result = ci.import_csv("data/products.csv", save_after=False)
  result = ci.import_excel("data/products.xlsx")
"""

from __future__ import annotations

import csv
from pathlib import Path

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


COLUMN_ALIASES = {
    # 한글 → 영문
    "상품명": "name",
    "판매가": "price",
    "가격": "price",
    "재고": "stock",
    "재고수량": "stock",
    "수량": "stock",
    "카테고리": "category",
    "브랜드": "brand",
    "제조사": "manufacturer",
    "모델명": "model_name",
    "모델": "model_name",
    "대표이미지": "main_image",
    "이미지": "main_image",
    "상세설명": "description",
    "설명": "description",
    "부가세": "vat_type",
    "상품상태": "product_status",
    "미성년자": "minor_purchase",
    "사은품": "gift",
    "이벤트문구": "event_text",
}


def normalize_row(row: dict) -> dict:
    """CSV row의 한글 컬럼명을 영문으로 정규화 + 타입 변환."""
    out = {}
    for k, v in row.items():
        if not k or v is None or v == "":
            continue
        key = COLUMN_ALIASES.get(k.strip(), k.strip())
        # 타입 변환
        if key in ("price", "stock"):
            try:
                v = int(str(v).replace(",", "").strip())
            except (ValueError, TypeError):
                continue
        elif key == "minor_purchase":
            v = str(v).strip().lower() in ("true", "1", "y", "yes", "가능")
        out[key] = v
    return out


class CSVImporter:
    """CSV/Excel 파일 → 스마트스토어 일괄 등록."""

    def __init__(self, page: Page):
        self.page = page

    def parse_csv(self, csv_path: str) -> list[dict]:
        """CSV → list[dict] (한글 컬럼 정규화)."""
        path = Path(csv_path)
        if not path.exists():
            return []
        products = []
        # UTF-8 BOM 또는 cp949 자동 감지
        for encoding in ("utf-8-sig", "utf-8", "cp949"):
            try:
                with path.open(encoding=encoding, newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        normalized = normalize_row(row)
                        if normalized.get("name"):
                            products.append(normalized)
                break
            except UnicodeDecodeError:
                continue
        _log.info("[csv-import] %s에서 %d개 행 파싱", csv_path, len(products))
        return products

    def parse_excel(self, xlsx_path: str, sheet: str | int = 0) -> list[dict]:
        """Excel → list[dict] (openpyxl 필요)."""
        try:
            import openpyxl
        except ImportError:
            _log.error("[csv-import] openpyxl 미설치 — pip install openpyxl")
            return []

        wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
        try:
            ws = wb[sheet] if isinstance(sheet, str) else wb.worksheets[sheet]
            rows = list(ws.iter_rows(values_only=True))
        finally:
            wb.close()
        if not rows:
            return []
        headers = [str(h).strip() if h else "" for h in rows[0]]
        products = []
        for row in rows[1:]:
            row_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
            normalized = normalize_row(row_dict)
            if normalized.get("name"):
                products.append(normalized)
        return products

    def import_csv(
        self,
        csv_path: str,
        product_type: str = "general",
        save_after: bool = False,
        require_confirm: bool = False,
        max_retries: int = 2,
        dry_run: bool = False,
    ) -> dict:
        """CSV 파일 → 일괄 등록.

        dry_run=True: 파싱만 (등록 X)
        """
        products = self.parse_csv(csv_path)
        if not products:
            return {"ok": False, "error": "empty_or_invalid_csv", "file": csv_path}

        log_critical(
            "DATA_IMPORT",
            f"CSV 일괄 등록 시작: {Path(csv_path).name}",
            file=csv_path,
            count=len(products),
            dry_run=dry_run,
            mode="csv_import_start",
        )

        if dry_run:
            return {"ok": True, "dry_run": True, "parsed": len(products), "preview": products[:3]}

        from scripts.naver.smartstore.bulk import BulkRegister

        br = BulkRegister(self.page)
        return br.register_all(
            products,
            product_type=product_type,
            save_after=save_after,
            require_confirm=require_confirm,
            max_retries=max_retries,
        )

    def import_excel(self, xlsx_path: str, sheet: str | int = 0, **kwargs) -> dict:
        """Excel 파일 → 일괄 등록."""
        products = self.parse_excel(xlsx_path, sheet=sheet)
        if not products:
            return {"ok": False, "error": "empty_or_invalid_excel"}

        if kwargs.get("dry_run"):
            return {"ok": True, "dry_run": True, "parsed": len(products), "preview": products[:3]}

        from scripts.naver.smartstore.bulk import BulkRegister

        br = BulkRegister(self.page)
        return br.register_all(products, **{k: v for k, v in kwargs.items() if k != "dry_run"})
