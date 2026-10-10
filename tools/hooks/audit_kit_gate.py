"""audit-kit 게이트 — 코드를 쓸 때(PostToolUse)와 세션을 끝낼 때(Stop) audit-kit 의 파일 단위 개발 기준서 검사를 건다.

이 저장소에는 이미 편집 직후 ruff(신규 오류)·영향 테스트를 보는 `post_edit_fast_gate` 가 있다. 이 게이트는 그것이
보지 않는 것을 맡는다: audit-kit 의 **개발 기준서 파일 단위 검사(조항 ID, 신규/기존 구분)** 와 **순환 import**.
ruff 는 audit-kit 쪽에서 끄고(`pyproject.toml` `[tool.audit-kit] hook_tools = "design"`) 중복 실행하지 않는다. **mypy 는 이 게이트가
직접 돌린다**: audit-kit 가상환경의 mypy 로 파일 하나를 검사해 HEAD 버전에 없던 **신규 타입 오류만** 막는다(ruff 와 같은 원칙).
`--staged`(커밋 단계)는 같은 결과를 일괄로 낸다: hook 은 동시에, mypy 는 기준 폴더별 1회(`check_files`) — 파일 100개 이동 커밋이 15분 걸리던 문제.

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
import threading
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))
from scripts.common.no_window import no_window_kwargs  # noqa: E402
from tools.code_map.proc_tree import run_tree_killed  # noqa: E402

PER_FILE_TIMEOUT_S = 60
_MYPY_LOCK = (
    threading.Lock()
)  # verify_change 가 파일을 병렬로 검사해도 mypy 는 한 번에 하나만(같은 .mypy_cache 를 동시에 쓰면 자체 오류가 난다)
STOP_BUDGET_S = 90
MAX_SHOWN = 30
_NOISE = ("import-not-found", "import-untyped")  # audit-kit 가상환경에 프로젝트 의존성이 없어 생기는 잡음
_EXE_NAMES = ("audit-kit.exe", "audit-kit")
BATCH_SCRIPT = Path(__file__).resolve().parents[1] / "audit_kit_batch.py"  # tools/hooks/ 의 한 단계 위(tools/) — 이동 후 깊이 보정 누락 버그(2026-10-10, CI verify-static 90분 지연 조사 중 발견: parents[0]은 이 파일 자신의 폴더라 늘 실패해 배치스크립트를 못 찾고 파일별 단독 재시도로 느려짐)
_MYPY_ARGS = (
    "--ignore-missing-imports",
    "--follow-imports=silent",
    "--no-error-summary",
    "--no-color-output",
    "--explicit-package-bases",  # core/agent_runtime 처럼 __init__.py 없는 최상위 폴더가 생기면서
    # mypy 가 "Source file found twice under different module names" 자체오류로 전체 묶음·파일별
    # 재시도까지 전부 "실행 못함"으로 죽이던 문제(run38009465088, 161건) — 이 플래그로 파일마다
    # __init__.py 없는 첫 상위 폴더를 패키지 기준으로 명시해 모호성을 없앤다(실측: mypy==2.4.0 으로
    # core/agent_runtime/agent.py 단독 재현 — 이 플래그 전 exit=2 자체오류 → 후 exit=1 진짜 결과).
)
# __init__.py 가 전혀 없는 독립 실행 앱(런타임에 자기 폴더를 직접 sys.path 에 넣는 설계) — bare
# import(예: blog_router.py 의 "from core import ai_writer")가 cwd=ROOT 인 mypy 호출에선 저장소
# 최상위 core/(agent_runtime, 최근 신설) 로 잘못 풀린다("Module 'core' has no attribute
# 'ai_writer'", run38009465088 실측 재현). MYPYPATH 에 앱 폴더를 더해 각자 자기 core/ 를 먼저
# 보게 한다(실측: 추가 전 exit=1 오탐 → 추가 후 exit=0).
_STANDALONE_APP_DIRS = ("apps/marketing-standalone", "apps/ig-comment-dm-bot", "apps/youtube-analyzer-standalone")
# `경로:줄:칸: error: 문장` — 경로는 드라이브 콜론(C:)을 포함할 수 있어 가장 짧게 잡고, 줄·칸은 없을 수도 있다
_MYPY_ERROR_LINE = re.compile(r"^(?P<path>.+?)(?::\d+){0,2}: error: (?P<msg>.*)$")
_HOOK_WORKERS = max(1, min(8, os.cpu_count() or 1))  # audit-kit hook 은 파일을 읽기만 해서 동시에 돌려도 된다


def find_audit_kit(root: Path | None = None, env: Mapping[str, str] | None = None) -> list[str] | None:
    """audit-kit 실행 명령(리스트). 못 찾으면 None. `.py` 로 지정하면 현재 파이썬으로 실행한다(시험용)."""
    root = root or ROOT  # 호출 시점의 ROOT(시험에서 바꿀 수 있게 기본값을 import 때 고정하지 않는다)
    environ: Mapping[str, str] = os.environ if env is None else env
    explicit = (environ.get("AUDIT_KIT_BIN") or "").strip()
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
    """기준 트리와 변경 트리의 같은 문제를 알아보는 키: 경로:줄번호(`path.py:12`)와 `(기존)` 표시를 뺀 태그+메시지.

    `_hook_finding_key()` 와 같은 정규화(2026-10-08 에 그쪽만 고쳤던 것을 이쪽에도 적용, 2026-10-10):
    파일이 이동(rename)되면 메시지 속 경로 문자열이 기준/변경 트리에서 달라져, 줄 번호만 지우던 예전 방식으론
    같은 문제가 "새 문제"로 오탐됐다(이동 파일 ~2780건 커밋에서 실측). 경로:줄번호 토큰을 통째로 떼어내
    태그(`[...]`)+메시지만 키로 삼는다. 같은 키의 "개수"는 호출부(verify_change.py)가 Counter 로 비교하므로
    이 함수가 줄 번호를 지워도 "같은 메시지 2건"과 "1건"은 여전히 구별된다.
    """
    return re.sub(r"^(\[[^\]]+\])\s+\S+:\d+\s+", r"\1 ", line.removesuffix("(기존)").strip())


def new_findings(head: list[str], base: list[str]) -> list[str]:
    """`head` 중 `base` 에는 없던(개수가 넘치는) 항목만 — `finding_key()` 로 정규화한 뒤 Counter 로 비교한다.

    set 이 아니라 Counter 를 쓰는 이유: 파일 이동으로 `finding_key()` 가 경로:줄번호를 지우면, 같은 메시지가
    한 파일 안에 여러 줄(= 여러 건) 있을 때 set 비교는 "기준에 1건 있으니 변경본의 N건 전부 known"으로
    잘못 셀 수 있다. 기준 쪽 개수만큼만 소비하고, 그 이상은 전부 새 항목으로 센다(2026-10-10).
    """
    remaining = Counter(finding_key(x) for x in base)
    out = []
    for item in head:
        key = finding_key(item)
        if remaining[key] > 0:
            remaining[key] -= 1
        else:
            out.append(item)
    return out


def raw_findings(kit: list[str], path: Path, root: Path | None = None) -> list[str] | None:
    """`(기존)` 표시와 무관하게 audit-kit 이 보고한 모든 항목(환경 잡음 제외). 검사 못 하면 None.

    커밋된 두 트리(기준/변경)를 비교하는 검증용이다 — 깨끗한 체크아웃에서는 audit-kit 이 전부 `(기존)`으로 표시하므로
    그 표시를 믿지 않고 두 트리의 결과 차이로 "이번 변경이 만든 문제"를 가린다.
    """
    root = root or ROOT
    payload = json.dumps({"tool_input": {"file_path": str(path)}, "cwd": str(root)})
    try:
        proc = run_tree_killed(  # audit-kit 이 자손을 남겨 파이프를 물어도 시간 초과 때 트리째 종료하고 돌아온다(PR #160 verify 정지)
            [*kit, "hook"],
            input=payload.encode("utf-8"),
            text=False,
            timeout=PER_FILE_TIMEOUT_S,
            cwd=str(root),
            env=_utf8_env(),
            **no_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 0:
        return []
    if proc.returncode != 2:
        return None
    lines = proc.stderr.decode("utf-8", errors="replace").splitlines()
    return [ln.strip() for ln in lines if ln.strip().startswith("[") and not any(n in ln for n in _NOISE)]


def _hook_lines(messages: list[str]) -> list[str]:
    """hook 메시지 → `raw_findings` 와 같은 규칙으로 거른 항목('['로 시작, 환경 잡음 제외)."""
    return [m.strip() for m in messages if m.strip().startswith("[") and not any(n in m for n in _NOISE)]


def batch_raw_findings(
    kit: list[str], root: Path, rels: list[str], *, workers: int = 4, timeout_s: int = 1500
) -> dict[str, list[str]]:
    """여러 파일의 audit-kit 검사를 프로세스 몇 개에서 묶어 돈다(`tools/audit_kit_batch.py`) — 프로젝트 그래프를 프로세스마다 한 번만 만든다.

    파일마다 `raw_findings`(= `audit-kit hook` 호출)를 따로 부르면 호출마다 그래프를 새로 만들어 파일당 수 초가 걸린다(PR #160 verify 정지의 원인).
    돌려주는 dict 에 없는 파일(진짜 audit-kit 가 아니거나 묶음 실행이 실패한 경우)은 호출 쪽이 `raw_findings` 로 단독 재시도한다.
    """
    py = mypy_python(kit)  # audit-kit 가상환경의 python (진짜 audit-kit 일 때만 — 시험용 가짜 kit 이면 None)
    if py is None or not rels:
        return {}
    # scripts/ops/hooks/ 의 한 단계 위(scripts/ops/)에 있다 — 2026-10-09(PR #165 7차 CI) 전까지
    # with_name() 으로 같은 폴더를 찾아 항상 못 찾았다. 못 찾으면 묶음을 전혀 시도하지 않고 빈 dict
    # 를 바로 돌려줘서(호출 쪽이 파일마다 raw_findings 로 단독 재시도) — 묶음이 조용히 매번 실패해
    # 2240개 단독 재시도 폭주로 90분 제한을 넘기던 것과 같은 사고가 다시 나도 최소한 느려지기만
    # 하고 멈추지는 않는다(경고는 호출 쪽 _audit_kit_new_findings 가 kit_errors 에 남긴다).
    if not BATCH_SCRIPT.is_file():
        return {}
    script = BATCH_SCRIPT
    chunks = [rels[i::workers] for i in range(min(workers, len(rels)))]

    def run_chunk(chunk: list[str]) -> dict[str, list[str]]:
        try:
            proc = run_tree_killed(
                [py, str(script), str(root)],
                input=json.dumps(chunk).encode("utf-8"),
                text=False,
                timeout=timeout_s,
                cwd=str(root),
                env=_utf8_env(),
                **no_window_kwargs(),
            )
            data = json.loads(proc.stdout.decode("utf-8")) if proc.returncode == 0 else {}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {}
        return {rel: _hook_lines(msgs) for rel, msgs in data.items() if isinstance(msgs, list)}

    found: dict[str, list[str]] = {}
    with ThreadPoolExecutor(len(chunks)) as pool:
        for part in pool.map(run_chunk, chunks):
            found.update(part)
    return found


def _utf8_env() -> dict[str, str]:
    """하위 프로세스(audit-kit·mypy)가 콘솔 코드페이지(cp949)가 아니라 utf-8 로 출력하게 한다 — 결과를 utf-8 로 읽기 때문.

    MYPYPATH 에 독립 실행 앱(__init__.py 없음, `_STANDALONE_APP_DIRS`)을 더한다 — mypy 가
    --explicit-package-bases 로도 그 안의 bare import("core" 등)를 저장소 최상위로 잘못
    풀지 않고 앱 자신의 폴더부터 보게 한다(run38009465088 조사, 실측 재현·검증).
    """
    mypypath = os.pathsep.join(str(ROOT / d) for d in _STANDALONE_APP_DIRS)
    extra = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "MYPYPATH": mypypath}
    if os.environ.get("MYPYPATH"):
        extra["MYPYPATH"] = os.environ["MYPYPATH"] + os.pathsep + mypypath
    return {**os.environ, **extra}


def is_real_kit(kit: list[str]) -> bool:
    """진짜 audit-kit 실행 파일인가(시험용 가짜·직접 지정한 .py 는 아니다) — 진짜인데 mypy 를 못 돌리면 환경 결함이다."""
    return Path(kit[0]).name.lower().startswith("audit-kit")


def mypy_python(kit: list[str]) -> str | None:
    """audit-kit 가상환경의 파이썬(mypy 가 들어 있다). audit-kit 실행 파일이 아니면(시험용 가짜 등) None = mypy 생략."""
    first = Path(kit[0])
    if not is_real_kit(kit):
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
    cmd = [py, "-m", "mypy", *_MYPY_ARGS, str(path)]
    proc = None
    with _MYPY_LOCK:
        for _attempt in range(2):  # 자체 오류(종료코드 2 이상)는 일시적일 수 있어 한 번 다시 시도한다
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=PER_FILE_TIMEOUT_S,
                    cwd=str(root),
                    env=_utf8_env(),
                    check=False,
                    **no_window_kwargs(),
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            if proc.returncode in (0, 1):
                break
    if proc is None or proc.returncode not in (0, 1):  # 2 이상 = mypy 자체 오류
        return None
    # mypy 가 설치돼 있지 않으면 `python -m mypy` 가 종료코드 1 + 빈 출력으로 끝나 '오류 없음'처럼 보인다 — 통과로 오인하지 않는다
    if proc.returncode == 1 and b"No module named mypy" in (getattr(proc, "stderr", None) or b""):
        return None
    found = set()
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        match = re.search(r": error: (.*)$", line)
        if match:
            found.add(match.group(1).strip())
    return found


def _mypy_base_dir(path: Path) -> str:
    """mypy 가 이 파일을 실행할 때 검색 경로에 넣는 기준 폴더(`__init__.py` 가 없는 첫 상위 폴더).

    mypy 는 명령줄로 받은 파일마다 이 폴더를 import 검색 경로에 더한다 — 같은 기준 폴더의 파일끼리만 한 번에 돌려야
    파일별로 따로 돌릴 때와 import 해석(=오류)이 같다. 같은 기준 폴더 안에서는 모듈 이름도 겹치지 않는다.
    """
    folder = path.absolute().parent
    while ((folder / "__init__.py").is_file() or (folder / "__init__.pyi").is_file()) and folder.parent != folder:
        folder = folder.parent
    return os.path.normcase(str(folder))


def _norm(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _split_mypy_output(text: str, group: list[Path], root: Path) -> dict[Path, set[str]] | None:
    """여러 파일을 한 번에 돌린 mypy 출력을 파일별 오류 문장 집합으로 나눈다. 어느 파일 것인지 모를 오류 줄이 있으면 None."""
    index = {_norm(p): p for p in group}
    found: dict[Path, set[str]] = {p: set() for p in group}
    for line in text.splitlines():
        if not re.search(r": error: (.*)$", line):
            continue
        match = _MYPY_ERROR_LINE.match(line)
        target = index.get(_norm(root / match.group("path"))) if match else None
        if match is None or target is None:
            return None
        found[target].add(match.group("msg").strip())
    return found


def _mypy_group(py: str, group: list[Path], root: Path) -> dict[Path, set[str] | None]:
    """같은 기준 폴더의 파일들을 mypy 한 번으로 검사. 결과는 파일마다 `mypy_keys` 를 부른 것과 같다.

    mypy 자체 오류(종료코드 2 이상, 예: 한 파일의 문법 오류는 검사 전체를 멈춘다)·출력 해석 실패면 파일별 실행으로 되돌아가
    같은 결과를 낸다. 시간 초과·mypy 미설치는 파일별로 돌려도 같으므로 전부 '실행 못 함'(None).
    """
    if len(group) == 1:
        return {group[0]: mypy_keys(py, group[0], root)}
    cmd = [py, "-m", "mypy", *_MYPY_ARGS, *(str(p) for p in group)]
    proc = None
    with _MYPY_LOCK:
        for _attempt in range(2):  # mypy_keys 와 같이 자체 오류는 한 번 다시 시도
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=PER_FILE_TIMEOUT_S * len(group),
                    cwd=str(root),
                    env=_utf8_env(),
                    check=False,
                    **no_window_kwargs(),
                )
            except (OSError, subprocess.TimeoutExpired):
                return dict.fromkeys(group)
            if proc.returncode in (0, 1):
                break
    if proc is not None and proc.returncode == 1 and b"No module named mypy" in (getattr(proc, "stderr", None) or b""):
        return dict.fromkeys(group)
    split = None
    if proc is not None and proc.returncode in (0, 1):
        split = _split_mypy_output(proc.stdout.decode("utf-8", errors="replace"), group, root)
    if split is None:  # 잠금 밖에서 파일별로(mypy_keys 가 스스로 잠근다)
        return {p: mypy_keys(py, p, root) for p in group}
    return dict(split)


_CMD_CHAR_BUDGET = 20000  # 한 mypy 명령줄에 넣는 경로 글자 수 상한 — 윈도우 명령줄 한도(32767자) 아래로 여유를 둔다


def _split_by_command_length(group: list[Path]) -> list[list[Path]]:
    """파일이 많으면(PR #160: 변경 1049개 ≈ 10만 자) 한 명령에 다 넣을 수 없다 — WinError 206(OSError)이 나면 전부 '실행 못 함'이 되어 버린다."""
    parts: list[list[Path]] = []
    current: list[Path] = []
    size = 0
    for path in group:
        length = len(str(path)) + 1
        if current and size + length > _CMD_CHAR_BUDGET:
            parts.append(current)
            current, size = [], 0
        current.append(path)
        size += length
    if current:
        parts.append(current)
    return parts


def mypy_keys_batch(py: str, paths: list[Path], root: Path | None = None) -> dict[Path, set[str] | None]:
    """여러 파일의 mypy 오류 문장 집합을 기준 폴더별 mypy 1회로 구한다 — 파일마다 `mypy_keys` 를 부른 것과 같은 결과."""
    root = root or ROOT
    groups: dict[str, list[Path]] = {}
    for path in dict.fromkeys(paths):
        groups.setdefault(_mypy_base_dir(path), []).append(path)
    result: dict[Path, set[str] | None] = {}
    for group in groups.values():
        for part in _split_by_command_length(group):
            result.update(_mypy_group(py, part, root))
    return result


def _new_typed(
    path: Path, current: set[str] | None, has_baseline: bool, before_keys: set[str] | None
) -> tuple[list[str], str]:
    """mypy 결과(현재·기준) → (신규 목록, 못 한 이유). `mypy_new` 와 일괄 검사가 같은 규칙을 쓴다."""
    if current is None:
        return [], "mypy 를 실행하지 못했습니다"
    before: set[str] = set()
    if has_baseline:
        if before_keys is None:
            return [], "기준 파일의 mypy 를 실행하지 못했습니다"
        before = before_keys
    return [f"[mypy] {path.name}: {msg}" for msg in sorted(current - before)], ""


def mypy_new(py: str, path: Path, baseline: Path | None, root: Path | None = None) -> tuple[list[str], str]:
    """`baseline` 파일(편집 전/기준 트리의 같은 파일)에 없던 mypy 오류만 → (신규 목록, 못 한 이유). baseline 이 None 이면 전부 신규."""
    current = mypy_keys(py, path, root)
    if current is None:
        return _new_typed(path, None, False, None)
    before_keys = mypy_keys(py, baseline, root) if baseline is not None else None
    return _new_typed(path, current, baseline is not None, before_keys)


def _mypy_against_head(py: str, path: Path, root: Path, old_rel: str | None = None) -> tuple[list[str], str]:
    """편집한 파일을 HEAD 버전과 비교(편집 전에 없던 오류만). HEAD 에 없는 새 파일이면 전부 신규.

    `old_rel`: git 이 이름 변경(R)으로 본 파일의 옛 경로(저장소 기준 posix). 있으면 HEAD:<옛 경로> 를 비교 기준으로 쓴다 — 옛 위치에
    있던 기존 오류가 이동 때문에 '새 파일의 신규 오류'로 잡히지 않게 한다(2026-10-07, git mv 이동 커밋에서 오탐 3건).
    """
    rel = old_rel or path.resolve().relative_to(root.resolve()).as_posix()
    shown = subprocess.run(
        ["git", "show", f"HEAD:{rel}"], capture_output=True, cwd=str(root), check=False, **no_window_kwargs()
    )
    if shown.returncode != 0:
        return mypy_new(py, path, None, root)
    copy = path.with_name(f"_mypy_base_{path.name}")  # 같은 폴더에 둬야 상대 import 가 같게 풀린다
    try:
        copy.write_bytes(shown.stdout)
        return mypy_new(py, path, copy, root)
    finally:
        copy.unlink(missing_ok=True)


def _head_blobs(root: Path, rels: list[str]) -> dict[str, bytes | None]:
    """여러 `HEAD:<경로>` 내용을 `git cat-file --batch` 한 번으로 읽는다(없으면 None). 실패하면 파일별 `git show` 로 되돌아간다."""
    unique = list(dict.fromkeys(rels))
    if not unique:
        return {}
    request = "".join(f"HEAD:{rel}\n" for rel in unique).encode("utf-8")
    proc = subprocess.run(
        ["git", "cat-file", "--batch"], input=request, capture_output=True, cwd=str(root), check=False
    )
    blobs: dict[str, bytes | None] = {}
    data, pos = proc.stdout, 0
    for rel in unique:
        if proc.returncode != 0:
            break
        end = data.find(b"\n", pos)
        if end < 0:
            break
        header = data[pos:end].split()
        pos = end + 1
        if len(header) == 3 and header[2].isdigit():  # `<oid> <종류> <크기>` 다음에 내용과 줄바꿈 하나
            size = int(header[2])
            blobs[rel] = data[pos : pos + size] if header[1] == b"blob" else None
            pos += size + 1
        else:  # `<이름> missing` 등 — HEAD 에 없다
            blobs[rel] = None
    if len(blobs) != len(unique):  # 출력을 다 못 읽었으면 예전 방식으로
        for rel in unique:
            shown = subprocess.run(
                ["git", "show", f"HEAD:{rel}"], capture_output=True, cwd=str(root), check=False, **no_window_kwargs()
            )
            blobs[rel] = shown.stdout if shown.returncode == 0 else None
    return blobs


def mypy_against_head_many(
    py: str, items: list[tuple[Path, str | None]], root: Path | None = None
) -> dict[Path, tuple[list[str], str]]:
    """여러 파일을 각자의 HEAD 버전과 비교 — 파일마다 `_mypy_against_head` 를 부른 것과 같은 결과를 mypy 몇 번(기준 폴더 수)으로 낸다.

    HEAD 버전 사본은 예전처럼 원본 옆(`_mypy_base_<이름>`)에 두어 상대 import 가 같게 풀리고, 이름 변경(old_rel)은 HEAD:<옛 경로> 와 비교한다.
    """
    root = root or ROOT
    rels = [old_rel or path.resolve().relative_to(root.resolve()).as_posix() for path, old_rel in items]
    blobs = _head_blobs(root, rels)
    copies: dict[Path, Path] = {}
    try:
        for (path, _old), rel in zip(items, rels, strict=True):
            content = blobs.get(rel)
            if content is not None:
                copy = path.with_name(f"_mypy_base_{path.name}")  # 같은 폴더에 둬야 상대 import 가 같게 풀린다
                copy.write_bytes(content)
                copies[path] = copy
        keys = mypy_keys_batch(py, [path for path, _old in items] + list(copies.values()), root)
    finally:
        for copy in copies.values():
            copy.unlink(missing_ok=True)
    return {
        path: _new_typed(path, keys.get(path), path in copies, keys.get(copies[path]) if path in copies else None)
        for path, _old in items
    }


def _kit_hook_raw(kit: list[str], path: Path, root: Path) -> tuple[list[str] | None, str]:
    """`audit-kit hook` 으로 한 파일을 검사해 `(기존)` 표시와 무관한 전체 항목을 돌려준다(이름 변경 비교용). (None, 이유) = 검사 못 함."""
    payload = json.dumps({"tool_input": {"file_path": str(path)}, "cwd": str(root)})
    try:
        proc = run_tree_killed(  # audit-kit 이 자손을 남겨 파이프를 물어도 시간 초과 때 트리째 종료하고 돌아온다(PR #160 verify 정지)
            [*kit, "hook"],
            input=payload.encode("utf-8"),
            text=False,
            timeout=PER_FILE_TIMEOUT_S,
            cwd=str(root),
            env=_utf8_env(),
            **no_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    stderr = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode not in (0, 2):
        return None, f"audit-kit 종료코드 {proc.returncode}: {stderr[-200:].strip()}"
    if proc.returncode == 0:
        return [], ""
    lines = [
        ln.strip() for ln in stderr.splitlines() if ln.strip().startswith("[") and not any(n in ln for n in _NOISE)
    ]
    return lines, ""


def _hook_finding_key(item: str) -> str:
    """hook 지적 한 줄에서 `[표준 XXX]` 태그만 남기고 경로:줄번호·메시지는 비교용으로 남긴다.

    HEAD 사본은 `_hook_base_<이름>` 으로 옆에 써서 돌리므로(상대 import 보존), audit-kit 출력에 그 파일명이
    그대로 박혀(`tests/g2b/_hook_base_X.py:25 ...`) 원본(`tests/g2b/X.py:25 ...`)과 글자가 달라 그냥 비교하면
    항상 "다른 지적"으로 보인다 — 경로:줄번호 토큰을 통째로 떼어내고 태그+메시지만 비교한다.
    """
    return re.sub(r"^(\[[^\]]+\])\s+\S+:\d+\s+", r"\1 ", item.strip())


def _kit_hook_against_head(kit: list[str], path: Path, root: Path, old_rel: str | None) -> tuple[list[str], str]:
    """`audit-kit hook` 으로 한 파일 검사 → (신규 항목, 검사 못 한 이유).

    hook 체크(STD 류)는 audit-kit 내부적으로 git 이력을 안 봐서 `(기존)` 표시를 못 낸다 — 이름만 바뀐 파일(git mv)의
    기존 문제가 '신규'로 오탐되는 걸 막기 위해, old_rel(이름 변경 전 경로)이 있으면 HEAD:<old_rel> 버전도 같이 검사해
    두 결과에 공통으로 있는 항목(줄 번호 무시)을 빼고 돌려준다(2026-10-08, tests 이동 커밋에서 오탐 발견).
    """
    current, failed = _kit_hook_raw(kit, path, root)
    if failed or current is None:
        return [], failed
    if not current:
        return [], ""
    if not old_rel:
        return [f"{path.name}: {item}" for item in current if not item.endswith("(기존)")], ""
    shown = subprocess.run(
        ["git", "show", f"HEAD:{old_rel}"], capture_output=True, cwd=str(root), check=False, **no_window_kwargs()
    )
    if shown.returncode != 0:
        return [f"{path.name}: {item}" for item in current if not item.endswith("(기존)")], ""
    copy = path.with_name(f"_hook_base_{path.name}")
    try:
        copy.write_bytes(shown.stdout)
        before, before_failed = _kit_hook_raw(kit, copy, root)
    finally:
        copy.unlink(missing_ok=True)
    if before_failed or before is None:
        return [f"{path.name}: {item}" for item in current if not item.endswith("(기존)")], ""
    before_keys = {_hook_finding_key(item) for item in before}
    return [f"{path.name}: {item}" for item in current if _hook_finding_key(item) not in before_keys], ""


def _merge(findings: list[str], typed: list[str], why: str) -> tuple[list[str], str]:
    return findings + typed, ("" if findings or typed or not why else why)


def check_file(
    kit: list[str], path: Path, root: Path | None = None, old_rel: str | None = None
) -> tuple[list[str], str]:
    """한 파일 검사 → (신규 항목, 검사 못 한 이유). 이유가 있으면 항목은 비어 있다.

    old_rel: 이름 변경 전 경로 — mypy 비교 기준(`_mypy_against_head`)과, audit-kit hook 자체의
    "(기존)" 판정이 놓친 옛 위치의 기존 결함(`_kit_hook_against_head` 내부에서 old_rel 로 처리)
    둘 다에 쓴다.

    2026-10-09(PR #165 6차 CI, F821): 이름 변경 옛 경로 비교는 `_kit_hook_against_head` 가 이미
    old_rel 을 받아 내부에서 처리한다 — 같은 일을 다시 하던 `_kit_hook_old_path_keys` 호출(삭제된
    `_kit_hook` 참조로 NameError 였다)은 중복이라 걷어냈다. 새 함수를 만들지 않고 이미 있는
    완결된 구현에 연결한 것뿐이다.
    """
    root = root or ROOT
    findings, failed = _kit_hook_against_head(kit, path, root, old_rel)
    if failed:
        return [], failed
    py = mypy_python(kit)
    if py is None:
        return findings, ""
    return _merge(findings, *_mypy_against_head(py, path, root, old_rel))


def check_files(
    kit: list[str], items: list[tuple[Path, str | None]], root: Path | None = None
) -> list[tuple[Path, list[str], str]]:
    """여러 파일 검사 — 결과·순서는 파일마다 `check_file` 을 부른 것과 같다(커밋 단계용 일괄 실행).

    `audit-kit hook` 은 파일마다 따로지만 동시에(최대 8개) 돌리고, mypy 는 hook 이 끝난 뒤 기준 폴더별로 한 번만 돌린다
    (예전: 파일당 현재·HEAD 2회). hook 이 실패한 파일은 예전처럼 mypy 를 보지 않는다. 이름 변경 파일의 옛 경로
    기존 결함 비교는 `_kit_hook_against_head` 가 old_rel 을 받아 hook 호출과 같이 처리한다.

    2026-10-09(PR #165 6차 CI, F821): 삭제된 `_kit_hook` 을 부르던 줄이 NameError 였다 — 같은 일을
    하는 완결된 구현 `_kit_hook_against_head`(old_rel 처리 내장)에 연결, 중복이던
    `_rename_old_path_keys_many`/`_drop_old_path_findings` 2차 필터링은 걷어냈다.
    """
    root = root or ROOT
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(_HOOK_WORKERS, len(items))) as pool:
        hooked = list(pool.map(lambda item: _kit_hook_against_head(kit, item[0], root, item[1]), items))
    py = mypy_python(kit)
    ok = [item for item, (_f, failed) in zip(items, hooked, strict=True) if not failed]
    typed = mypy_against_head_many(py, ok, root) if py is not None and ok else {}
    out: list[tuple[Path, list[str], str]] = []
    for (path, _old), (findings, failed) in zip(items, hooked, strict=True):
        if failed:
            out.append((path, [], failed))
        elif py is None:
            out.append((path, findings, ""))
        else:
            out.append((path, *_merge(findings, *typed[path])))
    return out


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


def _required(env: Mapping[str, str] | None = None) -> bool:
    """AUDIT_KIT_REQUIRED=1/true/yes 면 audit-kit 를 못 찾을 때 통과시키지 않고 막는다(fail-closed)."""
    value = (env if env is not None else os.environ).get("AUDIT_KIT_REQUIRED", "")
    return value.strip().lower() in {"1", "true", "yes"}


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
        if _required():
            sys.stderr.write(
                "[audit_kit_gate] audit-kit 를 찾지 못했고 AUDIT_KIT_REQUIRED 가 켜져 있어 막습니다 (AUDIT_KIT_BIN 으로 위치 지정)\n"
            )
            return 2
        sys.stderr.write(
            "[audit_kit_gate] audit-kit 를 찾지 못해 이번 검사를 생략합니다 (AUDIT_KIT_BIN 환경변수로 위치 지정 가능)\n"
        )
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
    from tools.hooks.post_edit_fast_gate import cleanup_old_session_edit_files, load_session_edits

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
    reason = (
        f"audit-kit 세션 변경분 검사에서 신규 문제 {len(problems)}건 — stderr 로그를 참고해 고친 뒤 다시 종료하세요."
    )
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
        if _required():
            reason = "audit-kit 를 찾지 못했고 AUDIT_KIT_REQUIRED 가 켜져 있어 세션 종료를 막습니다 (AUDIT_KIT_BIN 으로 위치 지정)"
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
            return 0
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


def _staged_python_changes() -> list[tuple[Path, str | None]]:
    """커밋에 올라갈(staged, 삭제 제외) 저장소 안 .py 파일과, 이름 변경(R)이면 옛 경로.

    `git diff --cached -M --name-status` 로 읽어 R(이름 변경) 파일의 옛 경로를 함께 돌려준다 → 비교 기준을 HEAD:<옛 경로> 로 쓴다.
    새 파일(A)·복사(C)·수정(M)은 옛 경로가 None(HEAD:<같은 경로>, 없으면 전부 신규). 복사는 원본이 남아 있어 새 파일로 본다(보수적).
    """
    out = subprocess.run(
        ["git", "diff", "--cached", "-M", "--name-status", "--diff-filter=ACMR", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **no_window_kwargs(),
    ).stdout
    parts = [x for x in out.split("\0") if x]
    changes: list[tuple[Path, str | None]] = []
    i = 0
    while i < len(parts):
        status = parts[i]
        if status[:1] in ("R", "C") and i + 2 < len(parts):
            changes.append((ROOT / parts[i + 2], parts[i + 1] if status[0] == "R" else None))
            i += 3
        else:
            if i + 1 < len(parts):
                changes.append((ROOT / parts[i + 1], None))
            i += 2
    return [(c, old) for c, old in changes if _eligible(c)]


def _staged_python_files() -> list[Path]:
    """커밋에 올라갈(staged, 삭제 제외) 저장소 안 .py 파일."""
    return [c for c, _old in _staged_python_changes()]


def run_staged() -> int:
    """pre-commit 용: staged .py 의 신규 문제가 있으면 1(커밋 차단). 기존 문제는 막지 않는다."""
    files = _staged_python_changes()
    if not files:
        return 0
    kit = find_audit_kit()
    if kit is None:
        if _required():
            sys.stderr.write(
                "[audit_kit_gate] audit-kit 를 찾지 못했고 AUDIT_KIT_REQUIRED 가 켜져 있어 커밋을 막습니다 (AUDIT_KIT_BIN 으로 위치 지정)\n"
            )
            return 1
        sys.stderr.write(
            "[audit_kit_gate] audit-kit 를 찾지 못해 커밋 검사를 생략합니다 (AUDIT_KIT_BIN 환경변수로 위치 지정 가능)\n"
        )
        return 0
    problems: list[str] = []
    for path, findings, skipped in check_files(kit, files):
        if skipped:
            sys.stderr.write(f"[audit_kit_gate] {path.name} 검사하지 못했습니다(막지 않음): {skipped}\n")
        problems.extend(findings)
    if not problems:
        return 0
    sys.stderr.write("[audit_kit_gate] 이번 커밋으로 생긴 개발 기준서·구조 문제입니다. 고친 뒤 다시 커밋하세요.\n")
    for item in problems[:MAX_SHOWN]:
        sys.stderr.write(f"  {item}\n")
    return 1


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
        if mode == "--staged":
            return run_staged()
    except Exception as exc:  # noqa: BLE001 - 훅 진입점: 게이트 자체의 오류로 작업을 막지 않는 fail-open(rules.toml ERR-06), 이유는 stderr 로 남긴다
        sys.stderr.write(f"[audit_kit_gate] 내부 오류(무시): {type(exc).__name__}: {exc}\n")
        return 0
    sys.stderr.write(f"[audit_kit_gate] 알 수 없는 모드: {mode}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
