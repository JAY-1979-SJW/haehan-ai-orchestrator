"""PostToolUse(Edit|Write) — 편집 직후 빠른 게이트: ruff(신규 오류만) + 매핑 테스트(최대 3개)
+ (TS면) admin-web typecheck(5분 캐시). 상한 20초. 새 판정 로직 없음 — 기존 도구 재호출만.

기준서: docs/specs/2026-09-26_ai_code_quality_gate.md §3.2

동작:
- .py: `git show HEAD:<file>` 기준선과 현재 파일을 각각 ruff check 해서 신규 오류(차집합)만
  차단(exit 2 + stderr). 기존 오류(결함 #30, 레거시 lint 오류 다수)는 무시한다.
  이어서 `python -m tools.code_map.query tests-for <file>` 로 매핑 테스트를 찾아
  최대 3개까지 pytest 실행(live/e2e 이름은 제외 — 부작용 있는 외부 호출 방지).
  실패하면 HEAD 스냅샷(시스템 임시 폴더)에서 같은 테스트를 돌려, 같은 문구로 이미 실패하던 것은
  통과시키고 새로 실패한 것만 차단한다(2026-09-30 기준선 비교).
- .ts/.tsx: admin-web 내부 파일이면 tsc --noEmit 1회(5분 캐시).
- 전체 상한 20초. 초과/실패는 경고만(차단 아님) — 최종 확인은 Stop 훅(stop_fast_verify.py) 담당.
- 내부 예외는 fail-open(exit 0) — 이 훅이 죽어서 모든 편집이 막히면 안 된다. 실제 "신규 lint
  오류 발견"만 exit 2로 차단한다.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
RUFF_CFG = ROOT / "configs" / "ruff.toml"
QUERY_MOD = "tools.code_map.query"
TSC_CACHE_FILE = ROOT / "data" / ".post_edit_gate_tsc_cache.json"
TSC_CACHE_SECONDS = 5 * 60
OVERALL_BUDGET_SECONDS = 20.0
MAX_TESTS = 3


PROJECT_PYTHON_VERSION = (3, 14)


def _project_python() -> list[str]:
    """게이트가 띄우는 하위 프로세스(ruff·query·pytest)용 인터프리터.

    이 훅이 PATH 의 `python`(3.11 등)으로 호출돼도 프로젝트 버전(3.14)으로 돌린다 — 3.11 에는
    websocket-client·psutil 등 requirements 패키지가 없어 정상 코드도 수집 오류로 차단됐다
    (2026-09-30). 이미 3.14 이거나 py 런처가 없으면 현재 인터프리터를 그대로 쓴다.
    """
    if sys.version_info[:2] == PROJECT_PYTHON_VERSION or not shutil.which("py"):
        return [sys.executable]
    probe = subprocess.run(["py", "-3.14", "-c", "pass"], capture_output=True, timeout=10, check=False)
    return ["py", "-3.14"] if probe.returncode == 0 else [sys.executable]


# 기준선 비교 — 영향 테스트가 실패해도 HEAD 에서 같은 문구로 이미 실패하던 것은 차단하지 않는다.
HEAD_CACHE_DIR = (
    Path(tempfile.gettempdir()) / f"haehan_gate_head_{hashlib.sha256(str(ROOT).encode()).hexdigest()[:8]}"
)  # 저장소 밖 — 시크릿·레이어 감사가 스냅샷을 훑지 않게
HEAD_CACHE_KEEP = 2
HEAD_SNAPSHOT_BUDGET_SECONDS = 60.0  # HEAD 가 바뀐 뒤 첫 실패에서만 한 번 쓰는 시간
_SNAPSHOT_SKIP_DIRS = {"admin-web", "docs", "dist-electron", "data", "node_modules", ".github", ".git"}
_TOP_LEVEL_ASCII = re.compile(r"^[A-Za-z0-9_.-]+$")
_FAIL_LINE = re.compile(r"^(?:FAILED|ERROR) (\S+)(?: - (.*))?$")

# 세션별 편집 파일 기록 — stop_fast_verify.py 가 "이 세션에서 바뀐 파일만" 검사할 수
# 있도록 한다. git status 전체를 쓰면 다른 세션의 미커밋 변경분까지 차단 사유에
# 끼어들기 때문(2026-09-26 코드리뷰 실측 지적으로 도입).
SESSION_EDITS_DIR = ROOT / "data" / ".session_edits"
SESSION_EDITS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def _session_edits_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)
    return SESSION_EDITS_DIR / f"{safe}.json"


def record_session_edit(session_id: str | None, rel_path: str) -> None:
    """이번 세션이 건드린 파일 경로를 세션별 목록에 추가(중복 제거)."""
    if not session_id:
        return
    try:
        SESSION_EDITS_DIR.mkdir(parents=True, exist_ok=True)
        path = _session_edits_path(session_id)
        existing: list[str] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
                existing = []
        if rel_path not in existing:
            existing.append(rel_path)
        path.write_text(json.dumps(existing), encoding="utf-8")
    except Exception as exc:  # 기록 실패는 훅 동작 자체를 막지 않는다(fail-open)  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        sys.stderr.write(f"[post_edit_fast_gate] session edit record failed (ignored): {exc}\n")


def load_session_edits(session_id: str | None) -> list[str]:
    if not session_id:
        return []
    path = _session_edits_path(session_id)
    if not path.exists():
        return []
    try:
        edits = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        return []
    # 서브에이전트 격리 워크트리(.claude/worktrees/) 파일은 제외한다 — 기준선(HEAD 의 같은 경로)이
    # 없어 기존 ruff 오류가 전부 "새 오류"로 집계되는 오탐이 나고, 그 파일은 해당 워크트리 브랜치의
    # 커밋 훅이 따로 검증한다(defect_index #112, 2026-10-01).
    return [e for e in edits if not str(e).replace("\\", "/").startswith(".claude/worktrees/")]


def cleanup_old_session_edit_files(max_age_seconds: float = SESSION_EDITS_MAX_AGE_SECONDS) -> None:
    """7일 지난 세션 기록 파일 정리(디스크 누적 방지)."""
    if not SESSION_EDITS_DIR.exists():
        return
    now = time.time()
    try:
        for f in SESSION_EDITS_DIR.glob("*.json"):
            try:
                if now - f.stat().st_mtime > max_age_seconds:
                    f.unlink()
            except OSError:
                continue
    except Exception as exc:  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        sys.stderr.write(f"[post_edit_fast_gate] session edit cleanup failed (ignored): {exc}\n")


_SKIP_TEST_PATTERNS = re.compile(r"live|e2e", re.IGNORECASE)


def _remaining(start: float) -> float:
    return max(0.0, OVERALL_BUDGET_SECONDS - (time.monotonic() - start))


def _run(
    cmd: list[str], timeout: float, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=max(1.0, timeout),
        encoding="utf-8",
        errors="ignore",
    )


def _ruff_errors(file_text: str, suffix: str) -> set[tuple[str, str]]:
    """주어진 소스 텍스트를 임시 파일에 써서 ruff check 결과의 (rule_code, message) 집합을 반환.
    파일 경로/줄번호는 무시(같은 파일이라도 편집 전후 줄이 밀리므로 내용 기준 비교)."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8", dir=str(ROOT)) as tf:
        tf.write(file_text)
        tmp_path = Path(tf.name)
    try:
        proc = _run(
            [
                *_project_python(),
                "-m",
                "ruff",
                "check",
                "--config",
                str(RUFF_CFG),
                "--output-format",
                "json",
                str(tmp_path),
            ],
            timeout=10,
        )
        out = proc.stdout.strip()
        if not out:
            return set()
        try:
            items = json.loads(out)
        except json.JSONDecodeError:
            return set()
        result = set()
        for it in items:
            code = it.get("code") or ""
            msg = it.get("message") or ""
            result.add((code, msg))
        return result
    finally:
        try:
            tmp_path.unlink()
        except OSError as exc:
            sys.stderr.write(f"[post_edit_fast_gate] temp file cleanup failed (ignored): {exc}\n")


