"""네이버 라우터 공용 유틸리티 및 게이트 함수"""
from __future__ import annotations

import json

from scripts.common.gate import check as gate_check


def _option_value(args: list[str], prefix: str) -> str | None:
    for arg in args:
        text = str(arg)
        if text.startswith(prefix):
            return text.split("=", 1)[1]
    return None


def _option_phrase(args: list[str], prefix: str) -> str | None:
    for idx, arg in enumerate(args):
        text = str(arg)
        if not text.startswith(prefix):
            continue
        parts = [text.split("=", 1)[1]]
        for rest in args[idx + 1:]:
            rest_text = str(rest)
            if rest_text.startswith("--"):
                break
            parts.append(rest_text)
        return " ".join(part for part in parts if part).strip()
    return None


def _flag(args: list[str], name: str) -> bool:
    return name in args


def _int_option(args: list[str], prefix: str, default: int) -> int:
    value = _option_value(args, prefix)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"{prefix}<int> required") from exc


def _save_latest(name: str, payload: dict) -> str:
    from pathlib import Path

    path = Path("data") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _print_saved(payload: dict, path: str) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _parse_datetime_arg(value: str, field: str):
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"{field} must be ISO datetime, example: 2026-05-13T15:00:00") from exc


def _gate_blog(sub: str) -> None:
    if sub in ("publish", "send"):
        gate_check("blog_publish")       # APPROVE — 외부 공개
    elif sub in ("write", "draft", None, ""):
        gate_check("write_blog_post")    # APPROVE — 비가역 초안 작성
    else:
        gate_check("goto")               # AUTO — 읽기


def _gate_mail(sub: str) -> None:
    if sub in ("send",):
        gate_check("naver_mail_send")    # APPROVE — 외부 발송
    elif sub in ("delete", "trash"):
        gate_check("naver_mail_delete")  # APPROVE — 메일 삭제/휴지통 이동
    elif sub in ("move", "archive", "spam", "label", "unlabel"):
        gate_check("naver_mail_move")    # APPROVE — 메일함/분류 상태 변경
    else:
        gate_check("goto")               # AUTO — 읽기/작성 준비
