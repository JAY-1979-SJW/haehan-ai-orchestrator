"""G12 — 신규 구조동일 중복 차단 게이트.

staged(또는 지정한) .py 파일의 함수 중 '구조 동일 중복'(이름·상수를 지운 AST 해시가
같음, 본문 4문장 이상)이 저장소의 다른 파일에 이미 있으면 커밋을 차단한다.
기존에 이미 있던 중복 묶음은 기준선(configs/dup_baseline.json)에 고정해 두고 건드리지
않는다 — "새로 생긴 중복만" 막는다(CLAUDE.md 공통 원칙과 동일).

알고리즘은 tools/repo_gates/_dup_structure_hash.py(= C:/work/audit-tools/dupscan/src/dupscan/
extractor.py에서 그대로 가져온 구조 해시)를 쓴다. dupscan 자체를 CI에 설치하지 않는 이유:
그 저장소는 이 PC의 개인 작업 경로(C:/work/audit-tools/dupscan)에만 있고 패키지로 배포돼
있지 않아, CI 러너(다른 머신·컨테이너)에서는 pip install -e 할 경로가 없다. 알고리즘
핵심(정규화 + sha1, 약 40줄)만 저장소에 들여 외부 경로 의존을 없앴다(재구현이 아니라
동일 로직 이전).

사용:
  build-baseline            오늘 기준 전체 저장소를 스캔해 기존 중복 묶음을 기준선에 기록
  check --staged            git staged .py 파일만 검사(pre-commit)
  check <file> [file...]    지정 파일만 검사(CI verify에서 명시적으로 넘길 때)
  check --all               저장소 전체 비교(CI): 기준선에 없는 중복 묶음이 하나라도 있으면 실패, 기준선에만 남은(사라진) 해시는 알려 준다.
                            staged·변경 파일 검사는 새 중복이 '다른 파일'에 생기면 놓칠 수 있어(양쪽이 모두 새 파일이 아니면 한쪽만 검사) 전체 비교를 더한다.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

# 독립 실행 도구 — 시험이 이 파일만 임시 저장소에 복사해 돌리므로 정본(scripts.common.app_paths)에 기대지 않고 파일 위치로 루트를 잡는다.
ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))  # sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.repo_gates._dup_structure_hash import (  # noqa: E402
    body_statement_count,
    is_test_path,
    iter_functions,
    normalize,
    structure_hash,
)

BASELINE_PATH = ROOT / "configs" / "dup_baseline.json"
MIN_STATEMENTS = 4

EXEMPT_DIR_PREFIXES = (
    "scripts/archive/",
    "apps/",
)


def is_exempt(rel_path: str) -> bool:
    p = rel_path.replace("\\", "/")
    if any(p.startswith(d) for d in EXEMPT_DIR_PREFIXES):
        return True
    return is_test_path(p)


def _git(args: list[str]) -> str:
    out = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return out.stdout


def tracked_py_files() -> list[str]:
    return [f for f in _git(["ls-files", "*.py"]).splitlines() if f]


def staged_py_files() -> list[str]:
    raw = _git(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    return [f for f in raw.splitlines() if f.endswith(".py")]


def extract_fingerprints(rel_path: str, source: str) -> list[tuple[str, str, int]]:
    """(qualname, structure_hash, 문장수) 목록. 파싱 실패 시 빈 목록(문법 오류는 다른 게이트가 잡음)."""
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError:
        return []
    out = []
    for qualname, node in iter_functions(tree):
        if body_statement_count(node) < MIN_STATEMENTS:
            continue
        out.append((qualname, structure_hash(normalize(node)), node.lineno))
    return out


def build_repo_index(*, exclude_exempt: bool = True) -> dict[str, list[tuple[str, str]]]:
    """해시 → [(file, qualname), ...] 전체 저장소 색인(예외 폴더/시험 파일 제외)."""
    index: dict[str, list[tuple[str, str]]] = {}
    for rel in tracked_py_files():
        if exclude_exempt and is_exempt(rel):
            continue
        full = ROOT / rel
        try:
            source = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for qualname, h, _lineno in extract_fingerprints(rel, source):
            index.setdefault(h, []).append((rel, qualname))
    return index


def cmd_build_baseline(_args: argparse.Namespace) -> int:
    index = build_repo_index()
    dup_hashes = {h: locs for h, locs in index.items() if len(locs) >= 2}
    payload = {
        "generated_by": "tools/repo_gates/dup_gate.py build-baseline",
        "source_algorithm": "dupscan extractor.py (구조 해시 동일 로직 이전, tools/repo_gates/_dup_structure_hash.py)",
        "min_statements": MIN_STATEMENTS,
        "hash_count": len(dup_hashes),
        "hashes": {h: [f"{f}:{q}" for f, q in sorted(locs)] for h, locs in sorted(dup_hashes.items())},
    }
    tmp = BASELINE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(BASELINE_PATH)
    print(f"기준선 저장: {BASELINE_PATH} ({len(dup_hashes)}개 중복 해시 묶음)")
    return 0


def load_baseline_hashes() -> set[str]:
    if not BASELINE_PATH.exists():
        return set()
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return set(data.get("hashes", {}).keys())


def _read_files_from(path: str) -> list[str]:
    """`--files-from PATH`(한 줄에 파일 1개, `-` 면 표준입력) — 명령줄 인자 길이 한도(WinError 206/
    'Argument list too long')를 넘는 대량 변경 목록을 파일로 넘길 때 쓴다(PR #165, 변경 2567개)."""
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _normalize_targets(args: argparse.Namespace) -> list[str]:
    files_from = getattr(args, "files_from", None)
    if files_from:
        targets = _read_files_from(files_from)
    else:
        targets = staged_py_files() if args.staged else args.files
    targets = [PurePosixPath(t.replace("\\", "/")).as_posix() for t in targets]
    return [t for t in targets if not is_exempt(t)]


def _find_blocked(
    targets: list[str], baseline_hashes: set[str], repo_index: dict[str, list[tuple[str, str]]]
) -> list[str]:
    blocked: list[str] = []
    for rel in targets:
        full = ROOT / rel
        if not full.exists():
            continue  # 삭제된 파일
        try:
            source = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for qualname, h, lineno in extract_fingerprints(rel, source):
            if h in baseline_hashes:
                continue  # 기존 중복(기준선) — 통과
            others = [loc for loc in repo_index.get(h, []) if loc != (rel, qualname)]
            if not others:
                continue
            other_desc = ", ".join(f"{f}:{q}" for f, q in others[:3])
            blocked.append(f"{rel}:{lineno} {qualname}() — 구조 동일 중복 ↔ {other_desc}")
    return blocked


def _print_blocked(blocked: list[str]) -> None:
    print("=" * 60)
    print("[dup-gate/G12] 새 구조동일 중복 함수 발견 — 커밋 차단:")
    for b in blocked[:20]:
        print(f"    - {b}")
    if len(blocked) > 20:
        print(f"    ... 외 {len(blocked) - 20}건")
    print("    기존 구현을 재사용하거나 공용 함수로 추출하세요.")
    print("    기존부터 있던 중복이면 configs/dup_baseline.json에 이미 등록돼 있어야 합니다")
    print("    (등록 안 돼 있다면 실제로 새로 생긴 중복입니다).")
    print("=" * 60)


def cmd_check_all(_args: argparse.Namespace) -> int:
    """저장소 전체에서 구조 동일 중복 묶음을 모아 기준선과 비교한다(새 묶음 = 실패, 사라진 기준선 해시 = 안내)."""
    baseline_hashes = load_baseline_hashes()
    index = build_repo_index()
    dups = {h: locs for h, locs in index.items() if len(locs) >= 2}
    new = sorted(set(dups) - baseline_hashes)
    stale = sorted(baseline_hashes - set(dups))
    if stale:
        print(
            f"[dup-gate/G12] 참고: 기준선에만 남은(더는 중복이 아닌) 해시 {len(stale)}건 — build-baseline 으로 줄일 수 있다.",
            file=sys.stderr,
        )
    if new:
        print("=" * 60)
        print(f"[dup-gate/G12] 기준선에 없는 새 중복 묶음 {len(new)}건 — 실패:")
        for h in new[:20]:
            print(f"    - {h[:8]}: " + " ↔ ".join(f"{f}:{q}" for f, q in sorted(dups[h])[:4]))
        print("    기존 구현을 재사용하거나 공용 함수로 추출하세요(기준선에 넣어 가리지 마세요).")
        print("=" * 60)
        return 1
    print(f"[dup-gate/G12] PASS — 중복 묶음 {len(dups)}건 모두 기준선(기존 부채) 안")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    if getattr(args, "all", False):
        return cmd_check_all(args)
    targets = _normalize_targets(args)
    if not targets:
        return 0

    baseline_hashes = load_baseline_hashes()
    repo_index = build_repo_index()
    blocked = _find_blocked(targets, baseline_hashes, repo_index)

    if blocked:
        _print_blocked(blocked)
        return 1
    return 0


def _warn_if_wrong_python_version() -> None:
    """structure_hash() 는 ast.dump() 출력에 의존하는데, 그 포맷이 파이썬 버전마다 달라
    같은 코드도 다른 해시가 나온다(2026-10-09, dup_baseline 재검토 중 python 3.12 와
    py -3.14 사이에서 실제로 재현). 기준선은 constraints.txt 가 고정한 3.14 로 만들어졌으므로
    다른 버전으로 돌리면 전부 "새 중복"으로 보이는 거짓 대량 diff 가 난다."""
    if sys.version_info[:2] != (3, 14):
        print(
            f"[dup-gate/G12] 경고: 이 파이썬({sys.version_info[0]}.{sys.version_info[1]})"
            " 은 기준선을 만든 버전(3.14)과 다릅니다 — structure_hash 가 달라져 거짓 diff 가"
            " 날 수 있습니다. `py -3.14 ...` 로 다시 실행하세요.",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    for stream in (
        sys.stdout,
        sys.stderr,
    ):  # 참고·차단 메시지는 stderr 로도 나간다 — 콘솔 코드페이지(cp949)에서 한글이 깨지지 않게 둘 다 고정
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    _warn_if_wrong_python_version()
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("build-baseline").set_defaults(func=cmd_build_baseline)

    p_check = sub.add_parser("check")
    p_check.add_argument("files", nargs="*")
    p_check.add_argument("--staged", action="store_true")
    p_check.add_argument("--all", action="store_true", help="저장소 전체를 기준선과 비교(CI)")
    p_check.add_argument(
        "--files-from", help="대상 파일 목록(한 줄에 하나) 경로, '-' 면 표준입력 — 명령줄 인자 한도 회피용"
    )
    p_check.set_defaults(func=cmd_check)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
