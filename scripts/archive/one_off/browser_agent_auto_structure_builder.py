"""사이트 구조 자동 파악 및 코드 생성 스크립트.

실행 순서:
  1. 사이트 방문 → 네트워크 요청 캡처
  2. DOM 구조 자동 분석 (목록/상세 구분)
  3. 항목 클릭 → 상세 구조 분석
  4. 분석 결과로 extract_*.js 자동 생성
  5. mixin 메서드 자동 생성

사용:
  python -m scripts.archive.one_off.browser_agent_auto_structure_builder mail
  python -m scripts.archive.one_off.browser_agent_auto_structure_builder calendar
  python -m scripts.archive.one_off.browser_agent_auto_structure_builder mybox
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ── 상수 ─────────────────────────────────────────────────────────────────────

SERVICES = {
    "mail": {
        "url": "https://mail.naver.com/v2/folders/0/all",
        "domain": "mail.naver.com",
        "item_hint": "mail",  # DOM 탐지 힌트
        "detail_hint": "read",  # 상세 URL 패턴
        "api_keyword": "mail",
        "mixin_class": "MailMixin",
        "mixin_file": "mail_mixin.py",
        "methods": ["list", "read", "search"],
    },
    "calendar": {
        "url": "https://calendar.naver.com/",
        "domain": "calendar.naver.com",
        "item_hint": "event|schedule",
        "detail_hint": "event",
        "api_keyword": "calendar",
        "mixin_class": "CalendarMixin",
        "mixin_file": "calendar_mixin.py",
        "methods": ["events", "today"],
    },
    "mybox": {
        "url": "https://mybox.naver.com/",
        "domain": "mybox.naver.com",
        "item_hint": "file|item",
        "detail_hint": "detail|view",
        "api_keyword": "mybox",
        "mixin_class": "MyBoxMixin",
        "mixin_file": "mybox_mixin.py",
        "methods": ["list", "quota"],
    },
}

REPO_ROOT = Path(__file__).resolve().parents[3]
JS_DIR = Path(__file__).parent / "_js"
MIXINS_DIR = Path(__file__).parent / "mixins"
CACHE_DIR = Path(__file__).parent / ".structure_cache"


# ── 데이터 구조 ───────────────────────────────────────────────────────────────


@dataclass
class NetworkRequest:
    method: str
    url: str
    resource_type: str


@dataclass
class DomField:
    name: str
    selector: str
    sample: str = ""
    count: int = 0


@dataclass
class PageStructure:
    service: str
    url: str
    list_selectors: list[dict] = field(default_factory=list)
    detail_selectors: list[dict] = field(default_factory=list)
    api_endpoints: list[str] = field(default_factory=list)
    captured_apis: list[dict] = field(default_factory=list)  # 실제 캡처된 API
    fields: dict[str, list[DomField]] = field(default_factory=dict)


# ── 네트워크 캡처 ─────────────────────────────────────────────────────────────


class NetworkCapture:
    """Playwright 네트워크 요청/응답 캡처."""

    def __init__(self):
        self.requests: list[dict] = []
        self.api_calls: list[dict] = []

    def attach(self, page):
        """페이지에 이벤트 리스너 부착."""
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def _on_request(self, request):
        url = request.url
        method = request.method
        resource_type = request.resource_type

        self.requests.append(
            {
                "url": url,
                "method": method,
                "type": resource_type,
            }
        )

        # API 요청만 별도 수집
        if resource_type in ("fetch", "xhr") or "/api/" in url or "/v2/" in url or "/v1/" in url:
            self.api_calls.append(
                {
                    "url": url,
                    "method": method,
                    "path": self._extract_path(url),
                }
            )

    def _on_response(self, response):
        # JSON 응답만 추적 (API 확인용)
        if "application/json" in (response.headers.get("content-type", "") or ""):
            url = response.url
            if url not in [r["url"] for r in self.api_calls]:
                self.api_calls.append(
                    {
                        "url": url,
                        "method": response.request.method,
                        "path": self._extract_path(url),
                        "status": response.status,
                    }
                )

    def _extract_path(self, url: str) -> str:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return parsed.path
        except Exception:  # noqa: BLE001 - 페이지 구조/필드 자동탐지 및 요소 클릭 헬퍼(읽기전용 탐지+단순 클릭) - 실패 시 빈 목록/False 반환; 파일 내 다른 except처럼 보이는 부분은 실제로는 코드 생성용 문자열 템플릿 내부 텍스트라 AST상 except가 아님
            return url

    def get_unique_api_paths(self) -> list[str]:
        seen = set()
        paths = []
        for call in self.api_calls:
            p = call["path"]
            if p not in seen:
                seen.add(p)
                paths.append(p)
        return sorted(paths)


# ── DOM 분석 ─────────────────────────────────────────────────────────────────

COMMON_FIELD_SELECTORS = {
    "from": [".from", ".sender", ".button_sender", '[class*="from"]'],
    "to": [".to", ".recipient", '[class*="to"]'],
    "subject": ["h1", ".subject", ".mail_title", '[class*="subject"]', '[class*="title"]'],
    "date": [".date", "time", ".mail_time", '[class*="date"]', '[class*="time"]'],
    "body": ['[class*="content"]', ".body", ".mail_body", "article", '[class*="message"]'],
    "name": [".name", ".title", '[class*="name"]', '[class*="title"]'],
    "size": [".size", '[class*="size"]', "[data-size]"],
    "type": [".type", ".ext", '[class*="type"]'],
    "start": ['[class*="start"]', "[data-start]", ".begin"],
    "end": ['[class*="end"]', "[data-end]", ".finish"],
    "location": ['[class*="location"]', ".place", "[data-location]"],
}

LIST_ITEM_PATTERNS = {
    "mail": ["li.mail_item", '[class*="mail_item"]', 'li[class*="mail"]', "tr.mail_list"],
    "calendar": ['[class*="event"]', '[class*="schedule"]', ".calendar_item", "[data-event]"],
    "mybox": ['[class*="file"]', '[class*="item"]', 'tr[class*="file"]', 'li[class*="item"]'],
}


def detect_list_structure(page, service: str) -> list[dict]:
    """목록 페이지에서 아이템 셀렉터 자동 탐지."""
    patterns = LIST_ITEM_PATTERNS.get(service, [])
    found = []

    for sel in patterns:
        try:
            result = page.evaluate(
                """(sel) => {
                const els = document.querySelectorAll(sel);
                if (els.length === 0) return null;
                const sample = els[0];
                return {
                    selector: sel,
                    count: els.length,
                    classes: sample.className,
                    attrs: Object.fromEntries(Object.entries(sample.dataset)),
                    sample_text: sample.innerText.substring(0, 100),
                };
            }""",
                sel,
            )
            if result:
                found.append(result)
        except Exception:  # noqa: S110, BLE001
            pass

    return found


def detect_fields_on_page(page) -> dict[str, list]:
    """현재 페이지에서 필드별 셀렉터 탐지."""
    results = {}

    for field_name, selectors in COMMON_FIELD_SELECTORS.items():
        found = []
        for sel in selectors:
            try:
                result = page.evaluate(
                    """(sel) => {
                    const els = document.querySelectorAll(sel);
                    if (els.length === 0) return null;
                    return {
                        selector: sel,
                        count: els.length,
                        sample: els[0]?.innerText?.trim().substring(0, 80) || '',
                    };
                }""",
                    sel,
                )
                if result:
                    found.append(result)
            except Exception:  # noqa: S110, BLE001
                pass

        if found:
            results[field_name] = found

    return results


def click_first_item(page, service: str, list_items: list[dict]) -> bool:
    """목록의 첫 번째 항목 클릭."""
    if not list_items:
        return False

    best = list_items[0]
    sel = best["selector"]

    try:
        # JavaScript로 클릭 (인터셉트 우회)
        clicked = page.evaluate(
            """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return false;
            // 클릭 가능한 링크/버튼 찾기
            const link = el.querySelector('a[href], button') || el;
            link.click();
            return true;
        }""",
            sel,
        )
        return clicked
    except Exception:  # noqa: BLE001 - 페이지 구조/필드 자동탐지 및 요소 클릭 헬퍼(읽기전용 탐지+단순 클릭) - 실패 시 빈 목록/False 반환; 파일 내 다른 except처럼 보이는 부분은 실제로는 코드 생성용 문자열 템플릿 내부 텍스트라 AST상 except가 아님
        return False


# ── JS 코드 생성 ──────────────────────────────────────────────────────────────


def generate_extract_js(service: str, mode: str, structure: PageStructure) -> str:
    """탐지된 구조로 extract_*.js 생성."""

    fields = structure.fields
    list_items = structure.list_selectors

    if mode == "list":
        # 목록 페이지 JS — fields["list"] 사용
        item_selector = list_items[0]["selector"] if list_items else '[class*="item"]'  # noqa: F841
        js_fields = []

        for fname, found in fields.get("list", {}).items():
            if not found or not isinstance(found, list):
                continue
            js_fields.append(f"""
      // {fname}
      let {fname} = '';
      for (const sel of {json.dumps([f["selector"] for f in found[:3]])}) {{
        const el = item.querySelector(sel);
        if (el?.innerText?.trim()) {{ {fname} = el.innerText.trim(); break; }}
      }}""")

        fields_str = (
            "\n".join(js_fields)
            if js_fields
            else """
      // ID (class 또는 href에서)
      let id = item.className.match(/(?:mail|event|file)-(\\d+)/)?.[1] || '';
      const link = item.querySelector('a[href]');
      if (!id && link) {
        id = link.href.match(/\\/(read|detail|view)\\/(\\d+)/)?.[2] || '';
      }
      let from = item.querySelector('.button_sender')?.innerText?.trim() || '';
      let subject = item.querySelector('[class*="title"] .text, h1')?.innerText?.trim() || '';
      let date = item.querySelector('[class*="date"]')?.innerText?.trim() || '';
      let unread = item.classList.contains('unread');"""
        )

        return f"""// 네이버 {service} 목록 추출 — auto_structure_builder 자동 생성