def _git_show_head(rel_path: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "show", f"HEAD:{rel_path}"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="ignore",
        )
        if proc.returncode != 0:
            return None
        return proc.stdout
    except Exception:  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        return None


def parse_failures(output: str) -> dict[str, str]:
    """pytest -rfE 출력의 FAILED/ERROR 줄 → {테스트 id: 실패 문구}."""
    found: dict[str, str] = {}
    for line in output.splitlines():
        m = _FAIL_LINE.match(line.strip())
        if m:
            found[m.group(1)] = (m.group(2) or "").strip()
    return found


def new_failures(current: dict[str, str], baseline: dict[str, str]) -> list[str]:
    """기준선(HEAD)에서 같은 문구로 실패하던 것은 제외 — 새로 실패했거나 문구가 달라진 것만."""
    return sorted(t for t, msg in current.items() if t not in baseline or baseline[t] != msg)


def _pytest_cmd(targets: list[str]) -> list[str]:
    return [
        *_project_python(),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--tb=no",
        "-rfE",
        "--maxfail=25",
        *targets,
    ]


def _git_top_levels() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-tree", "--name-only", "HEAD"], cwd=str(ROOT), capture_output=True, timeout=10, check=False
    )
    names = proc.stdout.decode("utf-8", errors="ignore").splitlines()
    return [n for n in names if _TOP_LEVEL_ASCII.match(n) and n not in _SNAPSHOT_SKIP_DIRS]


