"""페이지 동적 로드 분석 및 메뉴 구조 자동 매핑.

지원 기능:
  - JavaScript 로드 완료 대기
  - 동적 콘텐츠 감시
  - 메뉴 구조 자동 매핑
  - 페이지 계층 구조 분석
"""

from __future__ import annotations

import time
from typing import Any

from scripts.common.logger import get_logger

_log = get_logger(__name__)


def wait_for_js_load(page, timeout_s: float = 10.0, stable_time_s: float = 2.0) -> dict[str, Any]:
    """JavaScript 로드 완료 대기.

    Args:
        page: Playwright Page
        timeout_s: 최대 대기 시간
        stable_time_s: DOM이 안정적인 시간

    Returns:
        {
            loaded: bool,
            elapsed_s: float,
            final_item_count: int,
            changes_detected: int,
        }
    """
    try:
        start = time.time()
        last_count = 0
        change_count = 0
        last_change_time = start

        while time.time() - start < timeout_s:
            # 현재 DOM 요소 개수
            current_count = page.evaluate("() => document.querySelectorAll('*').length")

            if current_count != last_count:
                change_count += 1
                last_change_time = time.time()
                last_count = current_count
                _log.debug("[page-analyzer] DOM 변화: %d개 요소", current_count)

            # stable_time 이상 변화 없으면 로드 완료
            if time.time() - last_change_time >= stable_time_s:
                elapsed = time.time() - start
                _log.info("[page-analyzer] JS 로드 완료 (%.1f초, %d개 변화)", elapsed, change_count)
                return {
                    "loaded": True,
                    "elapsed_s": elapsed,
                    "final_item_count": current_count,
                    "changes_detected": change_count,
                }

            time.sleep(0.5)

        elapsed = time.time() - start
        _log.warning("[page-analyzer] JS 로드 타임아웃 (%.1f초)", elapsed)
        return {
            "loaded": False,
            "elapsed_s": elapsed,
            "final_item_count": last_count,
            "changes_detected": change_count,
            "timeout": True,
        }

    except Exception as e:  # noqa: BLE001 - 페이지 구조(메뉴/테이블/완성도) 분석 읽기전용 도구 - 실패 시 에러 정보를 담은 기본 dict 반환
        _log.error("[page-analyzer] JS 로드 감시 실패: %s", e)
        return {
            "loaded": False,
            "error": str(e),
        }


def detect_menu_structure(page) -> dict[str, Any]:
    """페이지의 메뉴 구조 자동 감지.

    Returns:
        {
            menus: [
                {text, href, level, visible, hasSubmenu}
            ],
            structure: {
                type: "nav" | "sidebar" | "dropdown" | "unknown",
                links_count: int,
            }
        }
    """
    try:
        result = page.evaluate("""
        (() => {
            const menus = [];

            // 네비게이션 선택자 (우선순위 순)
            const navSelectors = [
                'nav',
                '[role="navigation"]',
                '.nav',
                '.navbar',
                '.menu',
                '.sidebar',
                'header',
            ];

            let navElement = null;
            for (const sel of navSelectors) {
                navElement = document.querySelector(sel);
                if (navElement) break;
            }

            if (!navElement) {
                return { menus: [], structure: { type: 'unknown', links_count: 0 } };
            }

            // 모든 링크 추출
            const links = navElement.querySelectorAll('a');
            links.forEach(a => {
                const text = (a.innerText || '').trim().substring(0, 50);
                const href = a.getAttribute('href') || '';
                const style = window.getComputedStyle(a);
                const visible = style.display !== 'none' && style.visibility !== 'hidden';

                // 계층 레벨 판단
                let level = 0;
                let parent = a.parentElement;
                while (parent && parent !== navElement && level < 5) {
                    if (parent.tagName.match(/^(LI|UL|OL|DIV)$/)) level++;
                    parent = parent.parentElement;
                }

                menus.push({
                    text,
                    href,
                    level,
                    visible,
                    hasSubmenu: a.querySelector('ul, [role="submenu"]') !== null,
                });
            });

            // 메뉴 타입 판단
            let type = 'unknown';
            if (navElement.tagName === 'NAV') type = 'nav';
            else if (navElement.classList.contains('sidebar')) type = 'sidebar';
            else if (navElement.classList.contains('navbar')) type = 'nav';
            else if (navElement.querySelector('[role="submenu"]')) type = 'dropdown';

            return {
                menus,
                structure: {
                    type,
                    links_count: menus.length,
                }
            };
        })();
        """)

        _log.info(
            "[page-analyzer] 메뉴 감지: %d개 링크, 유형: %s",
            result["structure"]["links_count"],
            result["structure"]["type"],
        )

        return result

    except Exception as e:  # noqa: BLE001 - 페이지 구조(메뉴/테이블/완성도) 분석 읽기전용 도구 - 실패 시 에러 정보를 담은 기본 dict 반환
        _log.error("[page-analyzer] 메뉴 감지 실패: %s", e)
        return {
            "menus": [],
            "structure": {"type": "unknown", "links_count": 0},
            "error": str(e),
        }


