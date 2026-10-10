"""스마트스토어 카테고리 캐시 모듈 (L3 Connector).

카테고리 목록을 CDP에서 한 번 추출해 JSON으로 저장.
이후 자동 등록 시 이름 검색 없이 ID로 직접 선택.

사용:
    # 1. 캐시 구축 (최초 1회 또는 갱신 시)
    result = build_cache(page)
    # {"ok": True, "count": 1234, "path": "data/smartstore/categories.json"}

    # 2. 이름으로 카테고리 ID 조회
    category_id = find_id("조명")         # "50001119"
    category_id = find_id("거실조명")      # "50003334"
    category_id = find_id("가구/인테리어>인테리어소품>조명>거실조명")  # full path

    # 3. Selectize에 ID 직접 주입 (검색 불필요)
    ok = set_by_id(page, category_id)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.logger import get_logger

_log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[4]
CACHE_PATH = data_dir() / "smartstore" / "categories.json"


# ══════════════════════════════════════════════════════════════════════════════
# 캐시 구축
# ══════════════════════════════════════════════════════════════════════════════


def build_cache(page) -> dict:
    """CDP 브라우저에서 전체 카테고리를 추출해 캐시 파일로 저장.

    Args:
        page: Playwright Page (products/create 페이지여야 함)

    Returns:
        {"ok": bool, "count": int, "path": str}
    """
    try:
        # Selectize에 빈 검색 트리거 → u.categories 로드
        page.evaluate("""
        (() => {
            const inp = document.querySelector("input[ng-model='vm.category']");
            const sel = inp?.selectize;
            if (sel) sel.onSearchChange('');
        })()
        """)
        time.sleep(1.0)

        cats = page.evaluate("""
        (() => {
            const inp = document.querySelector("input[ng-model='vm.category']");
            const sel = inp?.selectize;
            if (!sel) return null;
            // 빈 쿼리로 전체 옵션 로드
            sel.clearOptions();
            sel.settings.load.call(sel, '', () => {});
            return Object.values(sel.options || {})
                .filter(o => o && o.id && o.wholeCategoryName)
                .map(o => ({
                    id: String(o.id),
                    name: String(o.name || ''),
                    path: String(o.wholeCategoryName || ''),
                    level: Number(o.level || 0),
                    last: Boolean(o.lastLevel),
                    parent_id: o.parentId ? String(o.parentId) : null,
                }));
        })()
        """)
        time.sleep(0.5)

        if not cats:
            # fallback: Angular $http 서비스로 직접 호출
            cats = _fetch_via_angular(page)

        if not cats:
            return {"ok": False, "error": "카테고리 목록을 로드할 수 없습니다"}

        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cache = {
            "ok": True,
            "count": len(cats),
            "categories": cats,
            "built_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.info("[cat-cache] 캐시 구축 완료: %d개 → %s", len(cats), CACHE_PATH)
        return {"ok": True, "count": len(cats), "path": str(CACHE_PATH)}

    except Exception as e:  # noqa: BLE001 - 스마트스토어 카테고리 캐시 조회/구축 - 실패 시 빈 목록/False 반환
        _log.warning("[cat-cache] 구축 실패: %s", e)
        return {"ok": False, "error": str(e)[:120]}


def _fetch_via_angular(page) -> list | None:
    """Angular searchByIgnoreCase 서비스로 광범위 키워드 검색."""
    results = []
    keywords = ["", "가구", "의류", "식품", "전자", "스포츠", "조명", "주방", "유아"]
    seen_ids: set[str] = set()

    for kw in keywords:
        try:
            batch = page.evaluate(f"""
            (() => {{
                const inp = document.querySelector("input[ng-model='vm.category']");
                const sel = inp?.selectize;
                if (!sel) return [];
                // load 함수를 직접 실행
                const loaded = [];
                const origAdd = sel.addOption.bind(sel);
                sel.settings.load.call(sel, '{kw}', (opts) => {{
                    if (opts) loaded.push(...(Array.isArray(opts) ? opts : [opts]));
                }});
                return loaded.filter(o => o && o.id).map(o => ({{
                    id: String(o.id), name: String(o.name||''),
                    path: String(o.wholeCategoryName||''),
                    level: Number(o.level||0), last: Boolean(o.lastLevel),
                    parent_id: o.parentId ? String(o.parentId) : null,
                }}));
            }})()
            """)
            time.sleep(0.3)
            for c in batch or []:
                if c["id"] not in seen_ids:
                    seen_ids.add(c["id"])
                    results.append(c)
        except Exception:  # noqa: BLE001 - 스마트스토어 카테고리 캐시 조회/구축 - 실패 시 빈 목록/False 반환
            pass

    return results or None


# ══════════════════════════════════════════════════════════════════════════════
# 캐시 조회
# ══════════════════════════════════════════════════════════════════════════════


def load_cache() -> list[dict]:
    """캐시 파일에서 카테고리 목록 반환. 없으면 빈 리스트."""
    if not CACHE_PATH.exists():
        return []
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return data.get("categories", [])
    except Exception:  # noqa: BLE001 - 스마트스토어 카테고리 캐시 조회/구축 - 실패 시 빈 목록/False 반환
        return []


def find_id(name_or_path: str) -> str | None:
    """카테고리 이름 또는 경로로 ID 반환.

    검색 우선순위:
      1. 완전 일치 (name 또는 path)
      2. 경로 끝 단어 일치 (최말단 카테고리)
      3. path 포함 검색

    Args:
        name_or_path: "조명", "거실조명", "가구/인테리어>...>거실조명" 등

    Returns:
        category ID 문자열 또는 None
    """
    cats = load_cache()
    if not cats:
        return None

    q = name_or_path.strip()

    # 1. 완전 일치
    for c in cats:
        if c.get("name") == q or c.get("path") == q:
            return c["id"]

    # 2. 최말단 이름 일치 (마지막 > 이후)
    for c in cats:
        leaf = c.get("path", "").split(">")[-1].strip()
        if leaf == q:
            return c["id"]

    # 3. path 포함 + 최말단 우선
    candidates = [c for c in cats if q in c.get("path", "") or q in c.get("name", "")]
    if candidates:
        # 최말단(level 높은 것) 우선
        candidates.sort(key=lambda c: (-c.get("level", 0), len(c.get("path", ""))))
        return candidates[0]["id"]

    return None


def cache_info() -> dict:
    """캐시 상태 정보 반환."""
    if not CACHE_PATH.exists():
        return {"exists": False, "count": 0, "built_at": None}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return {
            "exists": True,
            "count": data.get("count", 0),
            "built_at": data.get("built_at"),
            "path": str(CACHE_PATH),
        }
    except Exception:  # noqa: BLE001 - 스마트스토어 카테고리 캐시 조회/구축 - 실패 시 빈 목록/False 반환
        return {"exists": False, "count": 0, "built_at": None}


# ══════════════════════════════════════════════════════════════════════════════
# Selectize ID 직접 주입
# ══════════════════════════════════════════════════════════════════════════════


def set_by_id(page, category_id: str) -> bool:
    """Selectize에 카테고리 ID를 직접 주입. 검색 과정 생략.

    Args:
        page:        Playwright Page
        category_id: 카테고리 ID 문자열

    Returns:
        성공 여부
    """
    try:
        result = page.evaluate(f"""
        (() => {{
            const inp = document.querySelector("input[ng-model='vm.category']");
            const sel = inp?.selectize;
            if (!sel) return false;

            const opt = sel.options['{category_id}'];
            if (!opt) {{
                // 옵션 없으면 추가 후 선택
                const dummy = {{
                    id: '{category_id}',
                    name: '{category_id}',
                    wholeCategoryName: '{category_id}',
                }};
                sel.addOption(dummy);
            }}
            sel.setValue('{category_id}');

            // Angular ng-model 동기화
            const scope = angular.element(inp).scope();
            if (scope) {{
                scope.$apply(() => {{
                    scope.vm && (scope.vm.category = '{category_id}');
                    scope.category = '{category_id}';
                }});
            }}
            return sel.getValue() === '{category_id}';
        }})()
        """)
        return bool(result)
    except Exception as e:  # noqa: BLE001 - 스마트스토어 카테고리 캐시 조회/구축 - 실패 시 빈 목록/False 반환
        _log.debug("[cat-cache] set_by_id 실패: %s", e)
        return False