def _prune_head_cache(keep: Path) -> None:
    others = sorted((d for d in HEAD_CACHE_DIR.glob("head_*") if d != keep), key=lambda d: d.stat().st_mtime)
    for old in others[: max(0, len(others) - (HEAD_CACHE_KEEP - 1))]:
        shutil.rmtree(old, ignore_errors=True)


def _head_snapshot() -> Path | None:
    """HEAD 커밋의 추적 파일을 캐시 폴더에 풀어 둔다(HEAD 별 1회). 실패하면 None."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        ).stdout.strip()
        if not sha:
            return None
        dest = HEAD_CACHE_DIR / f"head_{sha[:12]}"
        if (dest / ".ok").exists():
            return dest
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(
            ["git", "archive", "--format=tar", "HEAD", *_git_top_levels()],
            cwd=str(ROOT),
            capture_output=True,
            timeout=HEAD_SNAPSHOT_BUDGET_SECONDS,
            check=False,
        )
        if archive.returncode != 0:
            return None
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tf:
            tf.extractall(dest, filter="data")
        (dest / ".ok").write_text(sha, encoding="utf-8")
        _prune_head_cache(dest)
        return dest
    except Exception as exc:  # noqa: BLE001 - 기준선 스냅샷 실패는 '기준선 없음'으로 처리(종전처럼 차단), 훅 자체는 죽지 않는다
        sys.stderr.write(f"[post_edit_fast_gate] HEAD 스냅샷 실패(무시): {exc}\n")
        return None


def _baseline_failures(targets: list[str]) -> dict[str, str] | None:
    """HEAD 스냅샷에서 같은 테스트를 돌려 실패 목록을 얻는다. 스냅샷을 못 만들면 None."""
    snap = _head_snapshot()
    if snap is None:
        return None
    env = {**os.environ, "PYTHONPATH": str(snap), "COLUMNS": "400"}
    try:
        proc = _run(_pytest_cmd(targets), timeout=HEAD_SNAPSHOT_BUDGET_SECONDS, cwd=snap, env=env)
    except subprocess.TimeoutExpired:
        return None
    return parse_failures(proc.stdout)


def _impact_tests_gate(candidates: list[str], start: float) -> int:
    """영향 테스트 실행. 새로 실패한 것만 차단(2)하고, 기준선에서도 실패하던 것은 알리기만 한다."""
    env = {**os.environ, "COLUMNS": "400"}
    proc = _run(_pytest_cmd(candidates), timeout=_remaining(start), env=env)
    if proc.returncode in (0, 5):  # 5=collected 0 items
        return 0
    current = parse_failures(proc.stdout)
    baseline = _baseline_failures(sorted(current)) if current else None
    if baseline is None:
        sys.stderr.write(
            "[post_edit_fast_gate] 영향 테스트 실패(기준선 비교 불가):\n" + proc.stdout[-2000:] + proc.stderr[-500:]
        )
        return 2
    fresh = new_failures(current, baseline)
    if not fresh:
        sys.stderr.write(
            f"[post_edit_fast_gate] 영향 테스트 실패 {len(current)}건은 HEAD 에서도 같은 문구로 실패 — 기존 실패라 차단하지 않음\n"
        )
        return 0
    sys.stderr.write("[post_edit_fast_gate] 이번 편집 이후 새로 실패한 영향 테스트:\n")
    for test_id in fresh:
        sys.stderr.write(f"  {test_id} - {current[test_id]}\n")
    return 2


def _new_ruff_errors(current_text: str, rel_path: str) -> int:
    """편집 전(HEAD)에 없던 ruff 오류가 있으면 알리고 2, 없으면 0."""
    current_errors = _ruff_errors(current_text, ".py")
    baseline_text = _git_show_head(rel_path)
    baseline_errors = _ruff_errors(baseline_text, ".py") if baseline_text is not None else set()

    new_errors = current_errors - baseline_errors
    if not new_errors:
        return 0
    sys.stderr.write(f"[post_edit_fast_gate] 이번 편집으로 새로 생긴 ruff 오류가 있습니다 ({rel_path}):\n")
    for code, msg in sorted(new_errors):
        sys.stderr.write(f"  {code}: {msg}\n")
    sys.stderr.write("기존 오류(편집 전부터 있던 것)는 차단하지 않습니다. 위 신규 오류만 고치세요.\n")
    return 2


def _impact_candidates(rel_path: str, start: float) -> list[str]:
    """code_map 이 알려 주는 영향 테스트 파일(live/e2e 제외, 최대 MAX_TESTS개). 조회 실패는 빈 목록."""
    try:
        proc = _run(
            [*_project_python(), "-m", QUERY_MOD, "tests-for", rel_path],
            timeout=min(5, _remaining(start)),
        )
        # query.py 출력 형식: "  경로" 들여쓰기 라인
        candidates = []
        for ln in proc.stdout.splitlines():
            s = ln.strip()
            if s.startswith("tests-for:") or s.startswith("..."):
                continue
            if s.endswith(".py") and ("test" in s.lower()):
                candidates.append(s)
        return [c for c in candidates if not _SKIP_TEST_PATTERNS.search(c)][:MAX_TESTS]
    except Exception:  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        return []


def _check_python(file_path: Path, start: float) -> int:
    try:
        current_text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0

    try:
        rel_path = str(file_path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        rel_path = file_path.name

    if _new_ruff_errors(current_text, rel_path):
        return 2

    # 매핑 테스트 선별 실행
    if _remaining(start) < 2:
        return 0
    candidates = _impact_candidates(rel_path, start)
    if not candidates:
        return 0

    if _remaining(start) < 3:
        sys.stderr.write("[post_edit_fast_gate] 시간 초과 근접 — 매핑 테스트 실행 스킵(수동 확인 필요)\n")
        return 0

    try:
        return _impact_tests_gate(candidates, start)
    except subprocess.TimeoutExpired:
        sys.stderr.write("[post_edit_fast_gate] 영향 테스트 시간 초과 — 수동 확인 필요(차단 아님)\n")
    except Exception as exc:  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        sys.stderr.write(f"[post_edit_fast_gate] 영향 테스트 실행 실패(무시): {exc}\n")

    return 0


def _tsc_cache_fresh() -> bool:
    try:
        data = json.loads(TSC_CACHE_FILE.read_text(encoding="utf-8"))
        return (time.time() - float(data.get("ts", 0))) < TSC_CACHE_SECONDS
    except Exception:  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        return False


def _tsc_cache_write() -> None:
    try:
        TSC_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        TSC_CACHE_FILE.write_text(json.dumps({"ts": time.time()}), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        sys.stderr.write(f"[post_edit_fast_gate] tsc cache write failed (ignored): {exc}\n")


def _check_typescript(file_path: Path, start: float) -> int:
    admin_web = ROOT / "admin-web"
    try:
        file_path.resolve().relative_to(admin_web.resolve())
    except (ValueError, OSError):
        return 0  # admin-web 밖의 .ts 파일은 스킵

    if _tsc_cache_fresh():
        return 0

    if _remaining(start) < 5:
        sys.stderr.write("[post_edit_fast_gate] 시간 초과 근접 — typecheck 스킵(수동 확인 필요)\n")
        return 0

    try:
        proc = _run(["npm", "run", "typecheck"], timeout=_remaining(start), cwd=admin_web)
        _tsc_cache_write()
        if proc.returncode != 0:
            sys.stderr.write(
                "[post_edit_fast_gate] admin-web typecheck 실패:\n" + proc.stdout[-2000:] + proc.stderr[-500:]
            )
            return 2
    except subprocess.TimeoutExpired:
        sys.stderr.write("[post_edit_fast_gate] typecheck 시간 초과 — 수동 확인 필요(차단 아님)\n")
    except Exception as exc:  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        sys.stderr.write(f"[post_edit_fast_gate] typecheck 실행 실패(무시): {exc}\n")

    return 0


def main() -> int:
    # 훅 출력은 하네스가 UTF-8 로 읽는다. 파이프로 연결되면 파이썬 기본 인코딩이 cp949 라 한글이 깨져
    # 사용자에게 안내 문구(예: /clear 안내)가 읽히지 않았다(2026-10-01).
    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    start = time.monotonic()
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        return 0

    try:
        tool_input = payload.get("tool_input") or {}
        file_path_str = tool_input.get("file_path") or ""
        if not file_path_str:
            return 0
        file_path = Path(file_path_str)
        if not file_path.exists():
            return 0

        session_id = payload.get("session_id")
        try:
            rel_for_session = str(file_path.resolve().relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            rel_for_session = str(file_path)
        record_session_edit(session_id, rel_for_session)
        cleanup_old_session_edit_files()

        suffix = file_path.suffix.lower()
        if suffix == ".py":
            return _check_python(file_path, start)
        if suffix in (".ts", ".tsx"):
            return _check_typescript(file_path, start)
        return 0
    except Exception as exc:  # fail-open  # noqa: BLE001 - 훅(hook) 스크립트 — 보조 기록/캐시/영향테스트 조회 실패로 저장 자체를 막으면 안 되므로 의도적 fail-open(코드 주석에 이미 명시됨), 이 저장소 rules.toml ERR-06(훅 진입점은 넓은 예외로 감싼다)과 일치(2026-09-28 검토)
        sys.stderr.write(f"[post_edit_fast_gate] internal error (ignored): {exc}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