(function () {{
  const items = [];
  const itemSelectors = {json.dumps([s["selector"] for s in list_items[:3]])};

  let elements = [];
  for (const sel of itemSelectors) {{
    const found = document.querySelectorAll(sel);
    if (found.length > 0) {{ elements = Array.from(found); break; }}
  }}

  elements.forEach((item) => {{
    try {{{fields_str}

      // ID 추출
      let id = item.className.match(/(?:mail|event|item)-(\\d+)/)?.[1] || '';
      if (!id) {{
        const link = item.querySelector('a[href*="/read/"], a[href*="/view/"]');
        id = link?.href?.match(/\\/(\\d+)/)?.[1] || '';
      }}

      if (id || from || subject) {{
        items.push({{ id, from, subject, date, unread: Boolean(item.classList.contains('unread')) }});
      }}
    }} catch(e) {{}}
  }});

  return items;
}})();
"""

    else:
        # 상세 페이지 JS — fields["detail"] 사용
        detail_fields = []
        for fname, found in fields.get("detail", {}).items():
            if not found or not isinstance(found, list):
                continue
            sels = [f["selector"] for f in found[:3]]
            detail_fields.append(f"""
    // {fname}
    for (const sel of {json.dumps(sels)}) {{
      const el = document.querySelector(sel);
      if (el?.innerText?.trim()) {{ result.{fname} = el.innerText.trim(); break; }}
    }}""")

        detail_str = (
            "\n".join(detail_fields)
            if detail_fields
            else """
    result.subject = document.querySelector('h1, [class*="subject"]')?.innerText?.trim() || '';
    result.from = document.querySelector('.button_sender, [class*="from"]')?.innerText?.trim() || '';
    result.body = document.querySelector('[class*="content"], article')?.innerText?.trim() || '';
    result.date = document.querySelector('[class*="date"], time')?.innerText?.trim() || '';
    result.to = document.querySelector('[class*="to"]')?.innerText?.trim() || '';"""
        )

        return f"""// 네이버 {service} 상세 추출 — auto_structure_builder 자동 생성
