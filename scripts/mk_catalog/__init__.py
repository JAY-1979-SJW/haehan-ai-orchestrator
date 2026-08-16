"""MK company 조명 카탈로그 → 스마트스토어 상품 데이터 추출 파이프라인.

배경: 카탈로그(약 2000개 제품, 페이지 이미지)에서 제품명/코드/스펙을 비전모델로
추출하고, 제품코드 마지막 6자리(공급가, 사업자 확인됨)를 파싱해 매입가 DB를 만든다.

## 확정된 사실 (2026-07-17 사업자 확인)
- 제품코드 마지막 6자리 = 업체 공급가 (예: 422-001-019-800 → 19,800원)
- 판매가는 마진율 미정 — 이 파이프라인은 매입가까지만 산출, 판매가는 별도 결정

## 모듈
- pricing.py       — 코드 → 공급가 파싱
- vision_extract.py — 페이지 이미지 → 제품 리스트(JSON) 추출 (GPT-4o vision)
- pipeline.py       — 여러 페이지 순회 → CSV 산출
"""

from .pipeline import run_pipeline
from .pricing import parse_price
from .vision_extract import extract_products_from_page

__all__ = ["extract_products_from_page", "parse_price", "run_pipeline"]
