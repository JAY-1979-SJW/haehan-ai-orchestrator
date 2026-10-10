"""Build a compact EUM capability catalog from accessible page exploration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.common.app_paths import repo_root

ROOT = repo_root()


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


DATA_DIR = _eum_dir()
ACCESSIBLE_PAGES = DATA_DIR / "eum_accessible_pages.json"
CAPABILITIES_FILE = DATA_DIR / "eum_capabilities.json"

ACTION_WORDS = {
    "search": ("조회", "검색"),
    "reset": ("초기화", "취소"),
    "excel": ("엑셀", "excel", "다운로드"),
    "create": ("등록", "추가", "신규"),
    "delete": ("삭제",),
    "save": ("저장",),
}


def _load_accessible_pages(path: Path = ACCESSIBLE_PAGES) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"accessible page map not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _web_code(url: str) -> str | None:
    upper = (url or "").upper()
    for marker in ("WEBMAN", "WEBCEN", "WEBMYP", "WEBJMA", "WEBFIR"):
        idx = upper.find(marker)
        if idx >= 0:
            return upper[idx : idx + 12]
    return None


def _visible(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("visible")]


def _action_flags(buttons: list[dict[str, Any]]) -> dict[str, bool]:
    joined = " ".join(
        f"{button.get('text', '')} {button.get('onclick', '')} {button.get('id', '')} {button.get('className', '')}"
        for button in buttons
    ).lower()
    return {action: any(word.lower() in joined for word in words) for action, words in ACTION_WORDS.items()}


def _classify_page(page: dict[str, Any]) -> str:
    title = str(page.get("title") or page.get("menuNm") or "")
    body = str(page.get("bodyTextSample") or "")
    text = f"{title} {body}"
    if "단말기" in text:
        return "terminal"
    if "퇴직공제" in text:
        return "retirement"
    if "구인" in text or "구직" in text or "훈련" in text:
        return "employment_training"
    if "공지" in text or "자료" in text or "매뉴얼" in text:
        return "content"
    if "마이페이지" in text or "회원" in text or "알림" in text:
        return "account"
    return "general"


def build_capabilities(accessible: dict[str, Any] | None = None) -> dict[str, Any]:
    source = accessible or _load_accessible_pages()
    capabilities = []

    for page in source.get("pages", []):
        if not page.get("ok"):
            continue
        inputs = _visible(page.get("inputs", []))
        buttons = _visible(page.get("buttons", []))
        tables = page.get("tables", [])
        headers = []
        for table in tables:
            headers.extend(table.get("headers", []))

        capabilities.append(
            {
                "menu_id": page.get("menuId"),
                "menu_name": page.get("menuNm"),
                "url": page.get("url"),
                "code": _web_code(str(page.get("url") or "")),
                "category": _classify_page(page),
                "input_count": len(inputs),
                "button_count": len(buttons),
                "table_count": len(tables),
                "actions": _action_flags(buttons),
                "inputs": inputs[:80],
                "buttons": buttons[:80],
                "table_headers": headers[:120],
            }
        )

    by_category: dict[str, int] = {}
    for item in capabilities:
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(ACCESSIBLE_PAGES),
        "page_count": len(capabilities),
        "by_category": by_category,
        "capabilities": capabilities,
    }


def save_capabilities(result: dict[str, Any], path: Path = CAPABILITIES_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def find_capability(query: str, path: Path = CAPABILITIES_FILE) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    q = query.strip().lower()
    for item in data.get("capabilities", []):
        values = [
            str(item.get("code") or ""),
            str(item.get("menu_name") or ""),
            str(item.get("url") or ""),
            str(item.get("menu_id") or ""),
        ]
        lowered = [v.lower() for v in values]
        if q in lowered or any(q in v for v in lowered):
            return item
    return None


def print_page_info(item: dict[str, Any] | None, query: str) -> bool:
    print("=" * 60)
    print("EUM page capability")
    print("=" * 60)
    print(f"query: {query}")
    if not item:
        print("not found")
        return False
    print(f"menu: {item.get('menu_name')}")
    print(f"code: {item.get('code') or '-'}")
    print(f"url: {item.get('url')}")
    print(f"category: {item.get('category')}")
    actions = ", ".join(k for k, v in item.get("actions", {}).items() if v)
    print(f"actions: {actions}")
    print(f"inputs: {item.get('input_count', 0)}")
    for field in item.get("inputs", [])[:20]:
        label = field.get("placeholder") or field.get("id") or field.get("name") or field.get("type")
        print(f"  - {field.get('tag')}[{field.get('type')}] {label}")
    print(f"tables: {item.get('table_count', 0)}")
    headers = [h for h in item.get("table_headers", []) if h]
    if headers:
        print("headers:", ", ".join(headers[:40]))
    return True


def print_summary(result: dict[str, Any], path: Path | None = None) -> None:
    print("=" * 60)
    print("EUM capability catalog")
    print("=" * 60)
    print(f"pages: {result.get('page_count', 0)}")
    print("categories:")
    for category, count in sorted(result.get("by_category", {}).items()):
        print(f"  - {category}: {count}")
    if path:
        print(f"saved: {path}")
    print("\nTerminal pages:")
    for item in result.get("capabilities", []):
        if item.get("category") == "terminal":
            actions = ", ".join(k for k, v in item.get("actions", {}).items() if v)
            print(
                f"  - {item.get('code') or '-'} {item.get('menu_name')} actions=[{actions}] tables={item.get('table_count')}"
            )
