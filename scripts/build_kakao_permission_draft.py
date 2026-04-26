"""KAKAO-DEV-4 — Kakao 권한 신청 Draft 생성 CLI.

저장된 앱 상세 관찰 결과(app_details.json)를 읽어 권한 신청 draft를 생성한다.
실제 신청 제출은 하지 않는다.

사용:
  python scripts/build_kakao_permission_draft.py --from-latest-details --json
  python scripts/build_kakao_permission_draft.py --details-json PATH/app_details.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.observe_kakao_app_details import _build_permission_draft  # noqa: E402


def _find_latest_details_json(root: str = "runs/developer_console") -> Path | None:
    candidates = sorted(
        Path(root).glob("kakao_app_details_*/app_details.json"),
        key=lambda p: p.parent.name,
    )
    return candidates[-1] if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Kakao 권한 신청 draft builder")
    parser.add_argument("--from-latest-details", action="store_true",
                        help="최신 kakao_app_details 결과 자동 선택")
    parser.add_argument("--details-json", dest="details_json", default=None,
                        help="app_details.json 경로 직접 지정")
    parser.add_argument("--out-dir", default="runs/developer_console")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    details_path: Path | None = None
    if args.details_json:
        details_path = Path(args.details_json)
    elif args.from_latest_details:
        details_path = _find_latest_details_json(args.out_dir)
        if details_path is None:
            print("[build_kakao_permission_draft] 최신 app_details.json을 찾을 수 없습니다.", file=sys.stderr)
            return 1
        print(f"[build_kakao_permission_draft] 입력: {details_path}", file=sys.stderr)
    else:
        print("[build_kakao_permission_draft] --from-latest-details 또는 --details-json 필요", file=sys.stderr)
        parser.print_help()
        return 1

    try:
        data = json.loads(details_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[build_kakao_permission_draft] 파일 읽기 실패: {exc}", file=sys.stderr)
        return 1

    apps = data.get("apps") or []
    if not apps:
        print("[build_kakao_permission_draft] apps 목록이 비어 있습니다.", file=sys.stderr)
        return 1

    ts = data.get("observed_at") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result = _build_permission_draft(apps, Path(args.out_dir), ts)

    ddir = result.get("draft_dir", "")
    if ddir:
        print(f"[build_kakao_permission_draft] draft 저장: {ddir}", file=sys.stderr)

    if args.json_output:
        slim = {
            "created_at": result.get("created_at"),
            "app_count": result.get("app_count"),
            "draft_dir": ddir,
            "drafts": [
                {
                    "app_id": d["app_id"],
                    "app_name": d["app_name"],
                    "requested_features": d["requested_features"],
                    "submit_ready": d["submit_ready"],
                    "review_required": d.get("review_required", True),
                    "missing_inputs": d["missing_inputs"],
                    "required_documents": d["required_documents"],
                    "account_email_warning": d.get("account_email_warning", ""),
                }
                for d in (result.get("drafts") or [])
            ],
        }
        print(json.dumps(slim, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
