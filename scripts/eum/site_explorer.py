"""EUM 사이트 전체 탐색 및 메뉴/페이지 구조 추출.

로그인 후 메인 페이지에서 메뉴 구조를 추출하고,
각 WEBMAN 페이지를 순차 방문해 테이블·폼·버튼 구조를 기록한다.

결과: data/eum_site_map.json

사용:
    python scripts/eum/site_explorer.py
"""

from __future__ import annotations

import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from scripts.common.logger import get_logger  # noqa: E402
from scripts.common.op_log import op_context  # noqa: E402

log = get_logger(__name__)

EUM_BASE = "https://eum.cw.or.kr"


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


DATA_DIR = _eum_dir()

# 탐색 대상 WEBMAN 페이지 목록
WEBMAN_PAGES = [
    {"code": "WEBMAN370M00", "name": "설치안내대상", "url": f"{EUM_BASE}/web/man/WEBMAN370M00"},
    {"code": "WEBMAN380M00", "name": "현장별단말기목록", "url": f"{EUM_BASE}/web/man/WEBMAN380M00"},
    {"code": "WEBMAN381M00", "name": "단말기설치계획", "url": f"{EUM_BASE}/web/man/WEBMAN381M00"},
    {"code": "WEBMAN382M00", "name": "단말기철거", "url": f"{EUM_BASE}/web/man/WEBMAN382M00"},
    {"code": "WEBMAN390M00", "name": "단말기설치현황", "url": f"{EUM_BASE}/web/man/WEBMAN390M00"},
    {"code": "WEBMAN400M00", "name": "단말기이력관리", "url": f"{EUM_BASE}/web/man/WEBMAN400M00"},
]


def _extract_nav_links(page) -> list[dict]:
    """메인 페이지 네비게이션 링크 전체 추출."""
    try:
        links = page.evaluate("""
            () => {
                const anchors = document.querySelectorAll('nav a, .menu a, .gnb a, .lnb a, #nav a, #menu a, header a');
                return Array.from(anchors).map(a => ({
                    text: a.innerText.trim(),
                    href: a.href,
                    id: a.id || '',
                    cls: a.className || ''
                })).filter(l => l.text && l.href && !l.href.startsWith('javascript'));
            }
        """)
        return links or []
    except Exception as e:  # noqa: BLE001 - EUM 사이트 구조 읽기전용 탐색기(nav/table/form/button 추출) - 실패시 빈 리스트/dict 반환 또는 debug 로그만 남김, 쓰기 없음
        log.debug("nav 링크 추출 실패: %s", e)
        return []


