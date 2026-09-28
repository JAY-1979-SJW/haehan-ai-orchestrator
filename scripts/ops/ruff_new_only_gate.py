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

ROOT = Path(__file__).resolve().parents[2]  # scripts/ops/ -> repo root
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


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
    p = _run_git(["diff", "--cached", "--unified=0"])
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
    )
    try:
        return json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        # ruff 실행 자체가 실패(설정 오류 등) — stderr 를 그대로 보여주고 안전하게 차단
        print(p.stderr, file=sys.stderr)
        return [{"__ruff_failed__": True}]


def main() -> int:
    import contextlib

    # Windows 콘솔 기본 코드페이지(cp949)가 em-dash 등 출력에서 죽는 문제 방지
    # (이 세션에서 반복 발견된 패턴 — 이 스크립트 자신도 예외 아님)
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

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
        print(f"[ruff-new-only] git diff 조회 실패 — 새/기존 구분 불가, 전체 {len(findings)}건을 차단 대상으로 처리")
        for f in findings:
            print(f"  {f['filename']}:{f['location']['row']} {f['code']} {f['message']}")
        return 1

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
