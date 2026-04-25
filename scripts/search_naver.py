"""CLI: Naver Search Open API PoC (F-4S-2).

사용법 예:
    # dry-run (실제 호출 없음, 키 검증만)
    python scripts/search_naver.py --type blog --query "소방공사" --display 3

    # 실제 호출 (NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 필요)
    python scripts/search_naver.py --type blog --query "소방공사" --display 3 --live --json

원칙:
- 브라우저 자동화 절대 금지.
- 카페 가입 / 글쓰기 / 댓글 자동화 금지 — 본 스크립트는 read-only 검색 한정.
- secret 출력 금지 — redacted 형식만 노출.
"""
from __future__ import annotations

import argparse
import json as _json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# repo root import
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_orchestrator.connectors import naver_search_api_client as client_mod  # noqa: E402
from ai_orchestrator.connectors import naver_search_api_config as config_mod  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="search_naver.py",
        description="Naver Search Open API PoC CLI (read-only).",
    )
    p.add_argument(
        "--type",
        dest="search_type",
        required=True,
        choices=list(client_mod.SUPPORTED_TYPES),
        help="검색 종류",
    )
    p.add_argument("--query", required=True, help="검색어 (필수)")
    p.add_argument("--display", type=int, default=10, help="결과 개수 (1..100)")
    p.add_argument("--start", type=int, default=1, help="시작 위치 (1..1000)")
    p.add_argument(
        "--sort",
        default=None,
        choices=["sim", "date", "asc", "dsc"],
        help="정렬 (검색 타입별 허용값만 사용)",
    )
    p.add_argument("--live", action="store_true", help="실제 API 호출 활성화")
    p.add_argument("--json", action="store_true", help="콘솔에 결과 JSON 출력")
    p.add_argument(
        "--out-dir",
        default="runs/naver",
        help="결과 저장 폴더 (기본: runs/naver)",
    )
    return p


def _redacted_summary(cfg: config_mod.NaverSearchApiConfig) -> Dict[str, Any]:
    return cfg.redacted()


def _format_md(result: Dict[str, Any], cfg_summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Naver Search API PoC — {result.get('search_type')}")
    lines.append("")
    lines.append(f"- mode: `{result.get('mode')}`")
    lines.append(f"- query: `{result.get('query')}`")
    lines.append(f"- total: {result.get('total')}")
    lines.append(f"- start: {result.get('start')}")
    lines.append(f"- display: {result.get('display')}")
    lines.append(f"- items_count: {len(result.get('items') or [])}")
    warns = result.get("warnings") or []
    if warns:
        lines.append("")
        lines.append("## warnings")
        for w in warns:
            lines.append(f"- {w}")
    err = result.get("error")
    if err:
        lines.append("")
        lines.append(f"## error: {err}")
    lines.append("")
    lines.append("## config (redacted)")
    for k, v in cfg_summary.items():
        lines.append(f"- {k}: {v}")
    items = result.get("items") or []
    if items:
        lines.append("")
        lines.append("## items")
        for idx, item in enumerate(items, start=1):
            title = item.get("title") or ""
            link = item.get("link") or ""
            lines.append(f"{idx}. {title}")
            if link:
                lines.append(f"   - link: {link}")
    return "\n".join(lines) + "\n"


def _write_outputs(out_dir: Path, payload: Dict[str, Any], md_text: str) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"naver_search_{ts}.json"
    md_path = out_dir / f"naver_search_{ts}.md"
    json_path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def run(argv: List[str]) -> int:
    args = _build_parser().parse_args(argv)
    cfg = config_mod.load_naver_search_api_config()
    cfg_summary = _redacted_summary(cfg)

    warnings: List[str] = []
    if args.live and not cfg.live_enabled:
        warnings.append(
            "WARN: --live requested but NAVER_CLIENT_ID / NAVER_CLIENT_SECRET missing — falling back to mock_or_disabled"
        )

    try:
        result = client_mod.search_naver(
            search_type=args.search_type,
            query=args.query,
            display=args.display,
            start=args.start,
            sort=args.sort,
            live=args.live,
            config=cfg,
        )
    except ValueError as exc:
        result = {
            "success": False,
            "mode": "mock_or_disabled",
            "search_type": args.search_type,
            "query": args.query,
            "total": 0,
            "start": args.start,
            "display": args.display,
            "items": [],
            "error": f"validation_error: {exc}",
            "warnings": warnings,
        }
        print(f"[search_naver] validation_error: {exc}", file=sys.stderr)
        for w in warnings:
            print(f"[search_naver] {w}", file=sys.stderr)
        out_dir = Path(args.out_dir)
        payload = {"config": cfg_summary, "result": result}
        paths = _write_outputs(out_dir, payload, _format_md(result, cfg_summary))
        print(f"[search_naver] json -> {paths['json']}")
        print(f"[search_naver] md   -> {paths['md']}")
        return 2

    if warnings:
        existing = list(result.get("warnings") or [])
        existing.extend(warnings)
        result["warnings"] = existing

    out_dir = Path(args.out_dir)
    payload = {"config": cfg_summary, "result": result}
    md_text = _format_md(result, cfg_summary)
    paths = _write_outputs(out_dir, payload, md_text)

    print(f"[search_naver] mode={result.get('mode')} type={result.get('search_type')} "
          f"total={result.get('total')} items={len(result.get('items') or [])}")
    for w in (result.get("warnings") or []):
        print(f"[search_naver] WARN: {w}")
    print(f"[search_naver] json -> {paths['json']}")
    print(f"[search_naver] md   -> {paths['md']}")

    if args.json:
        print(_json.dumps(payload, ensure_ascii=False, indent=2))

    return 0 if result.get("success") else 1


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
