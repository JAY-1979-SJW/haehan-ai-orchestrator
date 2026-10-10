"""심층 사이트 맵 탐지 — 항목 클릭 후 모든 필드 자동 감지."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MailDetailInfo:
    """메일 상세 정보."""

    fields: dict = field(default_factory=dict)  # {field_name: selector_list}
    selectors: dict = field(default_factory=dict)  # {selector: count}
    sample_data: dict = field(default_factory=dict)


@dataclass
class CalendarEventInfo:
    """캘린더 이벤트 정보."""

    fields: dict = field(default_factory=dict)
    selectors: dict = field(default_factory=dict)
    sample_data: dict = field(default_factory=dict)


@dataclass
class MyBoxFileInfo:
    """MyBox 파일 정보."""

    fields: dict = field(default_factory=dict)
    selectors: dict = field(default_factory=dict)
    sample_data: dict = field(default_factory=dict)


def detect_mail_detail_fields(page) -> MailDetailInfo:
    """메일 상세 페이지에서 모든 필드 자동 탐지."""
    info = MailDetailInfo()

    try:
        # 일반적인 메일 필드 셀렉터
        field_patterns = {
            "from": [
                ".from",
                ".sender",
                "[class*='from']",
                "[data-from]",
                "span:contains('From')",
            ],
            "to": [
                ".to",
                ".recipient",
                "[class*='to']",
                "[data-to]",
                "span:contains('To')",
            ],
            "subject": [
                ".subject",
                "h1",
                "[class*='subject']",
                "[class*='title']",
                "h2",
            ],
            "body": [
                ".body",
                ".mail_content",
                "[class*='content']",
                "[class*='body']",
                ".mail_body",
            ],
            "date": [
                ".date",
                ".time",
                "[class*='date']",
                "[class*='time']",
                "time",
            ],
            "attachments": [
                ".attachment",
                ".attach_list",
                "[class*='attach']",
                "[class*='file']",
                "a[download]",
            ],
        }

        # 각 필드별로 실제 요소 탐지
        for field_name, selectors in field_patterns.items():
            found_selectors = {}
            for sel in selectors:
                try:
                    if sel.startswith("[data-"):
                        # data 속성 처리
                        elements = page.query_selector_all(sel)
                    elif "contains" in sel:
                        # :contains 대체 (XPath 사용)
                        xpath = f"//span[contains(text(), '{field_name.capitalize()}')]"
                        elements = page.query_selector_all(f"xpath={xpath}")
                    else:
                        elements = page.query_selector_all(sel)

                    if len(elements) > 0:
                        found_selectors[sel] = len(elements)
                except:  # noqa: S110, E722
                    pass

            if found_selectors:
                info.selectors[field_name] = found_selectors
                info.fields[field_name] = list(found_selectors.keys())

        # 샘플 데이터 추출
        try:
            sample = page.evaluate(
                """() => {
                return {
                    from: document.querySelector('.from')?.innerText || '',
                    to: document.querySelector('.to')?.innerText || '',
                    subject: document.querySelector('.subject, h1')?.innerText || '',
                    date: document.querySelector('.date, time')?.innerText || '',
                    body_length: document.querySelector('.body, [class*="content"]')?.innerText?.length || 0,
                    attachments: document.querySelectorAll('.attachment, [class*="attach"]').length || 0,
                };
            }"""
            )
            info.sample_data = sample
        except:  # noqa: S110, E722
            pass

        return info

    except Exception as e:  # noqa: BLE001 - 사이트 구조(메뉴/메일/캘린더/파일) 탐지 전용 읽기전용 도구 - 실패 시 빈 dict/기본값 반환, 실제 조작 없음
        print(f"  ✗ 필드 탐지 오류: {e}")
        return info


def detect_mail_inbox_structure(page) -> dict:
    """메일 목록 페이지에서 정확한 구조 탐지."""
    print("📍 메일 목록 구조 탐지...")

    try:
        # 메일 항목 셀렉터 자동 탐지
        selectors_to_try = [
            "li[data-mailsn]",
            "tr[data-mail-id]",
            ".mail_list_item",
            '[class*="mail_item"]',
            ".list_item",
            'li[class*="mail"]',
            'tr[class*="mail"]',
            '[role="listitem"]',
            "div[data-id]",
        ]

        found_mails = {}
        for sel in selectors_to_try:
            try:
                elements = page.query_selector_all(sel)
                if len(elements) > 0:
                    found_mails[sel] = len(elements)
            except:  # noqa: S110, E722
                pass

        if found_mails:
            print(f"  ✓ 메일 항목 셀렉터: {found_mails}")
            return {"mail_items": found_mails}
        else:
            print("  ✗ 메일 항목을 찾을 수 없음")
            # 대안: page 텍스트에서 메일 개수 확인
            text = page.content()
            import re

            mail_count = len(re.findall(r'href=["\'].*?/read/\d+', text))
            print(f"  📄 HTML에서 /read/ 링크 발견: {mail_count}개")
            return {"mail_links": mail_count}

    except Exception as e:  # noqa: BLE001 - 사이트 구조(메뉴/메일/캘린더/파일) 탐지 전용 읽기전용 도구 - 실패 시 빈 dict/기본값 반환, 실제 조작 없음
        print(f"  ✗ 구조 탐지 오류: {e}")
        return {}


def deep_detect_mail_service(page) -> dict:
    """네이버 메일 서비스 심층 탐지.

    1. 목록 페이지 → 구조 탐지
    2. 첫 메일 클릭
    3. 상세 페이지 → 모든 필드 탐지
    """
    print("\n" + "=" * 60)
    print("  네이버 메일 심층 탐지")
    print("=" * 60)

    result = {
        "service": "mail",
        "inbox_structure": {},
        "detail_structure": {},
        "auto_generated": True,
    }

    try:
        # 1. 메일 목록 구조 탐지
        print("\n1️⃣  메일 목록 페이지 분석...")
        inbox_struct = detect_mail_inbox_structure(page)
        result["inbox_structure"] = inbox_struct

        # 2. 첫 번째 메일 클릭
        print("\n2️⃣  첫 메일 열기...")
        try:
            # 메일 링크 찾기
            mail_link = page.query_selector('a[href*="/read/"]')
            if mail_link:
                mail_link.click()
                time.sleep(3)
                print("  ✓ 메일 상세 페이지 로드됨")

                # 3. 상세 페이지에서 필드 탐지
                print("\n3️⃣  상세 페이지 필드 탐지...")
                detail_info = detect_mail_detail_fields(page)

                result["detail_structure"] = {
                    "fields": detail_info.fields,
                    "selectors": detail_info.selectors,
                    "sample": detail_info.sample_data,
                }

                print(f"  ✓ {len(detail_info.fields)}개 필드 탐지됨")
                print(f"    필드: {list(detail_info.fields.keys())}")

            else:
                print("  ✗ 메일 링크를 찾을 수 없음")
                # 다른 방법 시도: iframe 내의 메일
                iframes = page.query_selector_all("iframe")
                if iframes:
                    print(f"  ℹ️  {len(iframes)}개 iframe 발견 (내용 접근 불가)")

        except Exception as e:  # noqa: BLE001 - 사이트 구조(메뉴/메일/캘린더/파일) 탐지 전용 읽기전용 도구 - 실패 시 빈 dict/기본값 반환, 실제 조작 없음
            print(f"  ✗ 메일 클릭 오류: {e}")

    except Exception as e:  # noqa: BLE001 - 사이트 구조(메뉴/메일/캘린더/파일) 탐지 전용 읽기전용 도구 - 실패 시 빈 dict/기본값 반환, 실제 조작 없음
        print(f"\n✗ 심층 탐지 실패: {e}")

    return result


def deep_detect_calendar_service(page) -> dict:
    """네이버 캘린더 심층 탐지."""
    print("\n" + "=" * 60)
    print("  네이버 캘린더 심층 탐지")
    print("=" * 60)

    result = {
        "service": "calendar",
        "event_structure": {},
        "auto_generated": True,
    }

    try:
        print("\n1️⃣  캘린더 이벤트 구조 탐지...")

        # 이벤트 셀렉터
        event_selectors = [
            '[class*="event"]',
            '[class*="schedule"]',
            '[role="button"][class*="event"]',
            ".calendar_item",
            "div[data-event]",
        ]

        found_events = {}
        for sel in event_selectors:
            try:
                elements = page.query_selector_all(sel)
                if len(elements) > 0:
                    found_events[sel] = len(elements)
            except:  # noqa: S110, E722
                pass

        if found_events:
            print(f"  ✓ 이벤트 셀렉터: {found_events}")
            result["event_structure"] = found_events
        else:
            print("  ✗ 이벤트를 찾을 수 없음")

    except Exception as e:  # noqa: BLE001 - 사이트 구조(메뉴/메일/캘린더/파일) 탐지 전용 읽기전용 도구 - 실패 시 빈 dict/기본값 반환, 실제 조작 없음
        print(f"  ✗ 캘린더 탐지 실패: {e}")

    return result


def deep_detect_mybox_service(page) -> dict:
    """네이버 MyBox 심층 탐지."""
    print("\n" + "=" * 60)
    print("  네이버 MyBox 심층 탐지")
    print("=" * 60)

    result = {
        "service": "mybox",
        "file_structure": {},
        "auto_generated": True,
    }

    try:
        print("\n1️⃣  파일 목록 구조 탐지...")

        file_selectors = [
            '[class*="file"]',
            '[class*="item"]',
            'tr[class*="file"]',
            'li[class*="file"]',
            "[data-file]",
            ".list_item",
        ]

        found_files = {}
        for sel in file_selectors:
            try:
                elements = page.query_selector_all(sel)
                if len(elements) > 0:
                    found_files[sel] = len(elements)
            except:  # noqa: S110, E722
                pass

        if found_files:
            print(f"  ✓ 파일 셀렉터: {found_files}")
            result["file_structure"] = found_files
        else:
            print("  ✗ 파일을 찾을 수 없음")

    except Exception as e:  # noqa: BLE001 - 사이트 구조(메뉴/메일/캘린더/파일) 탐지 전용 읽기전용 도구 - 실패 시 빈 dict/기본값 반환, 실제 조작 없음
        print(f"  ✗ MyBox 탐지 실패: {e}")

    return result


def main():
    """심층 탐지 실행."""
    from scripts.browser.agent.agent import BrowserAgent

    print("\n" + "=" * 70)
    print("  항목별 심층 사이트 맵 탐지")
    print("=" * 70)

    results = {}

    # 메일
    with BrowserAgent() as agent:
        agent.go("https://mail.naver.com/v2/folders/0/all")
        time.sleep(2)
        results["mail"] = deep_detect_mail_service(agent._page)

    # 캘린더
    with BrowserAgent() as agent:
        agent.go("https://calendar.naver.com/")
        time.sleep(2)
        results["calendar"] = deep_detect_calendar_service(agent._page)

    # MyBox
    with BrowserAgent() as agent:
        agent.go("https://mybox.naver.com/")
        time.sleep(2)
        results["mybox"] = deep_detect_mybox_service(agent._page)

    # 결과 저장
    cache_dir = Path(__file__).parent / ".deep_sitemap_cache"
    cache_dir.mkdir(exist_ok=True)

    for service, data in results.items():
        cache_file = cache_dir / f"{service}_deep.json"
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n💾 저장: {cache_file}")

    print("\n" + "=" * 70)
    print("  심층 탐지 완료")
    print("=" * 70 + "\n")

    return results


if __name__ == "__main__":
    main()