def _extract_page_structure(page, url: str) -> dict:
    """단일 페이지의 구조 정보 추출 (테이블·폼·버튼·필터)."""
    info: dict = {
        "url": url,
        "final_url": page.url,
        "title": "",
        "accessible": True,
        "tables": [],
        "forms": [],
        "buttons": [],
        "selects": [],
        "error": "",
    }

    # EUM 사이트 구조 읽기전용 탐색기 - 실패시 title 빈 문자열로 유지, 쓰기 없음
    with contextlib.suppress(Exception):
        info["title"] = page.title()

    # 접근 제한 여부 확인
    try:
        body_text = page.inner_text("body")
        if any(kw in body_text for kw in ["접근", "권한", "로그인", "제한", "denied", "403"]):
            if "로그아웃" not in body_text:  # 로그아웃 버튼이 있으면 정상 접근
                info["accessible"] = False
                info["error"] = "접근 제한 또는 권한 없음"
    except Exception:  # noqa: BLE001 - EUM 사이트 구조 읽기전용 탐색기(nav/table/form/button 추출) - 실패시 빈 리스트/dict 반환 또는 debug 로그만 남김, 쓰기 없음
        pass

    if not info["accessible"]:
        return info

    # 테이블 구조 추출
    try:
        tables = page.evaluate("""
            () => {
                const tbls = document.querySelectorAll('table');
                return Array.from(tbls).map((t, idx) => {
                    const rows = t.querySelectorAll('tr');
                    const headers = [];
                    if (rows.length > 0) {
                        const ths = rows[0].querySelectorAll('th');
                        ths.forEach(th => headers.push(th.innerText.trim()));
                    }
                    return {
                        index: idx,
                        row_count: rows.length,
                        headers: headers,
                        id: t.id || '',
                        cls: t.className || ''
                    };
                });
            }
        """)
        info["tables"] = tables or []
    except Exception as e:  # noqa: BLE001 - EUM 사이트 구조 읽기전용 탐색기(nav/table/form/button 추출) - 실패시 빈 리스트/dict 반환 또는 debug 로그만 남김, 쓰기 없음
        log.debug("테이블 추출 실패: url=%s err=%s", url, e)

    # 폼 구조 추출
    try:
        forms = page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('form')).map((f, idx) => ({
                    index: idx,
                    id: f.id || '',
                    action: f.action || '',
                    method: f.method || '',
                    input_names: Array.from(f.querySelectorAll('input')).map(i => i.name || i.id || i.type)
                }));
            }
        """)
        info["forms"] = forms or []
    except Exception as e:  # noqa: BLE001 - EUM 사이트 구조 읽기전용 탐색기(nav/table/form/button 추출) - 실패시 빈 리스트/dict 반환 또는 debug 로그만 남김, 쓰기 없음
        log.debug("폼 추출 실패: url=%s err=%s", url, e)

    # 버튼 추출
    try:
        buttons = page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn, a[class*="btn"]');
                return Array.from(btns).slice(0, 20).map(b => ({
                    text: b.innerText?.trim() || b.value || '',
                    type: b.type || b.tagName,
                    id: b.id || '',
                    cls: b.className || ''
                })).filter(b => b.text);
            }
        """)
        info["buttons"] = buttons or []
    except Exception as e:  # noqa: BLE001 - EUM 사이트 구조 읽기전용 탐색기(nav/table/form/button 추출) - 실패시 빈 리스트/dict 반환 또는 debug 로그만 남김, 쓰기 없음
        log.debug("버튼 추출 실패: url=%s err=%s", url, e)

    # select 필터 추출
    try:
        selects = page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('select')).map(s => ({
                    id: s.id || '',
                    name: s.name || '',
                    options: Array.from(s.options).slice(0, 10).map(o => o.text.trim())
                }));
            }
        """)
        info["selects"] = selects or []
    except Exception as e:  # noqa: BLE001 - EUM 사이트 구조 읽기전용 탐색기(nav/table/form/button 추출) - 실패시 빈 리스트/dict 반환 또는 debug 로그만 남김, 쓰기 없음
        log.debug("select 추출 실패: url=%s err=%s", url, e)

    return info


def explore_site(page) -> dict:
    """로그인된 page로 EUM 전체 사이트 탐색.

    Returns:
        탐색 결과 dict
    """
    result: dict[str, Any] = {
        "explored_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": EUM_BASE,
        "nav_links": [],
        "webman_pages": [],
        "extra_links": [],
    }

    with op_context("eum_site_explore", base=EUM_BASE):
        # 메인 페이지 이동 + 네비게이션 링크 수집
        log.info("메인 페이지 탐색 시작")
        try:
            page.goto(f"{EUM_BASE}/main", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:  # noqa: BLE001 - EUM 사이트 구조 읽기전용 탐색기(nav/table/form/button 추출) - 실패시 빈 리스트/dict 반환 또는 debug 로그만 남김, 쓰기 없음
            log.warning("메인 페이지 이동 실패: %s", e)

        nav_links = _extract_nav_links(page)
        result["nav_links"] = nav_links
        log.info("네비게이션 링크 수집: %d개", len(nav_links))

        # 메인 페이지에서 발견된 추가 링크 중 WEBMAN 관련
        for link in nav_links:
            href = link.get("href", "")
            if "WEBMAN" in href and href not in [p["url"] for p in WEBMAN_PAGES]:
                result["extra_links"].append(link)

        # 각 WEBMAN 페이지 순차 방문
        for page_info in WEBMAN_PAGES:
            code = page_info["code"]
            name = page_info["name"]
            url = page_info["url"]

            log.info("WEBMAN 페이지 탐색: %s (%s)", code, name)

            try:
                page.goto(url, timeout=15000)
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception as e:  # noqa: BLE001 - EUM 사이트 구조 읽기전용 탐색기(nav/table/form/button 추출) - 실패시 빈 리스트/dict 반환 또는 debug 로그만 남김, 쓰기 없음
                log.warning("페이지 이동 실패: url=%s err=%s", url, e)
                result["webman_pages"].append(
                    {
                        **page_info,
                        "accessible": False,
                        "error": str(e),
                        "tables": [],
                        "forms": [],
                        "buttons": [],
                        "selects": [],
                    }
                )
                continue

            structure = _extract_page_structure(page, url)
            entry = {**page_info, **structure}
            result["webman_pages"].append(entry)

            accessible = structure.get("accessible", True)
            table_count = len(structure.get("tables", []))
            log.info(
                "  %s: 접근=%s 테이블=%d개 버튼=%d개", code, accessible, table_count, len(structure.get("buttons", []))
            )

    return result


def main() -> None:
    """CLI 실행: 사이트 탐색 후 JSON 저장."""
    from scripts.eum.auth import is_logged_in, login
    from scripts.browser.cdp.connection import get_page

    print("=" * 60)
    print("EUM 전체 사이트 탐색")
    print("=" * 60)

    page = get_page()

    # 로그인 확인 및 자동 로그인
    if not is_logged_in(page):
        print("로그인 필요 — 자동 로그인 시도 중...")
        res = login(page)
        if not res["ok"]:
            print(f"✘ 로그인 실패: {res['reason']}")
            return
        print(f"✔ 로그인 성공: {res['user']}")
    else:
        print("✔ 기존 세션 사용")

    # 탐색 실행
    result = explore_site(page)

    # 저장
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "eum_site_map.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 요약 출력
    print(f"\n탐색 완료: {result['explored_at']}")
    print(f"네비게이션 링크: {len(result['nav_links'])}개")
    print()
    print("WEBMAN 페이지 결과:")
    for p in result["webman_pages"]:
        status = "접근가능" if p.get("accessible", True) else "접근제한"
        tables = len(p.get("tables", []))
        print(f"  [{status}] {p['code']} ({p['name']}) — 테이블 {tables}개")

    print(f"\n저장 완료: {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
