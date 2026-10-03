"""audit-kit 게이트 — 코드를 쓸 때(PostToolUse)와 세션을 끝낼 때(Stop) audit-kit 의 파일 단위 개발 기준서 검사를 건다.

이 저장소에는 이미 편집 직후 ruff(신규 오류)·영향 테스트를 보는 `post_edit_fast_gate` 가 있다. 이 게이트는 그것이
보지 않는 것을 맡는다: audit-kit 의 **개발 기준서 파일 단위 검사(조항 ID, 신규/기존 구분)** 와 **순환 import**.
ruff 는 audit-kit 쪽에서 끄고(`pyproject.toml` `[tool.audit-kit] hook_tools = "design"`) 중복 실행하지 않는다. **mypy 는 이 게이트가
직접 돌린다**: audit-kit 가상환경의 mypy 로 파일 하나를 검사해 HEAD 버전에 없던 **신규 타입 오류만** 막는다(ruff 와 같은 원칙).

모드
- `--post-edit` (PostToolUse): stdin 의 편집 파일 한 개를 `audit-kit hook` 으로 검사. **이번 편집이 만든 문제**가 있으면 exit 2 (Claude 가 보고 고친다).
- `--stop` (Stop): 이번 세션이 편집한 .py 들을 같은 방식으로 다시 검사. 신규 문제가 있으면 `decision: block`.

audit-kit 위치(이 PC 전용 경로를 고정하지 않는다): 환경변수 `AUDIT_KIT_BIN` → 저장소 위쪽 폴더의 `audit-tools/audit-kit/.venv` → PATH.
없으면 **검사를 생략하고 이유를 알린다**(설치 안 된 PC·CI 를 막지 않는 fail-open — 설치된 PC 에서는 필수로 동작).
`(기존)` 표시가 붙은 항목(이번 편집 이전부터 있던 문제)과 환경 잡음(`import-not-found`)은 막지 않는다.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PER_FILE_TIMEOUT_S = 60
STOP_BUDGET_S = 90
MAX_SHOWN = 30
_NOISE = ("import-not-found", "import-untyped")  # audit-kit 가상환경에 프로젝트 의존성이 없어 생기는 잡음
_EXE_NAMES = ("audit-kit.exe", "audit-kit")


def find_audit_kit(root: Path | None = None, env: dict[str, str] | None = None) -> list[str] | None:
    """audit-kit 실행 명령(리스트). 못 찾으면 None. `.py` 로 지정하면 현재 파이썬으로 실행한다(시험용)."""
    root = root or ROOT  # 호출 시점의 ROOT(시험에서 바꿀 수 있게 기본값을 import 때 고정하지 않는다)
    env = os.environ if env is None else env
    explicit = (env.get("AUDIT_KIT_BIN") or "").strip()
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return [sys.executable, str(path)] if path.suffix == ".py" else [str(path)]
        return None
    for parent in [root, *root.parents][:8]:
        scripts = parent / "audit-tools" / "audit-kit" / ".venv" / "Scripts"
        for name in _EXE_NAMES:
            if (scripts / name).is_file():
                return [str(scripts / name)]
    found = shutil.which("audit-kit")
    return [found] if found else None


def new_findings(stderr_text: str) -> list[str]:
    """audit-kit hook 출력에서 이번 편집이 만든 항목만 골라낸다: `[`로 시작하고 `(기존)`·환경 잡음이 아닌 줄."""
    out = []
    for line in stderr_text.splitlines():
        text = line.strip()
        if not text.startswith("["):
            continue
        if text.endswith("(기존)") or any(noise in text for noise in _NOISE):
            continue
        out.append(text)
    return out


def finding_key(line: str) -> str:
    """기준 트리와 변경 트리의 같은 문제를 알아보는 키: 줄 번호(`:12`)와 `(기존)` 표시를 뺀 문장."""
    return re.sub(r":\d+", ":", line.removesuffix("(기존)").strip())


def raw_findings(kit: list[str], path: Path, root: Path | None = None) -> list[str] | None:
    """`(기존)` 표시와 무관하게 audit-kit 이 보고한 모든 항목(환경 잡음 제외). 검사 못 하면 None.

    커밋된 두 트리(기준/변경)를 비교하는 검증용이다 — 깨끗한 체크아웃에서는 audit-kit 이 전부 `(기존)`으로 표시하므로
    그 표시를 믿지 않고 두 트리의 결과 차이로 "이번 변경이 만든 문제"를 가린다.
    """
    root = root or ROOT
    payload = json.dumps({"tool_input": {"file_path": str(path)}, "cwd": str(root)})
    try:
        proc = subprocess.run([*kit, "hook"], input=payload.encode("utf-8"), capture_output=True, timeout=PER_FILE_TIMEOUT_S, cwd=str(root), check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 0:
        return []
    if proc.returncode != 2:
        return None
    lines = proc.stderr.decode("utf-8", errors="replace").splitlines()
    return [ln.strip() for ln in lines if ln.strip().startswith("[") and not any(n in ln for n in _NOISE)]


def mypy_python(kit: list[str]) -> str | None:
    """audit-kit 가상환경의 파이썬(mypy 가 들어 있다). audit-kit 실행 파일이 아니면(시험용 가짜 등) None = mypy 생략."""
    first = Path(kit[0])
    if not first.name.lower().startswith("audit-kit"):
        return None
    for name in ("python.exe", "python"):
        candidate = first.parent / name
        if candidate.is_file():
            return str(candidate)
    return None


def mypy_keys(py: str, path: Path, root: Path | None = None) -> set[str] | None:
    """파일 하나의 mypy 오류 문장 집합(줄 번호·경로 제외). 실행 못 하면 None.

    `--ignore-missing-imports --follow-imports=silent`: audit-kit 가상환경에는 프로젝트 의존성이 없어 import 오류가 쏟아지므로
    끄고, 다른 모듈의 오류는 이 파일 검사에 섞이지 않게 한다.
    """
    root = root or ROOT
    cmd = [py, "-m", "mypy", "--ignore-missing-imports", "--follow-imports=silent", "--no-error-summary", "--no-color-output", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=PER_FILE_TIMEOUT_S, cwd=str(root), check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode not in (0, 1):  # 2 이상 = mypy 자체 오류
        return None
    found = set()
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        match = re.search(r": error: (.*)$", line)
        if match:
            found.add(match.group(1).strip())
    return found


def mypy_new(py: str, path: Path, baseline: Path | None, root: Path | None = None) -> tuple[list[str], str]:
    """`baseline` 파일(편집 전/기준 트리의 같은 파일)에 없던 mypy 오류만 → (신규 목록, 못 한 이유). baseline 이 None 이면 전부 신규."""
    current = mypy_keys(py, path, root)
    if current is None:
        return [], "mypy 를 실행하지 못했습니다"
    before: set[str] = set()
    if baseline is not None:
        before_keys = mypy_keys(py, baseline, root)
        if before_keys is None:
            return [], "기준 파일의 mypy 를 실행하지 못했습니다"
        before = before_keys
    return [f"[mypy] {path.name}: {msg}" for msg in sorted(current - before)], ""


def _mypy_against_head(py: str, path: Path, root: Path) -> tuple[list[str], str]:
    """편집한 파일을 HEAD 버전과 비교(편집 전에 없던 오류만). HEAD 에 없는 새 파일이면 전부 신규."""
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    shown = subprocess.run(["git", "show", f"HEAD:{rel}"], capture_output=True, cwd=str(root), check=False)
    if shown.returncode != 0:
        return mypy_new(py, path, None, root)
    copy = path.with_name(f"_mypy_base_{path.name}")  # 같은 폴더에 둬야 상대 import 가 같게 풀린다
    try:
        copy.write_bytes(shown.stdout)
        return mypy_new(py, path, copy, root)
    finally:
        copy.unlink(missing_ok=True)


def check_file(kit: list[str], path: Path, root: Path | None = None) -> tuple[list[str], str]:
    """한 파일 검사 → (신규 항목, 검사 못 한 이유). 이유가 있으면 항목은 비어 있다."""
    root = root or ROOT
    payload = json.dumps({"tool_input": {"file_path": str(path)}, "cwd": str(root)})
    try:
        proc = subprocess.run(
            [*kit, "hook"],
            input=payload.encode("utf-8"),
            capture_output=True,
            timeout=PER_FILE_TIMEOUT_S,
            cwd=str(root),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    stderr = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode not in (0, 2):
        return [], f"audit-kit 종료코드 {proc.returncode}: {stderr[-200:].strip()}"
    findings = [f"{path.name}: {item}" for item in new_findings(stderr)] if proc.returncode == 2 else []
    py = mypy_python(kit)
    if py is None:
        return findings, ""
    typed, why = _mypy_against_head(py, path, root)
    return findings + typed, ("" if findings or typed or not why else why)


def _eligible(path: Path, root: Path | None = None) -> bool:
    root = root or ROOT
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False  # 저장소 밖 파일(임시 스크립트 등)은 대상이 아니다
    return path.suffix == ".py" and path.is_file() and ".venv" not in path.parts and "node_modules" not in path.parts


def _utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")


def run_post_edit(stdin_text: str) -> int:
    try:
        data = json.loads(stdin_text) if stdin_text.strip() else {}
    except json.JSONDecodeError:
        return 0
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("path")
    if not file_path:
        return 0
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(data.get("cwd") or ROOT) / path
    if not _eligible(path):
        return 0
    kit = find_audit_kit()
    if kit is None:
        sys.stderr.write("[audit_kit_gate] audit-kit 를 찾지 못해 이번 검사를 생략합니다 (AUDIT_KIT_BIN 환경변수로 위치 지정 가능)\n")
        return 0
    findings, skipped = check_file(kit, path)
    if skipped:
        sys.stderr.write(f"[audit_kit_gate] 검사하지 못했습니다(막지 않음): {skipped}\n")
        return 0
    if not findings:
        return 0
    sys.stderr.write("[audit_kit_gate] 이번 편집으로 생긴 개발 기준서·구조 문제입니다. 고친 뒤 다시 저장하세요.\n")
    for item in findings[:MAX_SHOWN]:
        sys.stderr.write(f"  {item}\n")
    return 2


def _session_python_files(session_id: str | None) -> list[Path]:
    """이번 세션이 편집한 저장소 안 .py 파일(중복 제거, 순서 유지)."""
    from scripts.ops.post_edit_fast_gate import cleanup_old_session_edit_files, load_session_edits

    cleanup_old_session_edit_files()
    found = []
    for rel in load_session_edits(session_id):
        candidate = Path(rel) if Path(rel).is_absolute() else ROOT / rel
        if _eligible(candidate):
            found.append(candidate)
    return list(dict.fromkeys(found))


def _report_block(problems: list[str]) -> None:
    for item in problems[:MAX_SHOWN]:
        sys.stderr.write(f"  {item}\n")
    reason = f"audit-kit 세션 변경분 검사에서 신규 문제 {len(problems)}건 — stderr 로그를 참고해 고친 뒤 다시 종료하세요."
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))


def run_stop(stdin_text: str) -> int:
    import time

    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if payload.get("stop_hook_active"):
        return 0
    files = _session_python_files(payload.get("session_id"))
    kit = find_audit_kit() if files else None
    if files and kit is None:
        sys.stderr.write("[audit_kit_gate] audit-kit 를 찾지 못해 세션 종료 검사를 생략합니다\n")
    if not files or kit is None:
        return 0
    start = time.monotonic()
    problems: list[str] = []
    for path in files:
        if time.monotonic() - start > STOP_BUDGET_S:
            sys.stderr.write("[audit_kit_gate] 시간 초과 — 남은 파일 검사는 생략했습니다\n")
            break
        findings, skipped = check_file(kit, path)
        if skipped:
            sys.stderr.write(f"[audit_kit_gate] {path.name} 검사하지 못했습니다(막지 않음): {skipped}\n")
        problems.extend(findings)
    if problems:
        _report_block(problems)
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_streams()
    args = sys.argv[1:] if argv is None else argv
    mode = args[0] if args else "--post-edit"
    stdin_text = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        if mode == "--stop":
            return run_stop(stdin_text)
        if mode == "--post-edit":
            return run_post_edit(stdin_text)
    except Exception as exc:  # noqa: BLE001 - 훅 진입점: 게이트 자체의 오류로 작업을 막지 않는 fail-open(rules.toml ERR-06), 이유는 stderr 로 남긴다
        sys.stderr.write(f"[audit_kit_gate] 내부 오류(무시): {type(exc).__name__}: {exc}\n")
        return 0
    sys.stderr.write(f"[audit_kit_gate] 알 수 없는 모드: {mode}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
