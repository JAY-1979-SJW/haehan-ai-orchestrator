"""Stop 훅 — 세션 종료 시 이번 세션에서 실제로 편집한 파일만 빠르게 재확인.

기존 `behavior_gate.py`는 그대로 두고(파일 보존 원칙), settings.json Stop 배열에
이 스크립트를 별도 항목으로 추가한다(§3.3 참조). 전체 pytest(21분+, 멈춤 결함 있음)는
여기서 돌리지 않는다 — 전체 검증은 `tools/verify_change.py`(커밋 시점) 담당.

2026-09-26 수정: 최초 구현은 `git status --porcelain` 전체를 대상으로 했으나, 이 저장소는
항상 다수의 미커밋 변경이 있어 "다른 세션이 건드린 파일"까지 이 세션의 Stop 게이트가
검사·차단하는 문제가 실측으로 확인됨(code-reviewer 서브에이전트 지적). 그래서 이제는
`post_edit_fast_gate.py` 가 PostToolUse 마다 기록하는 세션별 편집 목록
(`data/.session_edits/<session_id>.json`)만 검사한다 — 다른 세션·다른 시점의 미커밋
변경은 대상에서 제외된다.

동작:
1. stdin JSON 의 `stop_hook_active` 가 true 면 즉시 통과(무한 루프 방지, 공식 규약).
2. stdin JSON 의 `session_id` 로 세션별 편집 목록을 읽는다. 목록이 없거나 비어 있으면
   (아직 post_edit_fast_gate 가 한 번도 기록하지 않은 세션이거나 이번 세션에 편집이 전혀
   없었던 경우) 즉시 통과.
3. 목록에 있는 파일 중 현재 존재하는 것만: .py 는 ruff 기준선 diff + 매핑 테스트(최대 3개),
   .ts/.tsx 는 tsc(캐시 있으면 재사용) — post_edit_fast_gate 와 동일한 검사 함수 재사용.
4. 상한 30초. 실패/신규 오류 있으면 decision: "block" + reason.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

from tools.hooks.post_edit_fast_gate import (  # noqa: E402
    _check_python,
    _check_typescript,
    cleanup_old_session_edit_files,
    load_session_edits,
)

OVERALL_BUDGET_SECONDS = 30.0


def _session_edit_files(session_id: str | None) -> list[Path]:
    rel_paths = load_session_edits(session_id)
    files = []
    for rel in rel_paths:
        p = ROOT / rel
        if p.exists() and p.is_file():
            files.append(p)
    return files


def _collect_problems(files, start):
    problems: list[str] = []

    for f in files:
        if time.monotonic() - start > OVERALL_BUDGET_SECONDS:
            break
        suffix = f.suffix.lower()
        try:
            if suffix == ".py":
                rc = _check_python(f, start)
            elif suffix in (".ts", ".tsx"):
                rc = _check_typescript(f, start)
            else:
                rc = 0
            if rc != 0:
                problems.append(str(f.relative_to(ROOT)))
        except Exception as exc:  # noqa: BLE001 - Stop 훅 빠른검증 — stdin 파싱 실패나 개별 파일 검사 실패, 내부 전역 오류 모두 훅 자체를 무해하게 통과시키는 의도된 fail-open(코드 주석에 '# fail-open'으로 명시됨)
            sys.stderr.write(f"[stop_fast_verify] check failed for {f} (ignored): {exc}\n")
            continue
    return problems


def main() -> int:
    # 훅 출력은 하네스가 UTF-8 로 읽는다. 파이프로 연결되면 파이썬 기본 인코딩이 cp949 라 한글이 깨져
    # 사용자에게 안내 문구(예: /clear 안내)가 읽히지 않았다(2026-10-01).
    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 - Stop 훅 빠른검증 — stdin 파싱 실패나 개별 파일 검사 실패, 내부 전역 오류 모두 훅 자체를 무해하게 통과시키는 의도된 fail-open(코드 주석에 '# fail-open'으로 명시됨)
        payload = {}

    if payload.get("stop_hook_active"):
        return 0

    session_id = payload.get("session_id")
    cleanup_old_session_edit_files()

    files = _session_edit_files(session_id)
    if not files:
        # 이번 세션이 편집한 파일 기록이 없음 — 검사할 대상이 없으므로 즉시 통과.
        return 0

    start = time.monotonic()
    try:
        problems = _collect_problems(files, start)

        if problems:
            print(
                json.dumps(
                    {
                        "decision": "block",
                        "reason": (
                            "세션 변경분 빠른 게이트에서 문제 발견: "
                            + ", ".join(problems)
                            + " — stderr 로그를 참고해 고친 뒤 다시 종료하세요."
                        ),
                    }
                )
            )
            return 0

        return 0
    except Exception as exc:  # fail-open  # noqa: BLE001 - Stop 훅 빠른검증 — stdin 파싱 실패나 개별 파일 검사 실패, 내부 전역 오류 모두 훅 자체를 무해하게 통과시키는 의도된 fail-open(코드 주석에 '# fail-open'으로 명시됨)
        sys.stderr.write(f"[stop_fast_verify] internal error (ignored): {exc}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
