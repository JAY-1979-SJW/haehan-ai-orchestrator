# module_category: audit
# primary_trade: common
"""작업 브리프 생성 — 에이전트가 이 1개 파일만 읽고 시작하도록 대상·영향 테스트·금지 파일·검증 명령을 담는다.

python -m tools.code_map.agent_brief <spec-id> --role implement --files a.py b.py [--map ..] [--out ..]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from tools.code_map import query

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()


def wip_files() -> list[str]:
    """미커밋 변경 파일 = 건드리면 안 되는 WIP (대상 파일 제외는 호출측)."""
    r = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return sorted(line[3:].strip().strip('"') for line in r.stdout.splitlines() if line[:2] != "??")


def build(spec_id: str, role: str, files: list[str], map_path: Path | None = None) -> str:
    roles = json.loads((ROOT / "configs" / "agent_roles.json").read_text(encoding="utf-8"))["roles"]
    r = roles[role]
    try:
        m = query.load(map_path)
        tests = query.tests_for(m, files) if files else []
        imp = query.impact(m, files)[:20] if files else []
    except FileNotFoundError:
        tests, imp = [], []
    forbidden = [f for f in wip_files() if f not in files][:50]
    L = [
        f"# 작업 브리프 — {spec_id} ({role})",
        f"- 모델: {r['model']} / 도구 호출 상한: {r['max_tool_calls']} / 출력: {r['output']}",
        f"- 상한 도달 시 data/impact/{spec_id}.handoff.md 작성 후 종료. 이어쓰기 금지.",
        "## 대상 파일",
        *[f"- {f}" for f in files],
        "## 영향받는 파일(상위 20)",
        *[f"- {f}" for f in imp],
        "## 영향 테스트",
        *[f"- {t}" for t in tests],
        "## 금지 파일(미커밋 WIP, 수정 금지)",
        *[f"- {f}" for f in forbidden],
        "## 검증",
        "- HAEHAN_NO_BROWSER_LAUNCH=1 python tools/verify_change.py --head",
    ]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_id")
    ap.add_argument("--role", default="implement")
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--map", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    out = a.out or ROOT / "data" / "impact" / f"{a.spec_id}.brief.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(a.spec_id, a.role, a.files, a.map), encoding="utf-8")
    print(f"brief: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
