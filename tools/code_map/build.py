# module_category: audit
# primary_trade: common
"""코드맵 S1 빌드 — 파일 단위 import·문자열 참조 그래프와 도달성 분류.

사용:
    python tools/code_map/build.py                # data/code_map/map.json + summary.md
    python tools/code_map/build.py --determinism  # 2회 빌드 결과(메타 제외) 비교
읽기 전용(원본·DB 쓰기 없음). 출력은 data/code_map/ (git 미추적).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.code_map import fullmap, reach, scan  # noqa: E402

OUT_DIR = ROOT / "data" / "code_map"


def build() -> dict:
    files = scan.tracked_files()
    graph = reach.build_graph(files, reach.load_manual())
    classes = reach.classify(graph, files)
    s = graph["stats"]
    total_imports = s["import_internal"] + s["import_external"] + s["import_failed"]
    coverage = {
        "py_files": len(graph["py_files"]),
        "parse_errors": len(graph["parse_errors"]),
        "imports_total": total_imports,
        "imports_internal": s["import_internal"],
        "imports_external": s["import_external"],
        "imports_failed": s["import_failed"],
        "import_failed_pct_of_internal_attempts": round(
            100 * s["import_failed"] / max(1, s["import_internal"] + s["import_failed"]), 2
        ),
        "dynamic_literal": s["dynamic_literal"],
        "dynamic_unresolved": s["dynamic_unresolved"],
        "dynamic_unresolved_files": len(graph["dynamic_files"]),
        "string_edges": s["string_edges"],
        "launcher_roots": len(graph["launcher_roots"]),
        "main_files": len(graph["has_main"]),
    }
    counts = Counter(v["class"] for v in classes.values())
    full = fullmap.extend(graph, files, {})
    all_counts = Counter(v["class"] for v in full["nodes"].values())
    return {
        "coverage": coverage,
        "class_counts": {c: counts.get(c, 0) for c in reach.CLASSES},
        "all_class_counts": {c: all_counts.get(c, 0) for c in fullmap.PRIORITY},
        "all_node_count": {"files": len(full["nodes"]), "dirs": len(full["dirs"])},
        "all_edge_kinds": full["edge_kinds"],
        "all_nodes": full["nodes"],
        "all_dirs": full["dirs"],
        "all_edges": full["edges"],
        "import_edges": full["import_edges"],  # 실제 import 만 — 층간 방향 판정용
        "all_roots": full["roots"],
        "files": classes,
        "edges": graph["edges"],
        "launcher_roots": graph["launcher_roots"],
        "parse_errors": graph["parse_errors"],
        "dynamic_unresolved_files": graph["dynamic_files"],
        "import_failed_samples": graph["import_failed_samples"],
    }


def _digest(result: dict) -> str:
    return hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _summary(result: dict, meta: dict) -> str:
    cov, cc = result["coverage"], result["class_counts"]
    by_dir: dict[str, Counter] = {}
    for p, v in result["files"].items():
        top = p.split("/")[0] if "/" in p else "(root)"
        by_dir.setdefault(top, Counter())[v["class"]] += 1
    lines = [
        f"# 코드맵 S1 요약 — {meta['generated_at']} @ {meta['commit']}",
        "",
        "## 1. 커버리지(사각지대 먼저)",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in cov.items()],
        "",
        "## 2. 분류",
        "",
        "| 분류 | 파일 수 |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in cc.items()],
        "",
        "## 3. 디렉터리별",
        "",
        "| dir | " + " | ".join(reach.CLASSES) + " |",
        "|---|" + "---|" * len(reach.CLASSES),
        *[f"| {d} | " + " | ".join(str(c.get(k, 0)) for k in reach.CLASSES) + " |" for d, c in sorted(by_dir.items())],
        "",
        "## 4. UNREACHED (삭제 후보 — 사람 확인 전 삭제 금지)",
        "",
        *[f"- {p}" for p, v in sorted(result["files"].items()) if v["class"] == "UNREACHED"],
        "",
        "## 5. 전체 파일·폴더 지도",
        "",
        f"노드: 파일 {result['all_node_count']['files']} · 폴더 {result['all_node_count']['dirs']}  "
        f"엣지: {result['all_edge_kinds']}",
        "",
        "| 분류 | 파일 수 |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in result["all_class_counts"].items()],
        "",
        "| 폴더(2단계) | 대표 | " + " | ".join(fullmap.PRIORITY) + " |",
        "|---|---|" + "---|" * len(fullmap.PRIORITY),
        *[
            f"| {d} | {v['class']} | " + " | ".join(str(v["counts"].get(k, 0)) for k in fullmap.PRIORITY) + " |"
            for d, v in sorted(result["all_dirs"].items())
            if d.count("/") <= 1
        ],
        "",
        "## 6. 전체 UNREACHED 파일(비코드 포함)",
        "",
        *[f"- {p}" for p, v in sorted(result["all_nodes"].items()) if v["class"] == "UNREACHED"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--determinism", action="store_true", help="2회 빌드 후 결과 해시 비교")
    a = ap.parse_args()
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    result = build()
    if a.determinism:
        second = build()
        same = _digest(result) == _digest(second)
        print(f"[code_map] determinism: {'SAME' if same else 'DIFF'}")
        if not same:
            return 1
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, encoding="utf-8"
    ).stdout.strip()
    meta = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": commit,
        "scan_root": str(ROOT),
        "digest": _digest(result),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "map.json").write_text(
        json.dumps({"meta": meta, **result}, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
    )
    (OUT_DIR / "summary.md").write_text(_summary(result, meta), encoding="utf-8")
    print(
        json.dumps(
            {"coverage": result["coverage"], "class_counts": result["class_counts"]}, ensure_ascii=False, indent=1
        )
    )
    print(f"[code_map] 저장: {OUT_DIR / 'map.json'}, {OUT_DIR / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
