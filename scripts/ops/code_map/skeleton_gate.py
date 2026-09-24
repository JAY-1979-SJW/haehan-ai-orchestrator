# module_category: gate
# primary_trade: common
"""지도↔골격 대조 의무화 — ① 커밋 게이트 (결함 #34 후속).

docs/specs/2026-09-24_skeleton_map_crosscheck_gate.md 참조.
지도(map.json) 빌드 없이 초 단위로 끝나야 하므로, 여기서는 git 인덱스(스테이지)와
정본(configs/module_registry.json) · 선언 모듈(configs/module_boundaries.json)만 비교한다.
층간 위반·순환·전체 지도 기반 대조는 무거워서 ③ merge_stage.py(verify_change)가 담당한다.

판정 항목:
  1. 스테이지된 A(추가)/D(삭제)/R(이동) 코드 파일(.py/.ts/.tsx/.js/.mjs) ↔ 스테이지된 정본 키
  2. 스테이지된 정본 전체 키 ⊆ 추적 파일, 추적 코드 파일 ⊆ 정본 (registry_sync 재사용)
  3. module_boundaries.json 선언 경로가 디스크에 존재
  4. 스테이지된 .py 파일에 새로 생긴 금지 import(기준선 밖) 없음

우회: 커밋 메시지에 trailer `Skip-Skeleton-Gate: <사유>` 를 적어도 pre-commit 훅은 그 시점에
아직 커밋 메시지를 보지 못한다(`git commit -m "..."` 의 -m 인자는 pre-commit 실행 후 최종
확정되며, .githooks/pre-commit 은 메시지 파일을 받지 않는다 — .githooks/commit-msg 만 받음).
그래서 이 게이트의 우회는 환경변수 SKELETON_GATE_SKIP_REASON 으로 받는다(quality_gate 류의
다른 게이트도 pre-commit 단계에선 메시지를 못 보므로 같은 방식이 이 저장소의 관례에 맞다).
사용 예: SKELETON_GATE_SKIP_REASON="긴급 롤백" git commit -m "..."
우회 시에도 scripts.op_log.log_op 로 감사 로그에 남긴다(다른 운영 로그와 같은 위치:
data/logs/ops.log, data/cdp.db ops_log 테이블).

사용: python scripts/ops/code_map/skeleton_gate.py   (pre-commit 훅에서 호출, exit 0/1)
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
CODE_SUFFIX = (".py", ".ts", ".tsx", ".js", ".mjs")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops.code_map.registry_sync import (  # noqa: E402
    diff_registry,
    tracked_code_files,
)
from scripts.ops.codebase_layer_audit import _FORBIDDEN_IMPORT_PAIRS  # noqa: E402

FIX_HINT = (
    "python scripts/ops/code_map/registry_sync.py --fix && "
    "git add configs/module_registry.json configs/module_registry.overrides.json"
)


def _run(args: list[str], root: Path) -> str:
    r = subprocess.run(args, cwd=str(root), capture_output=True, text=True)
    return r.stdout


def _staged_registry_files(root: Path) -> set[str] | None:
    """스테이지(git 인덱스)된 module_registry.json 의 files 키 집합.

    스테이지 안 됐으면(working tree 에만 변경) HEAD 버전을 본다 — 그래도 없으면 None.
    """
    out = _run(["git", "show", ":configs/module_registry.json"], root)
    text = out if out.strip() else _run(["git", "show", "HEAD:configs/module_registry.json"], root)
    if not text.strip():
        return None
    try:
        return set(json.loads(text).get("files", {}).keys())
    except json.JSONDecodeError:
        return None


def _name_status(root: Path) -> list[tuple[str, str, str]]:
    """[(status, path, path2)] — R 은 path=old, path2=new."""
    out = _run(["git", "diff", "--cached", "--name-status", "-M"], root)
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        status = parts[0]
        if status.startswith("R") and len(parts) == 3:
            rows.append((status, parts[1], parts[2]))
        elif len(parts) == 2:
            rows.append((status, parts[1], ""))
    return rows


def check_staged_adr(reg_files: set[str], root: Path) -> list[str]:
    """A/D/R 스테이지 파일 ↔ 스테이지된 정본 키 일치 검사."""
    fails: list[str] = []
    for status, path, path2 in _name_status(root):
        if status.startswith("A"):
            if PurePosixPath(path).suffix in CODE_SUFFIX and path not in reg_files:
                fails.append(f"추가된 코드 파일 '{path}' 가 정본에 없습니다(같은 커밋에 등록 필요)")
        elif status.startswith("D"):
            if PurePosixPath(path).suffix in CODE_SUFFIX and path in reg_files:
                fails.append(f"삭제된 코드 파일 '{path}' 가 정본에 아직 남아 있습니다")
        elif status.startswith("R"):
            if PurePosixPath(path2).suffix in CODE_SUFFIX:
                if path in reg_files:
                    fails.append(f"이동된 파일의 옛 키 '{path}' 가 정본에 남아 있습니다")
                if path2 not in reg_files:
                    fails.append(f"이동된 파일의 새 키 '{path2}' 가 정본에 없습니다")
    return fails


def check_whole_registry(reg_files: set[str], root: Path) -> list[str]:
    tracked = tracked_code_files(root)
    missing, ghost = diff_registry(reg_files, tracked)
    fails = []
    if missing:
        fails.append(f"정본에 없는 추적 코드 파일 {len(missing)}개 (예: {sorted(missing)[:5]})")
    if ghost:
        fails.append(f"정본에만 있고 추적 안 되는 항목 {len(ghost)}개 (예: {sorted(ghost)[:5]})")
    return fails


def check_declared_paths(root: Path) -> list[str]:
    boundaries = root / "configs" / "module_boundaries.json"
    if not boundaries.exists():
        return []
    doc = json.loads(boundaries.read_text(encoding="utf-8"))
    fails = []
    for mod in doc.get("modules", []):
        for p in mod.get("paths", []):
            target = root / p
            if not target.exists():
                fails.append(f"선언 모듈 '{mod.get('name')}' 의 경로 '{p}' 가 디스크에 없습니다")
    return fails


def _load_baseline(root: Path) -> set[tuple[str, str]]:
    baseline = root / "configs" / "skeleton_gate_baseline.json"
    if not baseline.exists():
        return set()
    doc = json.loads(baseline.read_text(encoding="utf-8"))
    return {(e["file"], e["target"]) for e in doc.get("known_forbidden_imports", [])}


def check_forbidden_imports(root: Path) -> list[str]:
    """스테이지된 .py 파일에서 새로 생긴 금지 import (기준선 밖)."""
    baseline = _load_baseline(root)
    fails: list[str] = []
    staged_py = [
        p
        for status, p, p2 in _name_status(root)
        for p in ([p2] if status.startswith("R") else [p])
        if p.endswith(".py") and not status.startswith("D")
    ]
    if not staged_py:
        return fails
    for path in staged_py:
        content = _run(["git", "show", f":{path}"], root)
        if not content:
            continue
        src_mod = path.replace("/", ".").removesuffix(".py")
        for src_prefix, forbidden_prefix, reason in _FORBIDDEN_IMPORT_PAIRS:
            if not src_mod.startswith(src_prefix.replace("/", ".")):
                continue
            fp = re.escape(forbidden_prefix)
            static_pat = re.compile(r"^\s*(?:import|from)\s+(" + fp + r"[\w.]*)", re.MULTILINE)
            dyn_pat = re.compile(r"import_module\(\s*[\"'](" + fp + r"[\w.]*)[\"']")
            hits = set(static_pat.findall(content)) | set(dyn_pat.findall(content))
            for target in hits:
                if (path, target) in baseline:
                    continue
                fails.append(f"'{path}' 에 새 금지 import '{target}' — {reason}")
    return fails


def _bypass_reason() -> str:
    return os.environ.get("SKELETON_GATE_SKIP_REASON", "").strip()


def _log_bypass(reason: str, fails: list[str]) -> None:
    with contextlib.suppress(Exception):
        from scripts.op_log import log_op

        log_op(
            "skeleton_gate_bypass",
            ok=True,
            message=f"우회 사유: {reason}",
            fail_count=len(fails),
            fails="; ".join(fails[:10]),
        )


def evaluate(root: Path = ROOT) -> tuple[bool, list[tuple[str, bool, list[str]]]]:
    """모든 판정 항목을 돌려 (전체 통과 여부, [(항목명, 통과여부, 실패목록)]) 반환. 부작용 없음(읽기 전용)."""
    reg_files = _staged_registry_files(root)
    results: list[tuple[str, bool, list[str]]] = []

    if reg_files is None:
        results.append(("staged_registry_readable", False, ["configs/module_registry.json 을 읽을 수 없습니다"]))
    else:
        f1 = check_staged_adr(reg_files, root)
        results.append(("staged_adr_vs_registry", not f1, f1))
        f2 = check_whole_registry(reg_files, root)
        results.append(("registry_vs_tracked", not f2, f2))

    f3 = check_declared_paths(root)
    results.append(("declared_module_paths_exist", not f3, f3))

    f4 = check_forbidden_imports(root)
    results.append(("no_new_forbidden_imports", not f4, f4))

    all_fails = [f for _n, _ok, fails in results for f in fails]
    return not all_fails, results


def run(root: Path = ROOT) -> int:
    """판정 실행 + 출력 + 우회 처리. exit code(0/1) 반환."""
    ok, results = evaluate(root)
    all_fails = [f for _n, _ok, fails in results for f in fails]

    for name, item_ok, fails in results:
        print(f"[{'PASS' if item_ok else 'FAIL'}] {name}")
        for f in fails:
            print(f"    - {f}")

    if ok:
        return 0

    reason = _bypass_reason()
    if reason:
        print(f"[skeleton_gate] SKELETON_GATE_SKIP_REASON 우회: {reason}")
        _log_bypass(reason, all_fails)
        return 0

    print("=" * 60)
    print(f"[skeleton_gate] FAIL {len(all_fails)}건 — 지도↔골격 불일치")
    print("고치는 명령:")
    print("  " + FIX_HINT)
    print('우회(비상시만, 감사 기록됨): SKELETON_GATE_SKIP_REASON="사유" git commit ...')
    print("=" * 60)
    return 1


def main() -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    return run(ROOT)


if __name__ == "__main__":
    sys.exit(main())
