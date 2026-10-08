"""인스타그램 마케팅 파이프라인 — big.sun2024(반딧불 전파사) 계정 전용.

네이버 블로그 스킬(scripts/naver/blog/marketing/)과 동일한 3분리 구조:
  cases.py    — 이미지 소스에서 시공사례 그룹핑 + 중복 발행 방지
  caption.py  — 캡션 생성 (제품 + 대표 경력/자격 + 연락처 + 위치 + 해시태그)
  publish.py  — CDP 업로드 + 발행 (항상 사용자 확인 후 confirmed=True로만 실제 발행)

이미지 원본: C:\\work\\전등 이미지\\gonobi_images_v2\\{카테고리}\\{log_no}_NN_설명.jpg
"""

from __future__ import annotations

from pathlib import Path

from scripts.common.app_paths import onedrive_root, resolve_external

TARGET_IG_ACCOUNT = "big.sun2024"
IMAGE_ROOT = resolve_external("HAEHAN_LIGHTING_IMAGE_DIR", "전등 이미지", "gonobi_images_v2", base=onedrive_root())
CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "instagram_post_cache.json"
MAX_CAROUSEL = 10
