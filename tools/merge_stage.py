# module_category: gate
# primary_trade: common
"""지도↔골격 대조 의무화 — ③ 병합 게이트 (결함 #34 후속).

docs/specs/2026-09-24_skeleton_map_crosscheck_gate.md 참조.
stage/* 브랜치를 master 로 합치기 전에 tools/verify_change.py(9항목: 지도↔골격 대조 포함)를
강제로 돌려 PASS 일 때만 `git merge --ff-only` 하고, 검증표를 메시지로 담은 태그
`verified/<branch-이름(stage/ 접두 제거)>` 를 남긴다. PASS 기록 없이는 master 로 못 들어간다.

사용:
    python tools/merge_stage.py stage/skeleton-gate [--base master] [--dry-run]
    python tools/merge_stage.py stage/skeleton-gate --dry-run --no-verify-dry   # 순수 미리보기

안전장치(리뷰 반영, 2026-09-24):
  1. 현재 체크아웃된 브랜치(`git rev-parse --abbrev-ref HEAD`, 메인 저장소 루트 기준)가
     --base 와 다르면 실행을 거부한다. `git merge --ff-only <branch>` 는 "현재 체크아웃된
     브랜치"에 병합하므로, base 가 아닌 다른 브랜치에 있을 때 실행하면 엉뚱한 브랜치에
     합쳐진다. --dry-run 이어도 똑같이 거부한다(미리보기라도 틀린 전제로는 계획을 세우지 않는다).
  2. 태그 `verified/<name>` 이 이미 있으면 병합 전에 거부한다(먼저 확인, merge 시도 후가 아님).
  3. verify_change.py 가 죽거나(비정상 종료) 빈/깨진 JSON 을 내면 raw traceback 을 보여주지
     않고 깔끔하게 거부한다. `tempfile.mkstemp` 는 파일을 미리 만들어두므로 "파일이 있다"만으론
     내용이 유효하다는 증거가 안 된다 — 반드시 JSON 파싱 + 비어있지 않음 + 최소 스키마(dict,
     "ok" 키 존재)를 확인한 뒤에만 신뢰한다.
  4. 겹침 검사(브랜치 변경 파일 vs 메인 작업트리 미커밋 변경)는 `git status --porcelain -uall -z`
     (NUL 구분)로 한다. 개행/공백 분리는 파일명에 공백이 있거나 미추적 파일이 여러 개일 때
     깨지고, 비-ASCII/따옴표 경로도 잘못 잘린다.

--dry-run 의 의미: 기본값(플래그 없음)은 --dry-run 이어도 verify_change.py 를 실제로 실행한다
(임시 git worktree 를 만들어 기준 커밋을 체크아웃하고 테스트를 돌리는 무거운 작업 — 병합·태그만
건너뛴다). 병합 여부를 결정하는 진짜 판정 자체를 보고 싶다면 이 방식이 맞다. verify_change 조차
띄우지 않는 순수 계획 미리보기가 필요하면 --no-verify-dry 를 --dry-run 과 함께 준다(이때는
PASS/FAIL 판정을 하지 않고 "이런 커맨드를 실행할 예정"만 보여준다).

주의: 이 스크립트는 실제 병합을 수행할 수 있다(--dry-run 없이 실행 시). 운영 서버 재시작·DB 변경은
하지 않지만 master 브랜치 상태를 바꾸므로, 자동 스크립트/AI 가 사용자 승인 없이 실행하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[1]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
PY = sys.executable
VERIFY = ROOT / "tools" / "verify_change.py"


def run(args: list[str], cwd: Path = ROOT, **kw) -> subprocess.CompletedProcess:
    # core.quotepath=false: 비-ASCII(한글 등) 경로가 8진수 이스케이프로 감싸져 나오는 것을 막는다
    # (인코딩 견고성 — 안 하면 status/diff 파싱이 한글 파일명에서 깨진다).
    if args and args[0] == "git":
        args = [args[0], "-c", "core.quotepath=false", *args[1:]]
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kw,
    )


def tag_name_for(branch: str) -> str:
    """stage/skeleton-gate -> verified/skeleton-gate, 그 외는 verified/<branch>."""
    name = branch.split("/", 1)[1] if branch.startswith("stage/") else branch
    return f"verified/{name}"


def current_branch(root: Path = ROOT) -> str:
    """현재 체크아웃된 브랜치 이름(메인 저장소/현재 작업트리 기준)."""
    r = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    return r.stdout.strip()


def tag_exists(tag: str, root: Path = ROOT) -> bool:
    r = run(["git", "tag", "-l", tag], root)
    return bool(r.stdout.strip())


def _validate_verify_result(raw_text: str, returncode: int, stderr: str) -> dict:
    """verify_change.py 출력 JSON 이 유효한지 검사하고, 아니면 깔끔한 거부용 dict 를 만든다.

    파일 존재만으론 신뢰할 수 없다(mkstemp 가 빈 파일을 미리 만들어 둔다) — 반드시
    비어있지 않은지, 파싱되는지, 최소 스키마(dict + "ok" 키)를 갖췄는지까지 확인한다.
    """
    if not raw_text.strip():
        return {
            "ok": False,
            "report": (
                "[merge_stage] verify_change 가 결과 JSON을 만들지 못했습니다"
                f"(returncode={returncode}).\n--- stderr(끝부분) ---\n{stderr[-2000:]}"
            ),
            "changed": [],
        }
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "report": f"[merge_stage] verify_change 결과 JSON 파싱 실패: {exc}",
            "changed": [],
        }
    if not isinstance(data, dict) or "ok" not in data:
        return {
            "ok": False,
            "report": "[merge_stage] verify_change 결과 형식이 올바르지 않습니다(dict + 'ok' 키 필요).",
            "changed": [],
        }
    data.setdefault("report", "")
    data.setdefault("changed", [])
    return data


def run_verify_change(base: str, branch: str, json_path: Path) -> dict:
    """verify_change.py --base <base> --head <branch> --json <json_path> 실행 결과를 반환.

    verify_change.py 프로세스 자체가 죽어도(비정상 종료, 타임아웃 등) 예외를 여기서 삼키고
    깔끔한 거부 dict 를 돌려준다 — 호출자에 raw traceback 이 새어나가지 않게 한다.
    """
    try:
        proc = subprocess.run(
            [PY, str(VERIFY), "--base", base, "--head", branch, "--json", str(json_path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        returncode, stderr = proc.returncode, proc.stderr
    except Exception as exc:  # noqa: BLE001 - master 병합 전 verify_change 실행 게이트 — 서브프로세스 실행 자체가 실패하면 ok=False 인 실패 리포트를 반환하는 fail-closed 경로(실패 시 병합 진행 안 됨).
        return {
            "ok": False,
            "report": f"[merge_stage] verify_change 실행 자체가 실패했습니다: {type(exc).__name__}: {exc}",
            "changed": [],
        }

    try:
        raw_text = json_path.read_text(encoding="utf-8") if json_path.exists() else ""
    except OSError as exc:
        return {
            "ok": False,
            "report": f"[merge_stage] verify_change 결과 파일을 읽을 수 없습니다: {exc}",
            "changed": [],
        }
    return _validate_verify_result(raw_text, returncode, stderr)


def dirty_paths() -> set[str]:
    """메인 작업트리(현재 checkout)의 미커밋 변경 파일 경로 집합.

    `git status --porcelain -uall -z` (NUL 구분) 사용 — 개행/공백 분리는 파일명에 공백이
    있거나 비-ASCII/따옴표 경로가 있을 때 깨진다. rename 엔트리는 두 번째 NUL 조각에
    옛 경로가 따라오므로 그것도 같이 담는다(둘 다 "겹침"으로 봐도 안전한 쪽).
    """
    r = run(["git", "status", "--porcelain", "-uall", "-z"])
    raw = r.stdout
    if not raw:
        return set()
    tokens = raw.split("\0")
    out: set[str] = set()
    i = 0
    while i < len(tokens):
        entry = tokens[i]
        if not entry:
            i += 1
            continue
        status = entry[:2]
        path = entry[3:]
        if path:
            out.add(path)
        i += 1
        if ("R" in status or "C" in status) and i < len(tokens) and tokens[i]:
            out.add(tokens[i])
            i += 1
    return out


def overlap_with_dirty(changed: list[str]) -> list[str]:
    dirty = dirty_paths()
    return sorted(set(changed) & dirty)


def do_merge(branch: str) -> subprocess.CompletedProcess:
    return run(["git", "merge", "--ff-only", branch])


def do_tag(tag: str, message: str) -> subprocess.CompletedProcess:
    return run(["git", "tag", "-a", tag, "-m", message])


def _check_branch(a):
    branch_now = current_branch()
    if branch_now != a.base:
        print("=" * 60)
        print(f"[merge_stage] REFUSED — 현재 브랜치 '{branch_now}' 가 --base '{a.base}' 와 다릅니다.")
        print(f"    git checkout {a.base} 후 다시 시도하세요.")
        print("=" * 60)
        return 1
    return None


def _check_tag(a):
    tag = tag_name_for(a.branch)
    if tag_exists(tag):
        print("=" * 60)
        print(f"[merge_stage] REFUSED — 태그 '{tag}' 가 이미 있습니다(이미 검증·병합된 것으로 보입니다).")
        print("    다시 검증하려면 먼저 그 태그를 사람이 확인 후 지우세요.")
        print("=" * 60)
        return (1), None
    return None, tag


def _print_dry_preview(a, tag):
    print("[dry-run] --no-verify-dry — verify_change 를 실행하지 않는 순수 미리보기입니다.")
    print("[dry-run] PASS/FAIL 판정 없이, 실제 실행 시 수행할 순서만 보여줍니다:")
    print(f"[dry-run]   1) python tools/verify_change.py --base {a.base} --head {a.branch} --json <tmp>")
    print(f"[dry-run]   2) (PASS 시) git merge --ff-only {a.branch}")
    print(f"[dry-run]   3) (병합 성공 시) git tag -a {tag} -m <검증표>")


def _run_verify(a):
    fd, tmp_name = tempfile.mkstemp(suffix=".json", prefix="merge_stage_")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        result = run_verify_change(a.base, a.branch, tmp)
    finally:
        tmp.unlink(missing_ok=True)
    return result


def _print_verify_refused(a):
    print("=" * 60)
    print(f"[merge_stage] REFUSED — verify_change FAIL ({a.base}...{a.branch})")
    print("병합하지 않습니다. 리포트의 새 문제를 먼저 고치세요.")
    print("=" * 60)


def _print_overlap_refused(overlap):
    print("=" * 60)
    print("[merge_stage] REFUSED — 메인 작업트리에 겹치는 미커밋 변경이 있습니다:")
    for p in overlap[:20]:
        print("  - " + p)
    print("커밋하거나 stash 한 뒤 다시 시도하세요.")


def _print_dry_pass(a, tag):
    print("[dry-run] verify_change PASS — 실제로는 다음을 수행합니다:")
    print(f"[dry-run]   git merge --ff-only {a.branch}")
    print(f"[dry-run]   git tag -a {tag} -m <검증표>")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("branch", help="master 로 병합할 stage 브랜치")
    ap.add_argument("--base", default="master")
    ap.add_argument("--dry-run", action="store_true", help="병합·태그 없이 계획만 출력(verify_change 는 실제 실행함)")
    ap.add_argument(
        "--no-verify-dry",
        action="store_true",
        help="--dry-run 과 함께: verify_change 조차 실행하지 않는 순수 미리보기(PASS/FAIL 판정 없음)",
    )
    a = ap.parse_args(argv)

    # 1) 브랜치 확인 — --dry-run 이어도 동일하게 거부(틀린 전제로 계획 세우지 않음)
    _early = _check_branch(a)
    if _early is not None:
        return _early

    # 2) 태그 존재 확인 — 병합 시도 전에 먼저
    _early, tag = _check_tag(a)
    if _early is not None:
        return _early

    if a.dry_run and a.no_verify_dry:
        _print_dry_preview(a, tag)
        return 0

    result = _run_verify(a)

    report = result.get("report", "")
    print(report)

    if not result.get("ok"):
        _print_verify_refused(a)
        return 1

    changed = result.get("changed", [])
    overlap = overlap_with_dirty(changed)
    if overlap:
        _print_overlap_refused(overlap)
        print("=" * 60)
        return 1

    if a.dry_run:
        _print_dry_pass(a, tag)
        return 0

    merged = do_merge(a.branch)
    if merged.returncode != 0:
        print("[merge_stage] git merge --ff-only 실패:")
        print(merged.stdout)
        print(merged.stderr)
        return 1
    tagged = do_tag(tag, report)
    if tagged.returncode != 0:
        print("[merge_stage] 병합은 됐으나 태그 생성 실패:")
        print(tagged.stderr)
        return 1
    print(f"[merge_stage] PASS — {a.branch} → {a.base} 병합 완료, 태그 {tag} 생성")
    return 0


if __name__ == "__main__":
    sys.exit(main())
