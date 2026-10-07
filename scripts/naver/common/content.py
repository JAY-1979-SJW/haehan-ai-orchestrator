"""Naver blog/cafe exploration and gated writing helpers."""

from __future__ import annotations

import contextlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login
from scripts.naver.common.live_safety import ensure_page_safe, throttle_live
from scripts.site_engine.catalog_helpers import print_keyed_summary, select_named_targets
from scripts.site_engine.site_session_safety import assert_session_integrity

_log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"

CONTENT_TARGETS: dict[str, dict[str, str]] = {
    "blog": {
        "label": "Naver Blog",
        "url": "https://blog.naver.com/",
    },
    "blog_admin": {
        "label": "Naver Blog Admin",
        "url": "https://admin.blog.naver.com/",
    },
    "cafe": {
        "label": "Naver Cafe",
        "url": "https://section.cafe.naver.com/ca-fe/home/recent-articles",
    },
}

LATEST_SURFACE_PATH = DATA_DIR / "naver_blog_cafe_surfaces_latest.json"
LATEST_ACTION_CATALOG_PATH = DATA_DIR / "naver_blog_cafe_action_catalog_latest.json"
LATEST_CAFE_WRITE_PLAN_PATH = DATA_DIR / "naver_cafe_write_plan_latest.json"
LATEST_CAFE_SUBMIT_RECORD_PATH = DATA_DIR / "naver_cafe_submit_latest.json"
CAFE_SUBMIT_DIR = DATA_DIR / "naver_cafe_submits"

APPROVAL_CONFIRM_TEXT = "NAVER_APPROVED_PUBLISH"

SENSITIVE_INPUT_TOKENS = {
    "password",
    "passwd",
    "pwd",
    "otp",
    "token",
    "secret",
    "cookie",
    "session",
    "cert",
    "key",
    "인증",
    "비밀번호",
    "암호",
    "토큰",
}

STATE_CHANGE_BUTTON_TOKENS = {
    "발행",
    "등록",
    "저장",
    "수정",
    "삭제",
    "보내",
    "전송",
    "댓글",
    "답글",
    "초대",
    "이웃",
    "가입",
    "탈퇴",
    "확인",
    "publish",
    "submit",
    "save",
    "delete",
    "send",
    "comment",
    "reply",
    "invite",
}

