"""도구 집 게이트 (G11 / T2-a) — 도구 키워드가 든 새 파일이 그 도구의 집 밖이면 차단한다.

규칙 정본: configs/tool_home.json (도구 키워드·집·예외+사유), 기준선: configs/tool_home_baseline.json.
도구별 집: 구현 scripts/<도구>/, API ai_orchestrator/connectors/<도구>/, 화면 admin-web/src/app/<도구>/ (docs/architecture/TOOL_HOME_MAP.md).

사용:
    python tools/repo_gates/tool_home_gate.py --staged          # pre-commit: 새로 추가(A)·이름변경(R)된 .py/.ts/.tsx 만 본다
    python tools/repo_gates/tool_home_gate.py --check-all       # CI: 추적 파일 전체 — 기준선에 없는 집 밖 파일이 있으면 실패
    python tools/repo_gates/tool_home_gate.py --update-baseline # 기준선 줄이기(없어졌거나 집으로 옮긴 항목만 제거). 늘리기는 불가
    python tools/repo_gates/tool_home_gate.py --init-baseline   # 기준선 파일이 없을 때 현재 상태로 최초 생성
    python tools/repo_gates/tool_home_gate.py --classify <경로...>

판정:
    - 이동(R)은 목적지가 집 안이면 통과. 집 밖이면 새 이탈로 본다.
    - 기존 파일 수정(M)은 보지 않는다. 기준선 파일을 고쳐도 통과.
    - 예외(tests/·docs/·scripts/archive/·apps/·층 표준 폴더·도메인 계약 소유분 등)는 설정 파일에 사유와 함께 둔다.
    - 이미 어느 도구의 집 안에 있는 파일은 다른 도구 키워드가 우연히 들어 있어도 통과한다.
우회 옵션 없음 — 집 안으로 옮기거나, 정말 예외면 configs/tool_home.json 의 exempt 에 사유와 함께 추가(리뷰 대상).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_BOOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
CONFIG = "configs/tool_home.json"
BASELINE = "configs/tool_home_baseline.json"


def load_config(root: Path = ROOT) -> dict:
    cfg = json.loads((root / CONFIG).read_text(encoding="utf-8"))
    cfg["_tools"] = [(t["name"], re.compile(t["keyword"]), tuple(t["homes"])) for t in cfg["tools"]]
    cfg["_all_homes"] = tuple(h for t in cfg["tools"] for h in t["homes"])
    # 기능 폴더(before_exempt): 층 표준 폴더 예외보다 먼저 판정한다 — 기능 파일이 층 폴더에 새로 생기는 것을 막는다
    cfg["_pre_tools"] = [
        (t["name"], re.compile(t["keyword"]), tuple(t["homes"])) for t in cfg["tools"] if t.get("before_exempt")
    ]
    cfg["_exempt"] = [
        (re.compile(e["regex"]) if "regex" in e else None, e.get("prefix"), e["reason"]) for e in cfg["exempt"]
    ]
    return cfg


def classify(path: str, cfg: dict) -> tuple[str, str | None, str]:
    """(상태, 도구, 설명). 상태: skip(대상 아님) | exempt | home | leak."""
    p = path.replace("\\", "/")
    if Path(p).suffix.lower() not in cfg["extensions"]:
        return "skip", None, "대상 확장자 아님"
    lp = p.lower()
    for name, kw, homes in cfg["_pre_tools"]:
        if kw.search(lp):
            return (
                ("home", name, "기능 폴더 안")
                if p.startswith(homes)
                else ("leak", name, "기능 폴더 밖(층 폴더 예외 적용 안 함)")
            )
    for rx, prefix, reason in cfg["_exempt"]:
        if (prefix is not None and p.startswith(prefix)) or (rx is not None and rx.search(p)):
            return "exempt", None, reason
    for name, kw, homes in cfg["_tools"]:
        if kw.search(lp):
            if p.startswith(homes):
                return "home", name, "도구 집 안"
            if p.startswith(cfg["_all_homes"]):
                return "home", name, "다른 도구의 집 안(키워드는 우연)"
            return "leak", name, "도구 집 밖"
    return "skip", None, "도구 키워드 없음"


def _homes_of(cfg: dict, tool: str) -> tuple[str, ...]:
    return next(h for n, _, h in cfg["_tools"] if n == tool)


def load_baseline(root: Path = ROOT) -> set[str]:
    p = root / BASELINE
    if not p.is_file():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")).get("files", []))


def _exists_in_ref(root: Path, ref: str, path: str) -> bool:
    r = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"],
        cwd=str(root),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return r.returncode == 0


def _write_baseline(root: Path, files: list[str], note: str) -> None:
    p = root / BASELINE
    prev = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    payload = {
        "_comment": "도구 집 게이트(G11) 기준선 — 이미 집 밖에 있던 파일(기존 부채). 늘리는 변경 금지, 이동·삭제로 줄이는 방향만. 규칙: configs/tool_home.json",
        "target": prev.get("target", 0),
        "reviewed_at": prev.get("reviewed_at", ""),
        "count": len(files),
        "note": note,
        "files": sorted(files),
    }
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(p)  # 원자적 쓰기


def tracked_files(root: Path = ROOT) -> list[str]:
    r = subprocess.run(
        ["git", "ls-files", "-z"], cwd=str(root), capture_output=True, encoding="utf-8", errors="replace", check=True
    )
    return [f for f in r.stdout.split("\0") if f]


def _is_shim_file(root: Path, rel: str) -> bool:
    """`# haehan-shim:` 마커로 시작하는 1줄 경로-포워딩 호환 파일인가(scripts/ops/make_shim.py 가
    만듦). shim 은 메커니즘상 항상 '이동 전 옛 경로(집 밖) → 실제 모듈'이 되므로 집 밖인 게
    정상이다 — 도구 집 게이트 판정에서 제외한다(verify_change.py 의 같은 이름 헬퍼와 동일 패턴,
    PR #165 분석에서 발견한 tool_home_baseline 54건 중 20건(37%)이 이 사유의 가짜 위반이었음)."""
    try:
        with (root / rel).open(encoding="utf-8", errors="replace") as f:
            return f.readline().startswith("# haehan-shim:")
    except OSError:
        return False


def current_leaks(root: Path, cfg: dict) -> list[str]:
    return sorted(
        f for f in tracked_files(root)
        if (root / f).exists() and classify(f, cfg)[0] == "leak" and not _is_shim_file(root, f)
    )


def staged_added(root: Path = ROOT) -> list[tuple[str, str]]:
    """staged 의 새 파일(A)과 이름변경(R) 목적지 → [(상태, 경로)]."""
    r = subprocess.run(
        ["git", "diff", "--cached", "--name-status", "-M", "--diff-filter=AR", "-z"],
        cwd=str(root),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    parts = [x for x in r.stdout.split("\0") if x]
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(parts):
        st = parts[i]
        if st.startswith("R") and i + 2 < len(parts):
            out.append(("R", parts[i + 2]))
            i += 3
        else:
            if i + 1 < len(parts):
                out.append((st[0], parts[i + 1]))
            i += 2
    return out


def violations(
    entries: list[tuple[str, str]], cfg: dict, baseline: set[str], root: Path = ROOT,
) -> list[tuple[str, str, str]]:
    bad = []
    for st, path in entries:
        verdict, tool, _ = classify(path, cfg)
        if verdict == "leak" and path not in baseline and not _is_shim_file(root, path):
            bad.append((st, path, tool or "?"))
    return bad


def _report(bad: list[tuple[str, str, str]], cfg: dict) -> None:
    print("=" * 60, file=sys.stderr)
    print("[tool_home_gate] 도구 파일이 집 밖에 새로 생겨 차단합니다.", file=sys.stderr)
    for st, path, tool in bad:
        homes = ", ".join(_homes_of(cfg, tool)[:3])
        print(f"  - {path}  (도구 {tool}, {'이동' if st == 'R' else '신규'})", file=sys.stderr)
        print(f"      집: {homes}", file=sys.stderr)
    print(
        "  → 위 집 안으로 옮기세요. 정말 예외면 configs/tool_home.json 의 exempt 에 사유와 함께 추가(리뷰 대상).",
        file=sys.stderr,
    )
    print("  (우회 옵션 없음. 정본: docs/architecture/TOOL_HOME_MAP.md)", file=sys.stderr)
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
        help="configs/tool_home.json 규칙 변경(예: before_exempt 추가)으로 기존 파일이 "
        "새로 leak 판정이 된 경우만 기준선에 추가(줄이기도 같이 함). --reason 필수, "
        "판정 완화가 아니라 '이미 master 에 있던 파일' 임을 --verify-in-ref 로 검증.",
    )
    ap.add_argument("--reason", default=None)
    ap.add_argument(
        "--verify-in-ref",
        default="origin/master",
        help="--sync-baseline 전용: 새로 추가되는 각 파일이 이 ref 에도 이미 있어야 한다"
        "(이번 브랜치가 새로 만든 leak 은 절대 섞이지 않게).",
    )
    ap.add_argument("--classify", action="store_true")
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    root = a.root.resolve()
    cfg = load_config(root)

    if a.classify:
        for p in a.paths:
            print(f"{p}\t{'\t'.join(map(str, classify(p, cfg)))}")
        return 0
    if a.init_baseline:
        if (root / BASELINE).is_file():
            print("기준선이 이미 있다 — --update-baseline(줄이기만) 을 쓴다", file=sys.stderr)
            return 2
        leaks = current_leaks(root, cfg)
        _write_baseline(root, leaks, "최초 생성: 현재 집 밖 파일 전부")
        print(f"기준선 생성: {len(leaks)}개")
        return 0
    baseline = load_baseline(root)
    if a.update_baseline:
        leak_set = set(current_leaks(root, cfg))
        kept = sorted(baseline & leak_set)
        added = leak_set - baseline
        if added:
            print(f"기준선에 없는 집 밖 파일 {len(added)}개 — 기준선을 늘릴 수 없다(집으로 옮길 것):", file=sys.stderr)
            for f in sorted(added)[:20]:
                print("  " + f, file=sys.stderr)
            return 1
        _write_baseline(root, kept, f"하향 갱신: {len(baseline)} → {len(kept)}")
        print(f"기준선 {len(baseline)} → {len(kept)}")
        return 0
    if a.sync_baseline:
        if not a.reason:
            print("[tool_home_gate] --sync-baseline 은 --reason 이 필수(왜 기준선이 느는지 기록)", file=sys.stderr)
            return 2
        leak_set = set(current_leaks(root, cfg))
        added = leak_set - baseline
        removed = baseline - leak_set
        if added:
            not_in_ref = sorted(f for f in added if not _exists_in_ref(root, a.verify_in_ref, f))
            if not_in_ref:
                print(
                    f"[tool_home_gate] --sync-baseline 거부: {len(not_in_ref)}개가 {a.verify_in_ref} 에 없음"
                    " — 이번 브랜치가 새로 만든 leak 일 수 있다(판정 완화 금지):",
                    file=sys.stderr,
                )
                for f in not_in_ref[:20]:
                    print("  " + f, file=sys.stderr)
                return 1
        kept = sorted(leak_set)
        _write_baseline(root, kept, f"규칙 변경 동기화({a.reason}): +{len(added)} -{len(removed)} = {len(kept)}")
        print(f"[tool_home_gate] 기준선 동기화: {len(baseline)} → {len(kept)} (+{len(added)} -{len(removed)})")
        return 0
    if a.check_all:
        leaks = current_leaks(root, cfg)
        bad = [("A", f, classify(f, cfg)[1] or "?") for f in leaks if f not in baseline]
        stale = sorted(baseline - set(leaks))
        if stale:
            print(
                f"[tool_home_gate] 참고: 기준선 {len(stale)}건이 더 이상 집 밖이 아님 — --update-baseline 으로 줄일 것",
                file=sys.stderr,
            )
        if bad:
            _report(bad, cfg)
            return 1
        print(f"[tool_home_gate] PASS — 집 밖 {len(leaks)}건 모두 기준선(기존 부채) 안")
        return 0
    if a.staged:
        entries = staged_added(root)
        if not entries:
            return 0
        bad = violations(entries, cfg, baseline, root)
        if bad:
            _report(bad, cfg)
            return 1
        return 0
    ap.error("--staged / --check-all / --update-baseline / --init-baseline / --classify 중 하나")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
