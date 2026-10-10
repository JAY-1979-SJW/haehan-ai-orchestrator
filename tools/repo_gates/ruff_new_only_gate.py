"""ruff 검사를 "이번 커밋으로 새로 생긴 위반"만 차단하도록 감싼다.

배경(2026-09-28): pre-commit 훅의 `ruff check --fix`는 파일 전체를 검사해
자동수정 안 되는 위반이 하나라도 남으면 커밋을 막는다. 이 저장소는 BLE001
(blind-except, 2026-09-28 configs/ruff.toml select 에 추가)만 해도 기존
위반이 2,140건 있어서, 그 방식을 그대로 쓰면 그 부채가 있는 파일을 조금만
건드려도 매번 막혀 사실상 개발이 멈춘다. CLAUDE.md 도 "새 훅은 이번 편집으로
새로 생긴 오류만 차단해야 한다"고 명시하고 있어(기존 관례, 실제 구현은 안 돼
있었음) git diff로 "이번에 바뀐 줄"만 차단 대상으로 좁힌다.

같은 목적의 audit-kit(projects/audit-kit/src/audit_kit/gitutil.py)
changed_lines 알고리즘을 이 저장소용으로 의존성 추가 없이 독립 이식했다
(실측 검증된 hunk 파싱 로직 재사용, 로직만 복제 — import 는 아님, 별도
저장소라 패키지 의존을 걸 수 없음).

사용(참고 프로젝트: 32. Claude 개발표준/py_std_common.py 의 --cached 사용):
  python ruff_new_only_gate.py --config <ruff.toml> <file1> <file2> ...
반환: 0 = 새 위반 없음(기존 위반은 경고만 출력하고 통과), 1 = 새 위반 있음(차단)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))
from scripts.common.no_window import no_window_kwargs  # noqa: E402

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _nw_kwargs() -> dict[str, Any]:
    """no_window_kwargs() 는 dict[str, int] 로 좁게 선언돼 있어, subprocess.run(**...) 에
    그대로 풀면 mypy 가 여러 오버로드 중 하나로 못 좁혀 "No overload variant" 오류가 난다 —
    값 타입을 Any 로 넓혀 풀어주는 지점만 여기 한 곳으로 모은다(scripts/common/no_window.py
    자체는 안 건드림, 그 함수의 실제 동작·반환값은 그대로)."""
    return no_window_kwargs()


def _run_git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        **_nw_kwargs(),
    )


def _parse_diff_hunks(diff_text: str) -> dict[str, set[int]]:
    """`git diff --unified=0` 출력을 {파일 상대경로: 바뀐 줄 번호 집합}으로.
    audit-kit gitutil.py 의 동일 알고리즘(실측 테스트 검증됨)을 그대로 이식."""
    result: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current = None if path == "/dev/null" else path.removeprefix("b/")
            if current is not None:
                result.setdefault(current, set())
            continue
        m = _HUNK_RE.match(line)
        if m and current is not None:
            start = int(m.group(1))
            count = 1 if m.group(2) is None else int(m.group(2))
            if count:
                result[current].update(range(start, start + count))
    return result


def changed_lines_staged() -> dict[str, set[int]] | None:
    """스테이징(index) 대비 HEAD 기준 바뀐 줄. git 자체를 못 쓰면 None(판정 불가)."""
    # -M: git 설정(diff.renames)과 무관하게 이름 변경(git mv)을 감지한다 — 무변경 이동은 바뀐 줄 0, 편집한 이동은 그 줄만
    p = _run_git(["diff", "--cached", "-M", "--unified=0"])
    if p.returncode != 0:
        return None
    return _parse_diff_hunks(p.stdout)


def changed_lines_between(base_ref: str, head_ref: str | None) -> dict[str, set[int]] | None:
    """임의의 두 커밋/브랜치 사이 바뀐 줄. verify_change.py(CI) 재사용용 —
    2026-09-30 발견: CI의 "바뀐 파일 ruff" 체크가 이 함수 없이 head 쪽 ruff 결과를
    그대로 "새 문제"로 보고해, 손 안 댄 줄의 기존(pre-existing) 위반까지 전부 이번
    커밋 탓으로 돌려 FAIL시키고 있었다(defect_index 신규 항목). 같은 hunk 파싱
    알고리즘을 base/head 커밋 비교로 일반화해 재사용한다.
    head_ref 가 없으면(verify_change.py --head 생략 = 현재 작업트리) 커밋되지 않은
    변경까지 포함해 작업트리 대비로 비교한다."""
    ref_spec = f"{base_ref}..{head_ref}" if head_ref else base_ref
    p = _run_git(["diff", ref_spec, "-M", "--unified=0"])
    if p.returncode != 0:
        return None
    return _parse_diff_hunks(p.stdout)


def run_ruff_json(cfg: str, files: list[str]) -> list[dict]:
    p = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--config", cfg, "--output-format=json", *files],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
        **_nw_kwargs(),
    )
    try:
        return json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        # ruff 실행 자체가 실패(설정 오류 등) — stderr 를 그대로 보여주고 안전하게 차단
        print(p.stderr, file=sys.stderr)
        return [{"__ruff_failed__": True}]


def _reconfigure_streams():
    import contextlib

    # Windows 콘솔 기본 코드페이지(cp949)가 em-dash 등 출력에서 죽는 문제 방지
    # (이 세션에서 반복 발견된 패턴 — 이 스크립트 자신도 예외 아님)
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def _print_all_blocked(findings):
    print(f"[ruff-new-only] git diff 조회 실패 — 새/기존 구분 불가, 전체 {len(findings)}건을 차단 대상으로 처리")
    for f in findings:
        print(f"  {f['filename']}:{f['location']['row']} {f['code']} {f['message']}")


def _split_findings(findings, changed):
    new_findings, pre_existing = [], []
    for f in findings:
        try:
            rel = Path(f["filename"]).resolve().relative_to(ROOT).as_posix()
        except ValueError:
            rel = f["filename"]
        line = f["location"]["row"]
        lines_for_file = changed.get(rel)
        if lines_for_file is not None and line in lines_for_file:
            new_findings.append((rel, line, f))
        else:
            pre_existing.append((rel, line, f))
    return new_findings, pre_existing


def _report_split(new_findings, pre_existing):
    if pre_existing:
        print(f"[ruff-new-only] 기존 위반 {len(pre_existing)}건은 이번 변경과 무관 — 통과(참고용 경고만):")
        for rel, line, f in pre_existing[:20]:
            print(f"  (기존) {rel}:{line} {f['code']} {f['message']}")
        if len(pre_existing) > 20:
            print(f"  ... 외 {len(pre_existing) - 20}건")

    if new_findings:
        print(f"\n[ruff-new-only] 이번 변경으로 새로 생긴 위반 {len(new_findings)}건 — 커밋 차단:")
        for rel, line, f in new_findings:
            print(f"  {rel}:{line} {f['code']} {f['message']}")
        print("\n수정하거나, 의도된 경우 `# noqa: 코드 - 사유`를 추가한 뒤 재커밋하세요.")
        return 1
    return None


def main() -> int:
    _reconfigure_streams()

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("files", nargs="*")
    args = ap.parse_args()

    if not args.files:
        return 0

    findings = run_ruff_json(args.config, args.files)
    if findings and findings[0].get("__ruff_failed__"):
        return 1
    if not findings:
        return 0

    changed = changed_lines_staged()
    if changed is None:
        # git diff 자체를 못 읽으면 "새 것"인지 구분 불가 — 안전하게 기존 방식대로 전부 차단
        _print_all_blocked(findings)
        return 1

    new_findings, pre_existing = _split_findings(findings, changed)

    _early = _report_split(new_findings, pre_existing)
    if _early is not None:
        return _early

    return 0


if __name__ == "__main__":
    sys.exit(main())
