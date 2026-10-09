"""최상위 평면 금지 게이트 (G15 / S0) — scripts/*.py · ai_orchestrator/*.py · 저장소 루트 *.py 에 새 파일 추가를 차단한다.

설계: docs/architecture/FOLDER_STRUCTURE.md. 최상위가 평면이면 기능별 폴더(scripts/browser·common·auth …, ai_orchestrator/core·llm·mcp …)로
나눈 구조가 다시 무너진다. 새 코드는 알맞은 하위 폴더에 둔다.

규칙 정본: configs/flat_root_gate.json (평면 금지 폴더·허용 진입점), 기준선: configs/flat_root_baseline.json (기존 평면 파일, 줄이기만).
G11(tool_home_gate)과 같은 방식: pre-commit --staged, CI --check-all.

사용:
    python tools/repo_gates/flat_root_gate.py --staged          # pre-commit: 새로 추가(A)·이름변경(R)된 .py 만 본다
    python tools/repo_gates/flat_root_gate.py --check-all       # CI: 추적 파일 전체 — 기준선에 없는 평면 파일이 있으면 실패
    python tools/repo_gates/flat_root_gate.py --update-baseline # 기준선 줄이기(없어졌거나 하위 폴더로 옮긴 항목만 제거). 늘리기는 불가
    python tools/repo_gates/flat_root_gate.py --init-baseline   # 기준선 파일이 없을 때 현재 상태로 최초 생성
    python tools/repo_gates/flat_root_gate.py --classify <경로...>

판정:
    - 평면 파일 = 평면 금지 폴더 바로 아래의 .py (scripts/x.py, ai_orchestrator/x.py, x.py). 하위 폴더 파일은 대상이 아니다.
    - 허용 = 진입점 이름(asgi·router·config·app·__init__·conftest·sitecustomize) 또는 기준선에 든 파일.
    - 파일 수정(M)·삭제(D)는 보지 않는다. 기준선 파일을 고쳐도, 지워도 통과(삭제는 오히려 장려).
    - 옛 경로에 남기는 호환 shim 은 그 경로가 이미 기준선에 있으므로 통과한다.
우회 옵션 없음 — 알맞은 하위 폴더에 두거나, 정말 진입점이면 configs/flat_root_gate.json 의 entry_points 에 사유와 함께 추가(리뷰 대상).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath

_BOOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402
from tools.repo_gates.tool_home_gate import _exists_in_ref, staged_added, tracked_files  # noqa: E402

ROOT = repo_root()
CONFIG = "configs/flat_root_gate.json"
BASELINE = "configs/flat_root_baseline.json"


def load_config(root: Path = ROOT) -> dict:
    cfg = json.loads((root / CONFIG).read_text(encoding="utf-8"))
    cfg["_dirs"] = tuple(d.rstrip("/") for d in cfg["flat_dirs"])  # "" 는 저장소 루트
    cfg["_entry"] = frozenset(e["name"] for e in cfg["entry_points"])
    return cfg


def classify(path: str, cfg: dict) -> tuple[str, str]:
    """(상태, 설명). 상태: skip(대상 아님) | entry(허용 진입점) | flat(평면 파일)."""
    p = PurePosixPath(path.replace("\\", "/"))
    if p.suffix.lower() != ".py":
        return "skip", "대상 확장자 아님"
    parent = "" if str(p.parent) == "." else str(p.parent)
    if parent not in cfg["_dirs"]:
        return "skip", "평면 금지 폴더 바로 아래가 아님"
    if p.name in cfg["_entry"]:
        return "entry", "허용 진입점"
    return "flat", f"{parent or '(저장소 루트)'} 최상위 평면 파일"


def load_baseline(root: Path = ROOT) -> set[str]:
    p = root / BASELINE
    if not p.is_file():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")).get("files", []))


def _write_baseline(root: Path, files: list[str], note: str) -> None:
    p = root / BASELINE
    prev = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    payload = {
        "_comment": "최상위 평면 금지 게이트(G15) 기준선 — 이미 평면에 있던 파일(기존 부채). 늘리는 변경 금지, 하위 폴더로 옮기거나 삭제해 줄이는 방향만. 규칙: configs/flat_root_gate.json",
        "target": prev.get("target", 0),
        "count": len(files),
        "note": note,
        "files": sorted(files),
    }
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(p)  # 원자적 쓰기


def current_flat(root: Path, cfg: dict) -> list[str]:
    return sorted(f for f in tracked_files(root) if (root / f).exists() and classify(f, cfg)[0] == "flat")


def violations(entries: list[tuple[str, str]], cfg: dict, baseline: set[str]) -> list[tuple[str, str]]:
    return [(st, path) for st, path in entries if classify(path, cfg)[0] == "flat" and path not in baseline]


def _report(bad: list[tuple[str, str]], cfg: dict) -> None:
    print("=" * 60, file=sys.stderr)
    print("[flat_root_gate] 최상위 평면에 새 파일이 생겨 차단합니다.", file=sys.stderr)
    for st, path in bad:
        print(f"  - {path}  ({'이동' if st == 'R' else '신규'})", file=sys.stderr)
    print(f"  평면 금지 폴더: {', '.join(d or '(저장소 루트)' for d in cfg['_dirs'])}", file=sys.stderr)
    print(f"  허용 진입점: {', '.join(sorted(cfg['_entry']))}", file=sys.stderr)
    print(
        "  → 알맞은 하위 폴더(예: scripts/browser/, scripts/common/, ai_orchestrator/core/ …)에 두세요.",
        file=sys.stderr,
    )
    print(
        "    정말 진입점이면 configs/flat_root_gate.json 의 entry_points 에 사유와 함께 추가(리뷰 대상).",
        file=sys.stderr,
    )
    print("  (우회 옵션 없음. 정본: docs/architecture/FOLDER_STRUCTURE.md)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:  # noqa: C901, PLR0912 - CLI 모드 분기(staged/check-all/baseline/classify)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--check-all", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--init-baseline", action="store_true")
    ap.add_argument(
        "--sync-baseline",
        action="store_true",
        help="configs/flat_root_gate.json 규칙 변경으로 기존 파일이 새로 flat 판정이 "
        "된 경우만 기준선에 추가(줄이기도 같이 함). --reason 필수, 각 파일이 "
        "--verify-in-ref 에도 이미 있어야 허용(판정 완화 아님).",
    )
    ap.add_argument("--reason", default=None)
    ap.add_argument("--verify-in-ref", default="origin/master")
    ap.add_argument("--classify", action="store_true")
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    root = a.root.resolve()
    cfg = load_config(root)

    if a.classify:
        for p in a.paths:
            print(f"{p}\t{'\t'.join(classify(p, cfg))}")
        return 0
    if a.init_baseline:
        if (root / BASELINE).is_file():
            print("기준선이 이미 있다 — --update-baseline(줄이기만) 을 쓴다", file=sys.stderr)
            return 2
        flat = current_flat(root, cfg)
        _write_baseline(root, flat, "최초 생성: 현재 최상위 평면 파일 전부")
        print(f"기준선 생성: {len(flat)}개")
        return 0
    baseline = load_baseline(root)
    if a.update_baseline:
        flat_set = set(current_flat(root, cfg))
        kept = sorted(baseline & flat_set)
        added = flat_set - baseline
        if added:
            print(
                f"기준선에 없는 평면 파일 {len(added)}개 — 기준선을 늘릴 수 없다(하위 폴더로 옮길 것):", file=sys.stderr
            )
            for f in sorted(added)[:20]:
                print("  " + f, file=sys.stderr)
            return 1
        _write_baseline(root, kept, f"하향 갱신: {len(baseline)} → {len(kept)}")
        print(f"기준선 {len(baseline)} → {len(kept)}")
        return 0
    if a.sync_baseline:
        if not a.reason:
            print("[flat_root_gate] --sync-baseline 은 --reason 이 필수(왜 기준선이 느는지 기록)", file=sys.stderr)
            return 2
        flat_set = set(current_flat(root, cfg))
        added = flat_set - baseline
        removed = baseline - flat_set
        if added:
            not_in_ref = sorted(f for f in added if not _exists_in_ref(root, a.verify_in_ref, f))
            if not_in_ref:
                print(
                    f"[flat_root_gate] --sync-baseline 거부: {len(not_in_ref)}개가 {a.verify_in_ref} 에 없음"
                    " — 이번 브랜치가 새로 만든 평면 파일일 수 있다(판정 완화 금지):",
                    file=sys.stderr,
                )
                for f in not_in_ref[:20]:
                    print("  " + f, file=sys.stderr)
                return 1
        kept = sorted(flat_set)
        _write_baseline(root, kept, f"규칙 변경 동기화({a.reason}): +{len(added)} -{len(removed)} = {len(kept)}")
        print(f"[flat_root_gate] 기준선 동기화: {len(baseline)} → {len(kept)} (+{len(added)} -{len(removed)})")
        return 0
    if a.check_all:
        flat = current_flat(root, cfg)
        bad = [("A", f) for f in flat if f not in baseline]
        stale = sorted(baseline - set(flat))
        if stale:
            print(
                f"[flat_root_gate] 참고: 기준선 {len(stale)}건이 더 이상 평면에 없음 — --update-baseline 으로 줄일 것",
                file=sys.stderr,
            )
        if bad:
            _report(bad, cfg)
            return 1
        print(f"[flat_root_gate] PASS — 최상위 평면 {len(flat)}건 모두 기준선(기존 부채) 안")
        return 0
    if a.staged:
        entries = staged_added(root)
        if not entries:
            return 0
        bad = violations(entries, cfg, baseline)
        if bad:
            _report(bad, cfg)
            return 1
        return 0
    ap.error("--staged / --check-all / --update-baseline / --init-baseline / --classify 중 하나")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
