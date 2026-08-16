"""카탈로그 페이지 이미지 → 제품 리스트 구조화 추출 (GPT-4o vision).

⚠️ 차단됨 (2026-08-16): 쿼터 초과로 실패 이력 있음 + 제품 그룹 분리를 정확히 못함.
남은 페이지는 Claude Code가 직접 이미지를 읽어 append_rows.py 로 채운다
(scripts/mk_catalog/append_rows.py 상단 주석 참고). 유료 API 재사용 금지.
이 함수를 다시 활성화하려면 사용자 사전 승인이 필요하다 (CLAUDE.md 참고).
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

_PROMPT = """당신은 조명 제품 카탈로그 페이지에서 정보를 추출하는 도구입니다.
이 페이지 이미지에 있는 모든 제품을 찾아 아래 JSON 형식으로만 출력하세요.
설명·마크다운·코드블록 없이 순수 JSON 배열만 출력하세요.

⚠️ 한 제품명 아래 색상별로 코드가 여러 개 나열된 경우(예: "블랙,화이트" 코드 1개 +
"골드" 코드 1개 + "크롬" 코드 1개), 이것들은 하나의 제품 그룹으로 묶고 variants 배열에
색상별 코드를 각각 넣으세요. 절대로 같은 제품을 여러 product 객체로 중복 생성하지 마세요.

각 제품 객체 필드:
- name: 제품명 전체 (굵은 글씨 제목, 색상 표기 제외)
- variants: [{"code": "999-999-999-999", "color": "블랙, 화이트"}, ...] — 코드-색상 쌍 목록.
  코드가 1개뿐이면 배열에 1개만 넣으세요.
- size: 규격 (예: W185×H180). 없으면 null
- led: 광원 정보 (예: GU10 (LED전용)). 없으면 null
- color_temp: 색온도 정보. 없으면 null
- features: 특징 리스트 (예: ["KS", "플리커프리", "현장 A/S 1년"])
- bbox: 이 제품의 "사진 영역만"(텍스트 제외) 페이지 내 위치를 0~1 비율로
  {"x0":0.0~1.0, "y0":0.0~1.0, "x1":0.0~1.0, "y1":0.0~1.0} 형식으로 추정.
  여러 색상 사진이 나란히 있으면 그 전체를 감싸는 사각형으로.
- category_tab: 페이지 왼쪽 세로 탭에 있는 카테고리명. 실제로 탭이 보일 때만 채우고,
  안 보이면 반드시 null (추측 금지).

제품이 하나도 없으면 빈 배열 []을 출력하세요.
"""


def _encode_image(image_path: str | Path) -> str:
    data = Path(image_path).read_bytes()
    return base64.b64encode(data).decode("ascii")


def _extract_json_array(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text).rstrip("```").strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"JSON 배열을 찾을 수 없음: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def extract_products_from_page(image_path: str | Path, *, page_label: str = "") -> dict:
    """카탈로그 페이지 1장에서 제품 리스트 추출.

    반환: {"ok": bool, "products": [...], "error": str}
    """
    raise RuntimeError(
        "vision_extract.extract_products_from_page 는 차단되었다 (2026-08-16). "
        "쿼터 초과 + 제품 그룹 오분리 이력으로 유료 GPT 비전 호출을 중단했다. "
        "남은 페이지는 Claude Code가 이미지를 직접 읽어 scripts/mk_catalog/append_rows.py 로 "
        "채운다. 재활성화하려면 사용자 사전 승인이 필요하다 (CLAUDE.md 참고)."
    )
