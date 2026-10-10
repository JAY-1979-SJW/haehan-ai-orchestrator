# module_category: gate
# primary_trade: common
"""지도↔골격 대조 의무화 — ① 커밋 게이트 (결함 #34 후속).

docs/specs/2026-09-24_skeleton_map_crosscheck_gate.md 참조.
지도(map.json) 빌드 없이 초 단위로 끝나야 하므로, 여기서는 git 인덱스(스테이지)와
정본(configs/module_registry.json) · 선언 모듈(configs/module_boundaries.json)만 비교한다.
층간 위반·순환·전체 지도 기반 대조는 무거워서 ③ merge_stage.py(verify_change)가 담당한다.

판정 항목:
  1. 스테이지된 A(추가)/D(삭제)/R(이동) 코드 파일(.py/.ts/.tsx/.js/.mjs/.cjs) ↔ 스테이지된 정본 키
  2. 스테이지된 정본 전체 키 ⊆ 추적 파일, 추적 코드 파일 ⊆ 정본 (registry_sync 재사용)
  3. module_boundaries.json 선언 경로가 git 인덱스(git ls-files)에 존재
  4. 스테이지된 .py 파일에 새로 생긴 금지 import(기준선 밖) 없음

성능: 400개 스테이지 파일 기준 32.8s -> 목표 <3s.
  - 4번 검사는 _FORBIDDEN_IMPORT_PAIRS 의 소스 prefix 로 미리 경로를 걸러(대부분의 파일은
    금지 import 쌍의 "from" 쪽이 될 수 없다) 대상 파일 수를 줄인 뒤,
  - 남은 대상 파일 내용을 `git cat-file --batch` 한 번으로 모두 가져온다(파일마다
    `git show` 를 따로 부르던 방식은 스테이지 파일 수만큼 프로세스를 띄워 느렸다).
  - git 하위 프로세스 호출을 판정 항목 간에 공유해 중복 호출을 없앤다.

우회: 커밋 메시지에 trailer `Skip-Skeleton-Gate: <사유>` 를 적어도 pre-commit 훅은 그 시점에
아직 커밋 메시지를 보지 못한다(`git commit -m "..."` 의 -m 인자는 pre-commit 실행 후 최종
확정되며, .githooks/pre-commit 은 메시지 파일을 받지 않는다 — .githooks/commit-msg 만 받음).
그래서 이 게이트의 우회는 환경변수 SKELETON_GATE_SKIP_REASON 으로 받는다(quality_gate 류의
다른 게이트도 pre-commit 단계에선 메시지를 못 보므로 같은 방식이 이 저장소의 관례에 맞다).
사용 예: SKELETON_GATE_SKIP_REASON="긴급 롤백" git commit -m "..."
우회 시에도 scripts.common.op_log.log_op 로 감사 로그에 남긴다(다른 운영 로그와 같은 위치:
<메인 저장소 루트>/data/logs/ops.log, data/cdp.db ops_log 테이블 — 이 스크립트가 git worktree
안에서 실행돼도 `git rev-parse --git-common-dir` 로 메인 저장소 루트를 찾아 그 곳에 남긴다).
내부 오류(예상 못한 예외)가 나면: SKELETON_GATE_SKIP_REASON 이 있으면 그래도 우회(로그 남기고
exit 0), 없으면 FAIL 로 취급해 exit 1(원인을 화면에 보여주되 raw traceback 은 덤프하지 않음).

사용: python tools/code_map/skeleton_gate.py   (pre-commit 훅에서 호출, exit 0/1)
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.code_map.classify import CODE_SUFFIX  # noqa: E402
from tools.code_map.layer_rules import _FORBIDDEN_IMPORT_PAIRS  # noqa: E402
from tools.code_map.registry_sync import (  # noqa: E402
    diff_registry,
    tracked_code_files,
)

FIX_HINT = (
    "python tools/code_map/registry_sync.py --fix && "
    "git add configs/module_registry.json configs/module_registry.overrides.json"
)


def _git_args(args: list[str]) -> list[str]:
    """core.quotepath=false 강제 — 안 하면 비-ASCII(한글 등) 파일명이 8진수 이스케이프로
    감싸져 나와(예: "\\355\\225\\234....py") 접미사·경로 비교가 깨진다(인코딩 견고성)."""
    return [args[0], "-c", "core.quotepath=false", *args[1:]] if args and args[0] == "git" else args


def _run(args: list[str], root: Path) -> str:
    r = subprocess.run(
        _git_args(args),
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
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


def check_staged_adr(name_status: list[tuple[str, str, str]], reg_files: set[str]) -> list[str]:
    """A/D/R 스테이지 파일 ↔ 스테이지된 정본 키 일치 검사."""
    fails: list[str] = []
    for status, path, path2 in name_status:
        if status.startswith("A"):
            if PurePosixPath(path).suffix in CODE_SUFFIX and path not in reg_files:
                fails.append(f"추가된 코드 파일 '{path}' 가 정본에 없습니다(같은 커밋에 등록 필요)")
        elif status.startswith("D"):
            if PurePosixPath(path).suffix in CODE_SUFFIX and path in reg_files:
                fails.append(f"삭제된 코드 파일 '{path}' 가 정본에 아직 남아 있습니다")
        elif status.startswith("R") and PurePosixPath(path2).suffix in CODE_SUFFIX:
            if path in reg_files:
                fails.append(f"이동된 파일의 옛 키 '{path}' 가 정본에 남아 있습니다")
            if path2 not in reg_files:
                fails.append(f"이동된 파일의 새 키 '{path2}' 가 정본에 없습니다")
    return fails


def check_whole_registry(
    reg_files: set[str],
    root: Path,
    *,
    exclude_missing: set[str] | None = None,
    exclude_ghost: set[str] | None = None,
) -> list[str]:
    """check_staged_adr 이 이미 같은 파일을 보고했으면 여기서는 다시 보고하지 않는다(중복 제거)."""
    tracked = tracked_code_files(root)
    missing, ghost = diff_registry(reg_files, tracked)
    if exclude_missing:
        missing = missing - exclude_missing
    if exclude_ghost:
        ghost = ghost - exclude_ghost
    fails = []
    if missing:
        fails.append(f"정본에 없는 추적 코드 파일 {len(missing)}개 (예: {sorted(missing)[:5]})")
    if ghost:
        fails.append(f"정본에만 있고 추적 안 되는 항목 {len(ghost)}개 (예: {sorted(ghost)[:5]})")
    return fails


def check_declared_paths(root: Path) -> list[str]:
    """module_boundaries.json 선언 경로 존재 여부 — 디스크가 아니라 git 인덱스 기준.

    커밋 시점 판정이므로 스테이지-삭제(디스크엔 남아있지만 인덱스엔 없음)나
    스테이지-추가(디스크 상태와 무관)를 인덱스 기준으로 정확히 판정한다.
    """
    boundaries = root / "configs" / "module_boundaries.json"
    if not boundaries.exists():
        return []
    doc = json.loads(boundaries.read_text(encoding="utf-8"))
    tracked = set(_run(["git", "ls-files"], root).splitlines())
    fails = []
    for mod in doc.get("modules", []):
        for p in mod.get("paths", []):
            posix_p = p.replace("\\", "/")
            if posix_p.endswith("/"):
                if not any(t.startswith(posix_p) for t in tracked):
                    fails.append(f"선언 모듈 '{mod.get('name')}' 의 경로 '{p}' 아래 git 인덱스에 파일이 없습니다")
            elif posix_p not in tracked:
                fails.append(f"선언 모듈 '{mod.get('name')}' 의 경로 '{p}' 가 git 인덱스에 없습니다")
    return fails


def _load_baseline(root: Path) -> set[tuple[str, str]]:
    baseline = root / "configs" / "skeleton_gate_baseline.json"
    if not baseline.exists():
        return set()
    doc = json.loads(baseline.read_text(encoding="utf-8"))
    return {(e["file"], e["target"]) for e in doc.get("known_forbidden_imports", [])}


def _forbidden_src_prefixes() -> list[str]:
    """_FORBIDDEN_IMPORT_PAIRS 의 소스 prefix 를 경로 형태(점 -> 슬래시)로, 중복 없이."""
    seen: list[str] = []
    for src_prefix, _forbidden, _reason in _FORBIDDEN_IMPORT_PAIRS:
        p = src_prefix.replace(".", "/")
        if p not in seen:
            seen.append(p)
    return seen


def _needs_import_scan(path: str, prefixes: list[str]) -> bool:
    return any(path.startswith(p) for p in prefixes)


def _batch_cat_file(root: Path, paths: list[str]) -> dict[str, str]:
    """git cat-file --batch 로 스테이지된 여러 파일 내용을 프로세스 한 번에 가져온다.

    입력은 각 줄 ":<path>"(인덱스 stage 0 내용). 출력 형식(파일마다):
      "<sha> <type> <size>\\n<size바이트 내용>\\n"  또는 존재하지 않으면 "<입력> missing\\n".
    바이트 단위로 파싱해야 내용에 개행이 섞여도 안전하다.
    """
    if not paths:
        return {}
    stdin_data = ("\n".join(f":{p}" for p in paths) + "\n").encode("utf-8")
    proc = subprocess.run(
        _git_args(["git", "cat-file", "--batch"]),
        cwd=str(root),
        input=stdin_data,
        capture_output=True,
    )
    out: dict[str, str] = {}
    data = proc.stdout
    pos = 0
    idx = 0
    n = len(data)
    while pos < n and idx < len(paths):
        nl = data.find(b"\n", pos)
        if nl == -1:
            break
        header = data[pos:nl].decode("utf-8", errors="replace")
        pos = nl + 1
        parts = header.split()
        if len(parts) == 2 and parts[1] == "missing":
            out[paths[idx]] = ""
            idx += 1
            continue
        if len(parts) != 3:
            break
        _sha, _type, size_s = parts
        try:
            size = int(size_s)
        except ValueError:
            break
        content = data[pos : pos + size]
        pos += size + 1  # trailing newline git appends after the blob
        out[paths[idx]] = content.decode("utf-8", errors="replace")
        idx += 1
    return out


def check_forbidden_imports(root: Path, name_status: list[tuple[str, str, str]]) -> list[str]:
    """스테이지된 .py 파일에서 새로 생긴 금지 import (기준선 밖)."""
    baseline = _load_baseline(root)
    fails: list[str] = []
    staged_py = [
        p
        for status, p, p2 in name_status
        for p in ([p2] if status.startswith("R") else [p])
        if p.endswith(".py") and not status.startswith("D")
    ]
    if not staged_py:
        return fails

    prefixes = _forbidden_src_prefixes()
    candidates = [p for p in staged_py if _needs_import_scan(p, prefixes)]
    if not candidates:
        return fails

    contents = _batch_cat_file(root, candidates)
    for path in candidates:
        content = contents.get(path, "")
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


def _main_repo_root(root: Path) -> Path:
    """git worktree 안에서 실행돼도 메인 저장소 루트를 찾는다.

    `git rev-parse --git-common-dir` 는 worktree 들이 공유하는 진짜 .git 디렉터리를 준다.
    그 부모가 메인 저장소 루트(worktree 자신의 .git 디렉터리는 <main>/.git/worktrees/<name> 이라
    공유 디렉터리와 다르다). 실패하면(git 오류 등) 안전하게 root 자신을 돌려준다.
    """
    with contextlib.suppress(Exception):
        r = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        common_dir = r.stdout.strip()
        if common_dir:
            common_path = Path(common_dir)
            if not common_path.is_absolute():
                common_path = (root / common_path).resolve()
            else:
                common_path = common_path.resolve()
            return common_path.parent
    return root


def _log_bypass(reason: str, fails: list[str], root: Path = ROOT) -> None:
    with contextlib.suppress(Exception):
        from scripts.common.op_log import log_op

        main_root = _main_repo_root(root)
        log_op(
            "skeleton_gate_bypass",
            ok=True,
            message=f"우회 사유: {reason}",
            fail_count=len(fails),
            fails="; ".join(fails[:10]),
            root=main_root,
        )


def evaluate(root: Path = ROOT) -> tuple[bool, list[tuple[str, bool, list[str]]]]:
    """모든 판정 항목을 돌려 (전체 통과 여부, [(항목명, 통과여부, 실패목록)]) 반환. 부작용 없음(읽기 전용)."""
    name_status = _name_status(root)
    reg_files = _staged_registry_files(root)
    results: list[tuple[str, bool, list[str]]] = []

    if reg_files is None:
        results.append(("staged_registry_readable", False, ["configs/module_registry.json 을 읽을 수 없습니다"]))
    else:
        f1 = check_staged_adr(name_status, reg_files)
        results.append(("staged_adr_vs_registry", not f1, f1))

        added_code = {
            p for status, p, _p2 in name_status if status.startswith("A") and PurePosixPath(p).suffix in CODE_SUFFIX
        }
        deleted_code = {
            p for status, p, _p2 in name_status if status.startswith("D") and PurePosixPath(p).suffix in CODE_SUFFIX
        }
        f2 = check_whole_registry(reg_files, root, exclude_missing=added_code, exclude_ghost=deleted_code)
        results.append(("registry_vs_tracked", not f2, f2))

    f3 = check_declared_paths(root)
    results.append(("declared_module_paths_exist", not f3, f3))

    f4 = check_forbidden_imports(root, name_status)
    results.append(("no_new_forbidden_imports", not f4, f4))

    all_fails = [f for _n, _ok, fails in results for f in fails]
    return not all_fails, results


def run(root: Path = ROOT) -> int:
    """판정 실행 + 출력 + 우회 처리. exit code(0/1) 반환.

    evaluate() 자체가 예상 못한 예외를 던지면(버그·환경 문제):
      - SKELETON_GATE_SKIP_REASON 이 있으면 그래도 우회(exit 0, 감사 로그 남김)
      - 없으면 FAIL 로 취급(exit 1) — raw traceback 대신 원인 한 줄만 보여준다.
    """
    try:
        ok, results = evaluate(root)
    except Exception as exc:  # noqa: BLE001 - 코드맵 골격 게이트 — evaluate() 내부 오류 시 명시적 SKELETON_GATE_SKIP_REASON 환경변수가 없으면 FAIL(exit 1)로 취급하는 fail-closed 경로, 우회 시에도 감사 로그(_log_bypass) 남김.
        print(f"[skeleton_gate] 내부 오류로 판정할 수 없습니다: {type(exc).__name__}: {exc}")
        reason = _bypass_reason()
        if reason:
            print(f"[skeleton_gate] SKELETON_GATE_SKIP_REASON 우회(내부 오류): {reason}")
            _log_bypass(reason, [f"internal error: {type(exc).__name__}: {exc}"], root)
            return 0
        print('우회(비상시만, 감사 기록됨): SKELETON_GATE_SKIP_REASON="사유" git commit ...')
        return 1

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
        _log_bypass(reason, all_fails, root)
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
