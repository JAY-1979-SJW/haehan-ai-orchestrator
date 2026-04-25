#!/usr/bin/env python3
"""TAX-API-1 — 사업자등록 상태조회 / 진위확인 CLI (PoC).

사용 예:
    # status 조회 (live 안 함, dry-run 형식 점검만):
    python scripts/check_business_registration.py --status 1234567890 --json

    # status 조회 (live, 사업자번호 목록 파일):
    python scripts/check_business_registration.py \\
        --status-file samples/business_numbers.txt --live --json

    # validate 조회:
    python scripts/check_business_registration.py \\
        --validate-json samples/validate_items.json --live --json

원칙:
  - ``--live`` 없이 실행하면 dry-run / validation 중심 (HTTP 호출 없음).
  - ``--live`` 가 있어도 service_key 환경변수가 없으면 WARN 으로 종료
    (FAIL 이 아니다 — PoC 운영자가 키 등록 전에도 흐름 점검 가능).
  - 출력에 service_key 원문을 노출하지 않는다.
  - 본 CLI 는 홈택스 화면/쿠키/storage_state 에 접근하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "공공데이터포털 국세청 사업자등록정보 API PoC. "
            "--live 없이 실행하면 dry-run."
        ),
    )
    parser.add_argument(
        "--status",
        action="append",
        default=None,
        help="조회할 사업자번호 (여러 번 지정 가능).",
    )
    parser.add_argument(
        "--status-file",
        default=None,
        help="사업자번호 목록 파일 (한 줄에 하나).",
    )
    parser.add_argument(
        "--validate-json",
        default=None,
        help=(
            "진위확인 입력 JSON 파일. 최상위는 list[dict] 또는 "
            '{"businesses": [...]} 형태.'
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="결과를 JSON 으로 stdout 에 출력.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="실제 API 호출. service_key 가 없으면 WARN 으로 종료.",
    )
    return parser


def _read_status_file(path: str) -> list[str]:
    out: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = (line or "").strip()
            if not s or s.startswith("#"):
                continue
            out.append(s)
    return out


def _read_validate_json(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        items = data.get("businesses")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
    return []


def _print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    summary = payload.get("summary") or {}
    print(
        f"[check-business-registration] mode={payload.get('mode')!r} "
        f"kind={payload.get('kind')!r} "
        f"count={payload.get('count')} "
        f"items={len(payload.get('items') or [])} "
        f"warnings={len(payload.get('warnings') or [])}"
    )
    if summary:
        for k, v in summary.items():
            print(f"  - {k}: {v}")
    for w in payload.get("warnings") or []:
        print(f"  warn: {w}")


def _verdict_from_payload(payload: dict[str, Any]) -> str:
    """약식 PASS/WARN/FAIL.

      PASS: success=True, mode=live, items >= 1
      WARN: success=True, mode=mock_or_disabled (또는 live 인데 items=0)
      FAIL: success=False
    """
    if not payload.get("success"):
        return "FAIL"
    if payload.get("mode") == "live" and (payload.get("items") or []):
        return "PASS"
    return "WARN"


def _resolve_repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    sys.path.insert(0, _resolve_repo_root())
    from ai_orchestrator.connectors.nts_business_api_client import (
        check_status,
        validate_businesses,
    )
    from ai_orchestrator.connectors.nts_business_api_config import (
        load_nts_business_api_config,
    )

    cfg = load_nts_business_api_config()

    # --live 인데 키가 없으면 WARN 으로 종료 (FAIL 아님).
    if args.live and not cfg.live_enabled:
        warn_payload = {
            "success": True,
            "mode": "mock_or_disabled",
            "kind": "config",
            "count": 0,
            "items": [],
            "warnings": ["live_requested_but_service_key_missing"],
            "config": cfg.redacted(),
            "verdict": "WARN",
        }
        _print_payload(warn_payload, as_json=args.json)
        # --json 모드에서는 stdout 이 JSON 만 가져야 한다 — verdict 텍스트는 stderr.
        msg = (
            "[check-business-registration] verdict: WARN "
            "(--live 요청이지만 service_key 환경변수가 비어있습니다.)"
        )
        if args.json:
            print(msg, file=sys.stderr, flush=True)
        else:
            print(msg, flush=True)
        return 0

    # 입력 수집.
    status_numbers: list[str] = []
    if args.status:
        status_numbers.extend(args.status)
    if args.status_file:
        try:
            status_numbers.extend(_read_status_file(args.status_file))
        except OSError as e:
            print(
                f"[check-business-registration] status-file 읽기 실패: "
                f"{type(e).__name__}",
                file=sys.stderr,
                flush=True,
            )
            return 2

    validate_items: list[dict] = []
    if args.validate_json:
        try:
            validate_items = _read_validate_json(args.validate_json)
        except (OSError, json.JSONDecodeError) as e:
            print(
                f"[check-business-registration] validate-json 읽기 실패: "
                f"{type(e).__name__}",
                file=sys.stderr,
                flush=True,
            )
            return 2

    if not status_numbers and not validate_items:
        print(
            "[check-business-registration] 입력이 없습니다. "
            "--status / --status-file / --validate-json 중 하나를 지정하세요.",
            file=sys.stderr,
            flush=True,
        )
        return 2

    payloads: list[dict[str, Any]] = []
    if status_numbers:
        payloads.append(
            check_status(status_numbers, config=cfg, live=args.live)
        )
    if validate_items:
        payloads.append(
            validate_businesses(validate_items, config=cfg, live=args.live)
        )

    # 종합 verdict — 가장 보수적 결과.
    verdicts = [_verdict_from_payload(p) for p in payloads]
    if "FAIL" in verdicts:
        overall = "FAIL"
    elif "WARN" in verdicts or any(p.get("mode") != "live" for p in payloads):
        overall = "WARN"
    else:
        overall = "PASS"

    if args.json:
        out = {
            "verdict": overall,
            "config": cfg.redacted(),
            "results": payloads,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for p in payloads:
            _print_payload(p, as_json=False)
        print(f"[check-business-registration] verdict: {overall}", flush=True)

    return 0 if overall in ("PASS", "WARN") else 1


if __name__ == "__main__":
    sys.exit(main())