def extract_table_data(page) -> dict[str, Any]:
    """페이지의 모든 테이블 데이터 추출.

    Returns:
        {
            tables: [
                {
                    index: int,
                    headers: [str],
                    rows: [[str]],
                    row_count: int,
                }
            ],
            total_tables: int,
        }
    """
    try:
        result = page.evaluate("""
        (() => {
            const tables = [];
            const tableElements = document.querySelectorAll('table');

            tableElements.forEach((table, idx) => {
                // 헤더 추출
                const headers = [];
                const headerCells = table.querySelectorAll('thead th, thead td');
                headerCells.forEach(cell => {
                    headers.push((cell.innerText || '').trim());
                });

                // 행 데이터 추출
                const rows = [];
                const bodyRows = table.querySelectorAll('tbody tr');
                bodyRows.forEach(tr => {
                    const row = [];
                    const cells = tr.querySelectorAll('td');
                    cells.forEach(cell => {
                        row.push((cell.innerText || '').trim());
                    });
                    if (row.length > 0) rows.push(row);
                });

                if (headers.length > 0 || rows.length > 0) {
                    tables.push({
                        index: idx,
                        headers,
                        rows: rows.slice(0, 10),  // 처음 10행만
                        row_count: rows.length,
                        visible: table.offsetParent !== null,
                    });
                }
            });

            return {
                tables,
                total_tables: tableElements.length,
                extracted_count: tables.length,
            };
        })();
        """)

        _log.info("[page-analyzer] 테이블 추출: %d개 (총 %d개)", result["extracted_count"], result["total_tables"])

        return result

    except Exception as e:  # noqa: BLE001 - 페이지 구조(메뉴/테이블/완성도) 분석 읽기전용 도구 - 실패 시 에러 정보를 담은 기본 dict 반환
        _log.error("[page-analyzer] 테이블 추출 실패: %s", e)
        return {
            "tables": [],
            "total_tables": 0,
            "error": str(e),
        }


def analyze_page_completeness(page) -> dict[str, Any]:
    """페이지 로드 완성도 분석.

    Returns:
        {
            is_complete: bool,
            completeness_score: float,  # 0-100
            missing_elements: [str],
            recommendations: [str],
        }
    """
    try:
        result = page.evaluate("""
        (() => {
            const checks = {
                hasContent: document.body.innerText.length > 100,
                hasImages: document.querySelectorAll('img').length > 0,
                hasLinks: document.querySelectorAll('a').length > 0,
                hasButtons: document.querySelectorAll('button, [role="button"]').length > 0,
                hasNav: document.querySelector('nav, [role="navigation"]') !== null,
                noEmptyElements: document.querySelectorAll('div:empty, p:empty').length < 10,
                loadingIndicators: document.querySelectorAll('[class*="load"], [class*="spin"]').length === 0,
            };

            const completed = Object.values(checks).filter(v => v).length;
            const score = (completed / Object.keys(checks).length) * 100;

            return {
                checks,
                score: Math.round(score),
                missing: Object.entries(checks)
                    .filter(([_, v]) => !v)
                    .map(([k, _]) => k),
            };
        })();
        """)

        missing_elements = {
            "hasContent": "페이지 콘텐츠 부족",
            "hasImages": "이미지 없음",
            "hasLinks": "링크 없음",
            "hasButtons": "버튼 없음",
            "hasNav": "네비게이션 없음",
            "loadingIndicators": "로딩 상태",
        }

        recommendations = [missing_elements[m] for m in result["missing"] if m in missing_elements]

        is_complete = result["score"] >= 70

        _log.info("[page-analyzer] 완성도: %d%% %s", result["score"], "(완료)" if is_complete else "(진행 중)")

        return {
            "is_complete": is_complete,
            "completeness_score": result["score"],
            "missing_elements": result["missing"],
            "recommendations": recommendations,
        }

    except Exception as e:  # noqa: BLE001 - 페이지 구조(메뉴/테이블/완성도) 분석 읽기전용 도구 - 실패 시 에러 정보를 담은 기본 dict 반환
        _log.error("[page-analyzer] 완성도 분석 실패: %s", e)
        return {
            "is_complete": False,
            "completeness_score": 0,
            "error": str(e),
        }


def full_page_analysis(page, wait_for_load: bool = True) -> dict[str, Any]:
    """페이지 종합 분석.

    Returns:
        {
            js_load: dict,
            completeness: dict,
            menu: dict,
            tables: dict,
            recommendations: [str],
        }
    """
    try:
        _log.info("[page-analyzer] 페이지 종합 분석 시작: %s", page.url)

        results = {}

        # 1. JS 로드 대기
        if wait_for_load:
            results["js_load"] = wait_for_js_load(page)
        else:
            results["js_load"] = {"skipped": True}

        # 2. 완성도 분석
        results["completeness"] = analyze_page_completeness(page)

        # 3. 메뉴 구조 분석
        results["menu"] = detect_menu_structure(page)

        # 4. 테이블 추출
        results["tables"] = extract_table_data(page)

        # 5. 권장사항
        recommendations = results["completeness"].get("recommendations", [])
        results["recommendations"] = recommendations

        _log.info(
            "[page-analyzer] 분석 완료: 점수=%d%%, 메뉴=%d개, 테이블=%d개",
            results["completeness"]["completeness_score"],
            results["menu"]["structure"]["links_count"],
            results["tables"]["total_tables"],
        )

        return results

    except Exception as e:  # noqa: BLE001 - 페이지 구조(메뉴/테이블/완성도) 분석 읽기전용 도구 - 실패 시 에러 정보를 담은 기본 dict 반환
        _log.error("[page-analyzer] 종합 분석 실패: %s", e)
        return {
            "error": str(e),
        }