READ_BUTTON_TOKENS = {
    "검색",
    "조회",
    "보기",
    "목록",
    "닫기",
    "취소",
    "새로고침",
    "이전",
    "다음",
    "search",
    "view",
    "list",
    "close",
    "cancel",
    "refresh",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _contains_any(text: str, tokens: set[str]) -> bool:
    lowered = text.lower()
    return any(token.lower() in lowered for token in tokens)


def select_targets(name: str | None = None) -> dict[str, dict[str, str]]:
    return select_named_targets(CONTENT_TARGETS, name, "Naver content target")


def open_naver_content(page, url: str) -> None:
    result = ensure_naver_login(page, return_url=url)
    assert_session_integrity(result, site="naver", workflow="content_explore")
    if not result.get("ok"):
        raise RuntimeError(f"naver login failed: {result}")
    ensure_page_safe(page, site="naver", workflow="content_explore", phase="before_navigation")
    throttle_live("naver", workflow="content_explore")
    if not (page.url or "").startswith(url):
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
    # 페이지 이동 후 대기(wait_for_timeout) 실패 무시 — 읽기전용 탐색의 best-effort 대기
    with contextlib.suppress(Exception):
        page.wait_for_timeout(1500)
    ensure_page_safe(page, site="naver", workflow="content_explore", phase="after_navigation")


def extract_surface(page, *, limit: int = 120) -> dict[str, Any]:
    """Extract visible structure only."""
    ensure_page_safe(page, site="naver", workflow="content_explore", phase="before_surface_extract")
    return page.evaluate(
        """(limit) => {
          const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
          const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
          const links = Array.from(document.querySelectorAll('a[href]')).map((el) => ({
            text: clean(el.innerText || el.textContent).slice(0, 160),
            href: el.href || '',
            visible: visible(el)
          })).filter((x) => x.visible && (x.text || x.href)).slice(0, limit);
          const buttons = Array.from(document.querySelectorAll('button, [role=button]')).map((el, index) => ({
            index,
            text: clean(el.innerText || el.textContent || el.getAttribute('aria-label')).slice(0, 120),
            type: el.getAttribute('type') || '',
            visible: visible(el),
            disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true'
          })).filter((x) => x.visible && x.text).slice(0, limit);
          const inputs = Array.from(document.querySelectorAll('input, textarea, select, [contenteditable=true]')).map((el, index) => ({
            index,
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            name: el.name || '',
            id: el.id || '',
            placeholder: el.placeholder || '',
            aria: el.getAttribute('aria-label') || '',
            visible: visible(el),
            disabled: !!el.disabled,
            readonly: !!el.readOnly
          })).filter((x) => x.visible).slice(0, limit);
          return {
            url: location.href,
            title: document.title,
            counts: {
              links: document.querySelectorAll('a[href]').length,
              buttons: document.querySelectorAll('button, [role=button]').length,
              inputs: document.querySelectorAll('input, textarea, select, [contenteditable=true]').length,
              forms: document.querySelectorAll('form').length,
              iframes: document.querySelectorAll('iframe').length
            },
            links,
            buttons,
            inputs
          };
        }""",
        limit,
    )


def scan_target(page, key: str, target: dict[str, str], *, limit: int = 120) -> dict[str, Any]:
    open_naver_content(page, target["url"])
    return {
        "key": key,
        "label": target["label"],
        "target_url": target["url"],
        "scanned_at": _now(),
        "surface": extract_surface(page, limit=limit),
    }


def save_surface_report(results: list[dict[str, Any]], output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_SURFACE_PATH
    path.write_text(
        json.dumps({"generated_at": _now(), "targets": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_surface_report(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path else LATEST_SURFACE_PATH
    return json.loads(source.read_text(encoding="utf-8"))


def _classify_input(field: dict[str, Any]) -> dict[str, Any]:
    probe = " ".join(_clean(field.get(k)) for k in ("type", "name", "id", "placeholder", "aria"))
    sensitive = _clean(field.get("type")).lower() == "file" or _contains_any(probe, SENSITIVE_INPUT_TOKENS)
    return {
        "risk": "blocked_sensitive" if sensitive else "prepare",
        "can_auto_fill": not sensitive and not field.get("disabled") and not field.get("readonly"),
        "reason": "sensitive_or_file_input" if sensitive else "explicit_value_required",
    }


def _classify_button(button: dict[str, Any]) -> dict[str, Any]:
    text = _clean(button.get("text"))
    probe = " ".join(_clean(button.get(k)) for k in ("text", "type", "id", "name", "aria"))
    if button.get("disabled"):
        return {"risk": "disabled", "can_auto_click": False, "reason": "disabled"}
    if _contains_any(probe, STATE_CHANGE_BUTTON_TOKENS):
        return {"risk": "submit_gated", "can_auto_click": False, "reason": "state_change_keyword"}
    if text and _contains_any(probe, READ_BUTTON_TOKENS):
        return {"risk": "read", "can_auto_click": False, "reason": "read_control_cataloged_only"}
    return {"risk": "unknown_gated", "can_auto_click": False, "reason": "unclassified_button"}


def build_action_catalog(surface_report: dict[str, Any] | None = None) -> dict[str, Any]:
    report = surface_report or load_surface_report()
    targets = []
    for target in report.get("targets") or []:
        key = target.get("key")
        surface = target.get("surface") or {}
        inputs = []
        for idx, field in enumerate(surface.get("inputs") or []):
            meta = _classify_input(field)
            inputs.append(
                {
                    "control_id": f"{key}:input:{idx}",
                    "index": idx,
                    "field_key": _clean(
                        field.get("name")
                        or field.get("id")
                        or field.get("placeholder")
                        or field.get("aria")
                        or f"field_{idx}"
                    ),
                    "tag": field.get("tag") or "",
                    "type": field.get("type") or "",
                    "name": field.get("name") or "",
                    "id": field.get("id") or "",
                    "placeholder": field.get("placeholder") or "",
                    "aria": field.get("aria") or "",
                    **meta,
                }
            )
        buttons = []
        for idx, button in enumerate(surface.get("buttons") or []):
            meta = _classify_button(button)
            buttons.append(
                {
                    "control_id": f"{key}:button:{idx}",
                    "index": button.get("index", idx),
                    "text": _clean(button.get("text")),
                    **meta,
                }
            )
        targets.append(
            {
                "key": key,
                "label": target.get("label"),
                "target_url": target.get("target_url"),
                "surface_url": surface.get("url"),
                "title": surface.get("title"),
                "counts": surface.get("counts") or {},
                "inputs": inputs,
                "buttons": buttons,
                "summary": {
                    "input_total": len(inputs),
                    "button_total": len(buttons),
                    "auto_fillable_inputs": sum(1 for item in inputs if item["can_auto_fill"]),
                    "submit_gated_buttons": sum(1 for item in buttons if item["risk"] == "submit_gated"),
                    "unknown_gated_buttons": sum(1 for item in buttons if item["risk"] == "unknown_gated"),
                },
            }
        )
    return {
        "generated_at": _now(),
        "source_generated_at": report.get("generated_at"),
        "contract": {
            "explore": "read-only",
            "prepare": "explicit values only",
            "publish": f"requires --approved and --confirm={APPROVAL_CONFIRM_TEXT}",
        },
        "targets": targets,
    }


def save_action_catalog(catalog: dict[str, Any], output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_ACTION_CATALOG_PATH
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_cafe_write_plan(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
    *,
    cafe_url: str,
    board_no: str,
    title: str,
    body: str,
    publish: bool = False,
    approved_by: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    return {
        "generated_at": _now(),
        "workflow": "cafe_write",
        "cafe_url": cafe_url,
        "board_no": str(board_no),
        "title": title,
        "body_len": len(body or ""),
        "publish_requested": publish,
        "approval": {
            "required": bool(publish),
            "approved_by": approved_by,
            "confirm_text_required": APPROVAL_CONFIRM_TEXT,
        },
        "dry_run": dry_run,
        "prepared": False,
        "published": False,
    }


def save_cafe_write_plan(plan: dict[str, Any], output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_CAFE_WRITE_PLAN_PATH
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_cafe_submit_record(record: dict[str, Any], output: str | Path | None = None) -> Path:
    CAFE_SUBMIT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(output) if output else CAFE_SUBMIT_DIR / f"naver_cafe_submit_{stamp}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST_CAFE_SUBMIT_RECORD_PATH.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from scripts.common.realtime_audit import emit_event

        emit_event(
            "NAVER_CAFE_PUBLISH_EXECUTED" if record.get("published") else "NAVER_CAFE_WRITE_PREPARED",
            site="naver",
            workflow="cafe_write",
            status="ok" if record.get("ok", True) else "failed",
            risk="send" if record.get("publish_requested") else "prepare",
            message="Naver cafe write workflow recorded",
            artifact_path=str(path),
            metadata={"cafe_url": record.get("cafe_url"), "dry_run": record.get("dry_run")},
        )
    except Exception:  # noqa: BLE001 - 페이지 이동 후 대기(wait_for_timeout) 타임아웃 무시, 탐색 로그 저장 실패 무시 — 읽기전용 탐색의 best-effort 로깅
        pass
    return path


def print_surface_summary(results: list[dict[str, Any]], path: Path | None = None) -> None:
    print("=" * 60)
    print("Naver blog/cafe surfaces")
    print("=" * 60)
    for result in results:
        surface = result.get("surface") or {}
        counts = surface.get("counts") or {}
        print(
            f"- {result.get('key')}: title={surface.get('title')} "
            f"links={counts.get('links', 0)} buttons={counts.get('buttons', 0)} "
            f"inputs={counts.get('inputs', 0)} iframes={counts.get('iframes', 0)}"
        )
    if path:
        print(f"saved: {path}")


def print_action_summary(catalog: dict[str, Any], path: Path | None = None) -> None:
    print_keyed_summary(
        "Naver blog/cafe action catalog",
        catalog.get("targets") or [],
        (
            ("inputs", "input_total"),
            ("buttons", "button_total"),
            ("submit_gated", "submit_gated_buttons"),
            ("unknown_gated", "unknown_gated_buttons"),
        ),
        path,
    )