(function () {{
  const result = {{
    subject: '', from: '', to: '', date: '', body: '', attachments: []
  }};

  try {{{detail_str}

    // 첨부파일
    document.querySelectorAll('.attachment, [class*="attach"], a[download]').forEach(att => {{
      const name = att.innerText?.trim() || att.getAttribute('download') || '';
      if (name) result.attachments.push({{ name, size: att.dataset.size || '' }});
    }});
  }} catch(e) {{}}

  return result;
}})();
"""


# ── Python 메서드 생성 ────────────────────────────────────────────────────────


def generate_mixin_methods(service: str, structure: PageStructure, config: dict) -> str:
    """탐지된 구조로 mixin 메서드 자동 생성."""

    cls = config["mixin_class"]
    url = config["url"]  # noqa: F841
    captured_apis = [c["path"] for c in structure.captured_apis[:5]]

    if service == "mail":
        return f'''"""네이버 메일 Mixin — auto_structure_builder 자동 생성."""
from __future__ import annotations

import time
from pathlib import Path


def _js(name: str) -> str:
    return (Path(__file__).parent.parent / "_js" / name).read_text(encoding="utf-8")


class {cls}:
    """네이버 메일 기능.

    실제 캡처된 API: {captured_apis}
    """

    def mail_inbox(self, max_n: int = 30) -> list[dict]:
        """받은 편지함 메일 목록.

        반환: [{{id, from, subject, date, unread}}]
        """
        self.go("https://mail.naver.com/v2/folders/0/all")
        time.sleep(2)
        try:
            result = self._page.evaluate(_js("extract_mail_inbox.js"))
            return (result or [])[:max_n]
        except Exception:
            return []

    def mail_read(self, mail_id: str) -> dict:
        """메일 상세 조회.

        반환: {{from, to, subject, date, body, attachments}}
        """
        self.go(f"https://mail.naver.com/v2/read/{{mail_id}}")
        time.sleep(2)
        try:
            return self._page.evaluate(_js("extract_mail_detail.js")) or {{}}
        except Exception:
            return {{}}

    def mail_search(self, query: str, max_n: int = 30) -> list[dict]:
        """메일 검색.

        반환: [{{id, from, subject, date, unread}}]
        """
        from urllib.parse import quote
        self.go(f"https://mail.naver.com/v2/search?q={{quote(query)}}")
        time.sleep(2)
        try:
            result = self._page.evaluate(_js("extract_mail_inbox.js"))
            return (result or [])[:max_n]
        except Exception:
            return []

    def mail_folders(self) -> list[dict]:
        """폴더 목록.

        반환: [{{name, count}}]
        """
        self.go("https://mail.naver.com/")
        time.sleep(2)
        try:
            return self._page.evaluate(_js("extract_mail_folders.js")) or []
        except Exception:
            return []

    def mail_unread_count(self) -> int:
        """안읽은 메일 수."""
        folders = self.mail_folders()
        for f in folders:
            if "받은" in f.get("name", ""):
                return f.get("count", 0)
        return 0

    def mail_send(self, to: str, subject: str, body: str) -> dict:
        """메일 발송 준비 (사용자 승인 필수).

        실제 발송은 사용자가 Chrome에서 직접 클릭.
        반환: {{ok, draft_url}}
        """
        from scripts.common.cdp_audit import L2
        self.go("https://mail.naver.com/v2/write")
        time.sleep(2)
        try:
            self._page.fill('[name="to"], [placeholder*="받는"]', to)
            self._page.fill('[name="subject"], [placeholder*="제목"]', subject)
            # 본문은 iframe 내에 있을 수 있음
            L2("MAIL_WRITE_PREPARED", "mail_mixin", to=to, subject=subject)
            return {{"ok": True, "draft_url": self._page.url}}
        except Exception as e:
            return {{"ok": False, "error": str(e)}}
'''

    elif service == "calendar":
        return f'''"""네이버 캘린더 Mixin — auto_structure_builder 자동 생성."""
from __future__ import annotations

import time
from pathlib import Path


def _js(name: str) -> str:
    return (Path(__file__).parent.parent / "_js" / name).read_text(encoding="utf-8")


class {cls}:
    """네이버 캘린더 기능.

    실제 캡처된 API: {captured_apis}
    """

    def calendar_events(self, start: str, end: str) -> list[dict]:
        """일정 목록 조회.

        Args:
            start: 시작일 "YYYY-MM-DD"
            end: 종료일 "YYYY-MM-DD"
        반환: [{{id, title, start, end, location}}]
        """
        date = start.replace("-", "")
        self.go(f"https://calendar.naver.com/")
        time.sleep(3)
        try:
            return self._page.evaluate(_js("extract_calendar_events.js")) or []
        except Exception:
            return []

    def calendar_today(self) -> list[dict]:
        """오늘 일정 조회."""
        from datetime import date
        today = date.today().isoformat()
        return self.calendar_events(today, today)

    def calendar_create(self, title: str, start: str, end: str) -> dict:
        """일정 생성 준비 (사용자 승인 필수).

        반환: {{ok, draft_url}}
        """
        from scripts.common.cdp_audit import L2
        self.go("https://calendar.naver.com/")
        time.sleep(2)
        L2("CALENDAR_WRITE_PREPARED", "calendar_mixin", title=title, start=start, end=end)
        return {{"ok": True, "draft_url": self._page.url}}
'''

    else:  # mybox
        return f'''"""네이버 MyBox Mixin — auto_structure_builder 자동 생성."""
from __future__ import annotations

import time
from pathlib import Path


def _js(name: str) -> str:
    return (Path(__file__).parent.parent / "_js" / name).read_text(encoding="utf-8")


class {cls}:
    """네이버 MyBox 기능.

    실제 캡처된 API: {captured_apis}
    """

    def mybox_list(self, path: str = "/") -> list[dict]:
        """파일/폴더 목록 조회.

        반환: [{{name, type, size, mtime}}]
        """
        self.go("https://mybox.naver.com/main/web/my")
        time.sleep(2)
        try:
            return self._page.evaluate(_js("extract_mybox_list.js")) or []
        except Exception:
            return []

    def mybox_quota(self) -> dict:
        """용량 정보 조회.

        반환: {{used, total, unit}}
        """
        self.go("https://mybox.naver.com/main/web/my")
        time.sleep(2)
        try:
            return self._page.evaluate("""() => {{
                const el = document.querySelector('[class*="quota"], [class*="storage"]');
                return {{ raw: el?.innerText?.trim() || '' }};
            }}""") or {{}}
        except Exception:
            return {{}}
'''


# ── 메인 실행 ─────────────────────────────────────────────────────────────────


def _print_detected_fields(fields: dict) -> None:
    for fname, found in fields.items():
        print(f"  ✓ {fname:10s}: {found[0]['selector']} ({found[0]['count']}개, '{found[0]['sample'][:30]}')")


def _detect_with_browser(service_name: str, config: dict, structure: PageStructure, capture: NetworkCapture) -> list:
    """브라우저를 띄워 목록/상세 구조를 탐지하고 목록 셀렉터 후보를 반환."""
    from scripts.browser.agent.agent import BrowserAgent

    with BrowserAgent() as agent:
        # 네트워크 캡처 시작
        capture.attach(agent._page)

        # 1. 목록 페이지 로드
        print(f"1️⃣  [{service_name}] 목록 페이지 로드: {config['url']}")
        agent.go(config["url"])
        time.sleep(3)
        print(f"  ✓ URL: {agent._page.url}\n")

        # 2. 목록 구조 탐지
        print("2️⃣  목록 구조 탐지...")
        list_items = detect_list_structure(agent._page, service_name)
        structure.list_selectors = list_items
        for item in list_items[:3]:
            print(f"  ✓ {item['selector']} → {item['count']}개 (샘플: {item.get('sample_text', '')[:40]})")
        if not list_items:
            print("  ✗ 목록 항목을 찾을 수 없음\n")

        # 3. 필드 탐지 (목록 페이지)
        print("\n3️⃣  목록 페이지 필드 탐지...")
        fields_list = detect_fields_on_page(agent._page)
        structure.fields["list"] = fields_list
        _print_detected_fields(fields_list)

        # 4. 항목 클릭 → 상세 페이지
        print("\n4️⃣  첫 항목 클릭 → 상세 구조 탐지...")
        clicked = click_first_item(agent._page, service_name, list_items)

        if clicked:
            time.sleep(3)
            detail_url = agent._page.url
            print(f"  ✓ 상세 URL: {detail_url}\n")

            # 상세 페이지 필드 탐지
            fields_detail = detect_fields_on_page(agent._page)
            structure.fields["detail"] = fields_detail
            _print_detected_fields(fields_detail)
        else:
            print("  ✗ 상세 페이지 클릭 실패\n")
    return list_items


def _save_structure_cache(service_name: str, structure: PageStructure) -> Path:
    cache_file = CACHE_DIR / f"{service_name}_structure.json"
    with cache_file.open("w", encoding="utf-8") as f:
        # PageStructure를 직렬화
        data = {
            "service": structure.service,
            "url": structure.url,
            "list_selectors": structure.list_selectors,
            "api_endpoints": structure.api_endpoints[:20],
            "captured_apis": structure.captured_apis[:20],
            "fields": {k: v for k, v in structure.fields.items()},
        }
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 구조 캐시: {cache_file}")
    return cache_file


def _js_file_plan(service_name: str) -> list[tuple[str, str]]:
    if service_name == "mail":
        return [
            ("extract_mail_inbox.js", "list"),
            ("extract_mail_detail.js", "detail"),
        ]
    if service_name == "calendar":
        return [
            ("extract_calendar_events.js", "list"),
        ]
    return [
        ("extract_mybox_list.js", "list"),
    ]


def run(service_name: str):
    """서비스 구조 자동 파악 및 코드 생성."""
    if service_name not in SERVICES:
        print(f"❌ 알 수 없는 서비스: {service_name}")
        print(f"   가능한 서비스: {list(SERVICES.keys())}")
        return

    config = SERVICES[service_name]
    CACHE_DIR.mkdir(exist_ok=True)

    print(f"\n{'=' * 65}")
    print(f"  {service_name.upper()} 사이트 구조 자동 탐지 및 코드 생성")
    print(f"{'=' * 65}\n")

    structure = PageStructure(service=service_name, url=config["url"])
    capture = NetworkCapture()

    list_items = _detect_with_browser(service_name, config, structure, capture)

    # 5. 캡처된 API 정리
    api_paths = capture.get_unique_api_paths()
    structure.captured_apis = capture.api_calls[:30]
    structure.api_endpoints = api_paths

    print(f"\n5️⃣  캡처된 API 엔드포인트 ({len(api_paths)}개):")
    for path in api_paths[:10]:
        print(f"  → {path}")

    # 6. 결과 캐시 저장
    cache_file = _save_structure_cache(service_name, structure)

    # 7. extract_*.js 자동 생성
    print("\n6️⃣  JS 파일 자동 생성...")
    JS_DIR.mkdir(exist_ok=True)

    js_files = _js_file_plan(service_name)

    for js_name, mode in js_files:
        js_code = generate_extract_js(service_name, mode, structure)
        js_path = JS_DIR / js_name
        js_path.write_text(js_code, encoding="utf-8")
        print(f"  ✓ 생성: {js_path.name}")

    # 8. mixin 메서드 자동 생성
    print("\n7️⃣  Mixin 메서드 자동 생성...")
    mixin_code = generate_mixin_methods(service_name, structure, config)
    mixin_path = MIXINS_DIR / config["mixin_file"]
    mixin_path.write_text(mixin_code, encoding="utf-8")
    print(f"  ✓ 생성: {mixin_path.name}")

    # 9. 완료 요약
    print(f"\n{'=' * 65}")
    print(f"  [{service_name.upper()}] 자동 생성 완료 요약")
    print(f"{'=' * 65}")
    print(f"  ✓ 구조 캐시: {cache_file.name}")
    print(f"  ✓ JS 파일: {[f[0] for f in js_files]}")
    print(f"  ✓ Mixin: {config['mixin_file']}")
    print(f"  ✓ 캡처된 API: {len(api_paths)}개")
    print(f"  ✓ 목록 셀렉터: {len(list_items)}개")
    print(f"{'=' * 65}\n")


def main():
    """CLI 진입점."""
    services = sys.argv[1:] if len(sys.argv) > 1 else ["mail", "calendar", "mybox"]

    for service in services:
        run(service)


if __name__ == "__main__":
    main()
