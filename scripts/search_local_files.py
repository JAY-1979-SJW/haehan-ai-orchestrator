"""LOCAL-FS-1 — 로컬 파일 검색 CLI.

사용 예:
  python scripts/search_local_files.py --query "kakao" --preview --json
  python scripts/search_local_files.py --query "storage_state" --file-type py,md --json
  python scripts/search_local_files.py --glob "*.md" --query "자동화" --preview --json
  python scripts/search_local_files.py --include-runs --query "render_worker" --json

절대 금지:
  - .env / secrets/ 원문 출력
  - API key / token / password 원문 출력
  - --allow-sensitive-paths 사용 시에도 secret redaction 유지
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_orchestrator.local_files.file_indexer import (
    build_file_index,
    read_file_preview,
    search_files,
    write_search_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="LOCAL-FS-1 — 로컬 파일 검색")
    parser.add_argument("--root", default=".", help="검색 루트 디렉터리")
    parser.add_argument("--query", default="", help="검색어 (없으면 파일 index 요약)")
    parser.add_argument("--glob", dest="glob_pattern", default="", help="파일 glob 패턴 (예: *.py)")
    parser.add_argument("--file-type", default="", help="파일 타입 (쉼표 구분, 예: py,md,json)")
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--preview", action="store_true", help="매칭 파일 preview 포함")
    parser.add_argument("--max-preview-chars", type=int, default=8000)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--out-dir", default="runs/local_files")
    parser.add_argument("--include-runs", action="store_true", help="runs/ 디렉터리 포함")
    parser.add_argument("--allow-sensitive-paths", action="store_true",
                        help="민감 경로 스캔 허용 (secret redaction은 항상 적용)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_types = [ft.strip() for ft in args.file_type.split(",") if ft.strip()] or None
    include_globs = [args.glob_pattern] if args.glob_pattern else None

    if not args.query:
        # query 없음 → index 요약
        index = build_file_index(
            root,
            max_files=5000,
            include_runs=args.include_runs,
        )
        result = {
            "mode": "index",
            "root": str(root),
            "searched_at": ts,
            "total_files": index["total_files"],
            "by_extension": index["by_extension"],
            "query": "",
            "total_matches": 0,
            "results": [],
        }
        print(f"[index] {index['total_files']}개 파일 스캔 완료", file=sys.stderr)
        for ext, cnt in list(index["by_extension"].items())[:10]:
            print(f"  {ext}: {cnt}개", file=sys.stderr)
    else:
        matches = search_files(
            root,
            args.query,
            file_types=file_types,
            max_results=args.max_results,
            include_runs=args.include_runs,
            allow_sensitive_paths=args.allow_sensitive_paths,
            include_globs=include_globs,
        )

        if args.preview:
            for m in matches:
                full_path = root / m["path"]
                prev = read_file_preview(
                    full_path,
                    max_chars=args.max_preview_chars,
                    allow_sensitive_paths=args.allow_sensitive_paths,
                )
                m["preview"] = prev.get("preview")
                m["preview_truncated"] = prev.get("truncated", False)

        result = {
            "mode": "search",
            "root": str(root),
            "query": args.query,
            "searched_at": ts,
            "total_matches": len(matches),
            "results": matches,
            "security": {
                "env_printed": False,
                "secrets_printed": False,
                "api_key_raw": False,
                "private_key_printed": False,
            },
        }
        print(f"[검색] '{args.query}' → {len(matches)}개 파일 매칭", file=sys.stderr)

    paths = write_search_result(result, args.out_dir)
    print(f"[결과] {paths['json']}", file=sys.stderr)
    print(f"[결과] {paths['md']}", file=sys.stderr)

    if args.json_output:
        # preview는 json 출력에서는 생략 (파일로만 저장)
        slim = {k: v for k, v in result.items() if k != "results"}
        slim["result_count"] = len(result.get("results", []))
        slim["result_paths"] = [r["path"] for r in result.get("results", [])[:20]]
        slim["output_json"] = paths["json"]
        slim["output_md"] = paths["md"]
        print(json.dumps(slim, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
