"""LOCAL-FS-3 — 최근 runs 결과 자동 요약 CLI.

사용 예:
  python scripts/summarize_recent_runs.py --json
  python scripts/summarize_recent_runs.py --group developer_console --json
  python scripts/summarize_recent_runs.py --group render,video --json
  python scripts/summarize_recent_runs.py --root . --out-dir runs/local_files --json

절대 금지:
  - .env / secrets / browser_state 원문 출력
  - API key / token / password 원문 출력
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_orchestrator.local_files.runs_summarizer import (
    GROUPS,
    summarize_all_groups,
    write_runs_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="LOCAL-FS-3 — 최근 runs 결과 자동 요약")
    parser.add_argument("--root", default=".", help="프로젝트 루트 디렉터리")
    parser.add_argument(
        "--group", default="",
        help=f"요약할 작업군 (쉼표 구분). 미지정시 전체. 가능한 값: {', '.join(GROUPS)}"
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON 요약 stdout 출력")
    parser.add_argument("--out-dir", default="runs/local_files", help="결과 저장 디렉터리")
    parser.add_argument("--max-files", type=int, default=3, help="그룹당 최대 파일 수")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    groups = [g.strip() for g in args.group.split(",") if g.strip()] or None

    if groups:
        unknown = [g for g in groups if g not in GROUPS]
        if unknown:
            print(f"[오류] 알 수 없는 그룹: {unknown}. 가능한 값: {list(GROUPS)}", file=sys.stderr)
            return 1

    summary = summarize_all_groups(root, max_files_per_group=args.max_files, groups=groups)
    paths = write_runs_summary(summary, args.out_dir)

    print(f"[요약] overall_status={summary['overall_status']}", file=sys.stderr)
    for group, g in summary["groups"].items():
        mark = {"PASS": "✓", "WARN": "!", "FAIL": "✗"}.get(g["status"], "?")
        print(f"  {mark} {group}: {g['status']} (파일 {g['file_count']}개)", file=sys.stderr)
    print(f"[결과] {paths['json']}", file=sys.stderr)
    print(f"[결과] {paths['md']}", file=sys.stderr)

    if args.json_output:
        slim = {
            "summarized_at": summary["summarized_at"],
            "overall_status": summary["overall_status"],
            "group_statuses": {g: v["status"] for g, v in summary["groups"].items()},
            "action_required_groups": [
                g for g, v in summary["groups"].items() if v.get("action_required")
            ],
            "all_next_actions": summary.get("all_next_actions", []),
            "output_json": paths["json"],
            "output_md": paths["md"],
        }
        print(json.dumps(slim, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
