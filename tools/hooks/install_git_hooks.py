"""git hook 설치 스크립트.

.git/hooks/pre-commit  — ruff 문법/품질 검사 (staged 파일만)
.git/hooks/pre-push    — Claude Code AI 코드 검수

실행:
  python tools/hooks/install_git_hooks.py
"""

from __future__ import annotations

import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
# core.hooksPath = .githooks (프로젝트 설정)
HOOKS_DIR = ROOT / ".githooks"
CHECKLIST_MARKER = "# commit-checklist-wrapper v1"  # install_commit_checklist.py MARKER 와 동일

PRE_COMMIT = """\
#!/usr/bin/env python
import subprocess, sys
from pathlib import Path

ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
)  # __file__ 기준이면 core.hooksPath 공유 시 worktree 에서도 항상 메인 체크아웃을
# 가리켜 내용을 조용히 훼손한다(2026-09-28 worktree 병렬 세션에서 실측 발견).
# 실행 시점 cwd(git 이 훅에 주는 실제 worktree 루트) 기준으로 고정.


def _pyexe():
    # Windows py 런처로 프로젝트 고정 버전(3.14) 우선 — PATH의 "python"이 다른 버전
    # (예: 3.11)을 가리키면 그 버전엔 없는 패키지(예: audit_kit)가 없어 훅이 실패한다
    # (admin-web/electron/lib/agent.js resolvePython() 과 동일 사유, 2026-09-29
    # pre-push 훅에서 실측: "No module named audit_kit").
    import shutil

    if shutil.which("py"):
        try:
            subprocess.run(["py", "-3.14", "--version"], capture_output=True, check=True)
            return ["py", "-3.14"]
        except Exception:
            pass
    return [sys.executable]


# staged .py 파일 목록
# encoding 명시: Windows 기본 코드페이지(cp949)가 diff에 섞인 UTF-8 특수문자에서
# reader 스레드를 죽이는 문제 방지(2026-09-28 실측 발견 — 이 문제로 훅이 크래시했었음).
r = subprocess.run(
    ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
    cwd=str(ROOT), capture_output=True, text=True,
    encoding="utf-8", errors="replace",
)
py_files = [f for f in r.stdout.splitlines() if f.endswith(".py")]

if py_files:
    cfg = str(ROOT / "configs" / "ruff.toml")
    # 자동 수정·포맷은 이번 커밋에서 "새로 추가된(A)" 파일에만 적용한다.
    # 기존 파일에 적용하면 한 줄 수정도 파일 전체 기존 오류 정리·재포맷을 강제해
    # 대량 서식 변경과 커밋 차단이 생긴다(defect_index #30, 2026-10-01).
    # 기존 파일은 아래 3단계의 "새로 생긴 위반만 차단"으로 충분하다.
    _ra = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    _added = set(_ra.stdout.splitlines())
    fix_files = [f for f in py_files if f in _added]
    if fix_files:
        # 1. ruff check (자동 수정). F401 은 자동수정 제외 — 파사드의 재노출 import
        #    (mock.patch 대상·하위 호환 이름)를 '미사용'으로 지워 조용히 깨뜨린다
        #    (defect_index #33, #93, #110 에서 반복 발생).
        subprocess.run(
            [*_pyexe(), "-m", "ruff", "check", "--fix", "--unfixable", "F401",
             "--config", cfg] + fix_files,
            cwd=str(ROOT),
        )
        # 2. ruff format
        subprocess.run(
            [*_pyexe(), "-m", "ruff", "format", "--config", cfg] + fix_files,
            cwd=str(ROOT),
        )
        # ruff 가 수정한 신규 파일을 다시 stage
        subprocess.run(["git", "add"] + fix_files, cwd=str(ROOT))
    # 3. 자동수정 안 되는 나머지 위반은 "이번 커밋으로 새로 생긴 것"만 차단한다.
    #    (BLE001 같은 대규모 기존 부채가 있는 파일을 조금만 건드려도 매번 전체가
    #    막히면 사실상 개발이 정지된다 — CLAUDE.md "새 훅은 새로 생긴 오류만
    #    차단" 원칙을 실제로 구현, 2026-09-28)
    gate = ROOT / "scripts" / "ops" / "repo_gates" / "ruff_new_only_gate.py"
    if gate.exists():
        gate_result = subprocess.run(
            [*_pyexe(), str(gate), "--config", cfg] + py_files,
            cwd=str(ROOT),
        )
        if gate_result.returncode != 0:
            print("[ruff] 이번 변경으로 새로 생긴 위반이 있습니다. 위 내용을 확인하고 재커밋하세요.")
            sys.exit(1)

# ── 로그인 세션 파기 코드 차단 ───────────────────────────────────────
# 세션을 임의 로그아웃/쿠키삭제하면 '매번 재로그인' 문제 발생(CLAUDE.md 로그인 세션 보존).
# staged .py 에 세션 파기 패턴이 추가되면 차단. 정당한 로그아웃이면 줄에 '# session-ok'.
# (이 훅 설치 파일 자신은 패턴을 데이터로 가지므로 제외)
_sg_files = [f for f in py_files if not f.endswith("install_git_hooks.py")]
if _sg_files:
    _sdiff = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--"] + _sg_files,
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    _sess_pat = (
        "nidlogin.logout", "logout.naver", "clear_cookies", "delete_cookies",
        "deleteallcookies", "cookies.clear", "context.clear_cookies",
    )
    _sess_bad = []
    for _ln in _sdiff.stdout.splitlines():
        if _ln.startswith("+") and not _ln.startswith("+++"):
            _body = _ln[1:]
            if "session-ok" in _body:
                continue
            _low = _body.lower()
            if any(_pp in _low for _pp in _sess_pat):
                _sess_bad.append(_body.strip())
    if _sess_bad:
        print("=" * 60)
        print("[session-guard] 로그인 세션 파기 코드 감지 — 매번 재로그인 유발:")
        for _b in _sess_bad[:8]:
            print("    + " + _b[:90])
        print("    세션은 유지해야 합니다(CLAUDE.md 로그인 세션 보존).")
        print("    정당한 로그아웃이면 해당 줄에 '# session-ok' 주석을 추가하세요.")
        print("=" * 60)
        sys.exit(1)

# ── 소스 실행 방식 강제 ──────────────────────────────────────────────
# launcher(start_haehan_ai.ps1)가 frozen exe / Next standalone 빌드본을 '실행'하면 차단.
# 백엔드=uvicorn 소스, 프론트=next dev 소스 유지(재빌드 불필요). 정당한 예외는 파일에 '# source-ok'.
all_staged = r.stdout.splitlines()
if "scripts/start_haehan_ai.ps1" in all_staged:
    try:
        _txt = (ROOT / "scripts" / "start_haehan_ai.ps1").read_text(encoding="utf-8", errors="replace")
    except Exception:
        _txt = ""
    if "# source-ok" not in _txt:
        _bad = []
        if "Start-Process $FASTAPI" in _txt:
            _bad.append("FastAPI를 frozen exe로 실행 — uvicorn 소스로 유지하세요")
        if "-ArgumentList $NEXTJS" in _txt:
            _bad.append("Next를 standalone 빌드본(server.js)으로 실행 — next dev 소스로 유지하세요")
        if "uvicorn" not in _txt:
            _bad.append("uvicorn(소스 백엔드) 실행 흔적이 없습니다")
        if '"dev"' not in _txt:
            _bad.append("next dev(소스 프론트) 실행 흔적이 없습니다")
        if _bad:
            print("=" * 60)
            print("[source-only] launcher가 소스 실행 방식을 벗어났습니다 (재빌드 금지):")
            for _b in _bad:
                print("    - " + _b)
            print("    백엔드=uvicorn 소스, 프론트=next dev 소스로 유지하세요.")
            print("    정당한 예외면 start_haehan_ai.ps1 에 '# source-ok' 주석을 추가하세요.")
            print("=" * 60)
            sys.exit(1)

# ── windowsHide 누락 차단 (JS/Electron spawn) ───────────────────────────────
# Windows에서 windowsHide 없이 spawn하면 콘솔 창이 튀어나옴(터미널 창 문제 재발 방지).
_js_staged = [f for f in r.stdout.splitlines()
              if f.startswith("admin-web/electron/") and f.endswith(".js")]
if _js_staged:
    import re as _re
    _spawn_pat = _re.compile(r"\\bspawn\\s*\\(")
    _hide_pat = _re.compile(r"windowsHide\\s*:\\s*true")
    _jsdiff = subprocess.run(
        ["git", "diff", "--cached", "-U5", "--"] + _js_staged,
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    _chunks, _cur = [], []
    for _ln in _jsdiff.stdout.splitlines():
        if _ln.startswith("@@"):
            if _cur: _chunks.append("\\n".join(_cur))
            _cur = [_ln]
        else:
            _cur.append(_ln)
    if _cur: _chunks.append("\\n".join(_cur))
    _win_bad = []
    for _chunk in _chunks:
        _added = "\\n".join(l[1:] for l in _chunk.splitlines() if l.startswith("+") and not l.startswith("+++"))
        if _spawn_pat.search(_added) and not _hide_pat.search(_chunk):
            _ctx = _added[:120].replace("\\n", " | ")
            _win_bad.append(_ctx)
    if _win_bad:
        print("=" * 60)
        print("[windowsHide-guard] spawn() 에 windowsHide:true 없음 — 터미널 창 유발 위험:")
        for _w in _win_bad[:5]:
            print("    " + _w)
        print("    spawn() 옵션에 windowsHide: true 를 추가하세요.")
        print("=" * 60)
        sys.exit(1)

# ── 지도↔골격 대조 게이트 (skeleton_gate) ────────────────────────────────
# 정본(module_registry.json)이 스테이지된 A/D/R 코드 파일·추적 파일과 어긋나면 차단.
# 우회: SKELETON_GATE_SKIP_REASON="사유" 환경변수 (감사 로그 기록됨).
_sg = ROOT / "scripts" / "ops" / "code_map" / "skeleton_gate.py"
if _sg.exists():
    _sg_result = subprocess.run([*_pyexe(), str(_sg)], cwd=str(ROOT))
    if _sg_result.returncode != 0:
        sys.exit(_sg_result.returncode)

# ── audit-kit 개발 기준서 게이트 (staged .py 의 신규 문제만 차단) ──────────
# audit-kit 를 못 찾으면 건너뛰지만 AUDIT_KIT_REQUIRED=1 이면 커밋을 막는다.
_ak = ROOT / "scripts" / "ops" / "hooks" / "audit_kit_gate.py"
if _ak.exists():
    _ak_result = subprocess.run([*_pyexe(), str(_ak), "--staged"], cwd=str(ROOT))
    if _ak_result.returncode != 0:
        sys.exit(_ak_result.returncode)

# 기존 quality gate (pre-commit 내장)
from pathlib import Path as _P
import importlib.util, os
gate = ROOT / "scripts" / "ops" / "quality" / "quality_gate.py"
if gate.exists():
    # 2026-09-30 수정(defect_index #2): 이 훅이 --allow-existing-code-change 를 항상
    # 넘겨서 existing_code_change_requires_flag 안전장치가 영구 무력화돼 있었다.
    # 완전 차단은 비현실적이라 최소한 기존 활성 코드 수정 개수를 콘솔에 드러낸다.
    # (이 블록이 설치 원본에 없어 세션마다 .orig 가 덮어써져 사라지던 것을 2026-10-01 복원)
    try:
        _diff = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            cwd=str(ROOT), capture_output=True, text=True, check=True,
        ).stdout
        _modified = [
            line.split("\t", 1)[1] for line in _diff.splitlines()
            if line.startswith("M\t") and line.split("\t", 1)[1].endswith(".py")
        ]
        if _modified:
            print(f"[quality_gate] 기존 코드 수정 {len(_modified)}개 파일 감지 "
                  f"(--allow-existing-code-change 자동 적용됨):")
            for _m in _modified[:10]:
                print(f"    {_m}")
            if len(_modified) > 10:
                print(f"    ... 외 {len(_modified) - 10}개")
    except (subprocess.CalledProcessError, OSError):
        pass  # 가시성 로그 실패는 커밋을 막지 않음

    result = subprocess.run(
        [*_pyexe(), str(gate), "--staged", "--enforce", "--allow-existing-code-change"],
        cwd=str(ROOT),
    )
    sys.exit(result.returncode)
"""

PRE_PUSH = """\
#!/usr/bin/env python
import subprocess, sys
from pathlib import Path

ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
)  # worktree-aware (2026-09-28, pre-commit.orig 와 동일 사유)


def _pyexe():
    # Windows py 런처로 프로젝트 고정 버전(3.14) 우선 — PATH의 "python"이 다른 버전
    # (예: 3.11)을 가리키면 그 버전엔 없는 패키지(예: audit_kit)가 없어 훅이 실패한다
    # (admin-web/electron/lib/agent.js resolvePython() 과 동일 사유, 2026-09-29
    # pre-push 훅에서 실측: "No module named audit_kit").
    import shutil

    if shutil.which("py"):
        try:
            subprocess.run(["py", "-3.14", "--version"], capture_output=True, check=True)
            return ["py", "-3.14"]
        except Exception:
            pass
    return [sys.executable]


# Claude Code AI 코드 검수
result = subprocess.run(
    [*_pyexe(), str(ROOT / "scripts" / "ops" / "hooks" / "ai_code_review_gate.py")],
    cwd=str(ROOT),
)
sys.exit(result.returncode)
"""


POST_COMMIT = """\
#!/usr/bin/env python
import subprocess, sys
from pathlib import Path

ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
)  # worktree-aware (2026-09-28, pre-commit.orig 와 동일 사유)

# 모든 커밋을 data/ops/worklog.jsonl 에 1줄 기록 (session_handoff_guard).
# 커밋 자체를 절대 실패시키지 않는다(never fail the commit).
try:
    sys.path.insert(0, str(ROOT))
    from tools.hooks import session_handoff as sh

    _enc = {"encoding": "utf-8", "errors": "replace"}
    h = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, **_enc).stdout.strip()
    subj = subprocess.run(["git", "log", "-1", "--pretty=%s"], cwd=str(ROOT), capture_output=True, text=True, **_enc).stdout.strip()
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, **_enc).stdout.strip()
    files_out = subprocess.run(["git", "show", "--stat", "--format=", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, **_enc).stdout
    files_changed = len([ln for ln in files_out.splitlines() if "|" in ln])
    sh.log_event("commit", hash=h, subject=subj, branch=branch, files_changed=files_changed)
except Exception:
    pass
sys.exit(0)
"""


def install(name: str, content: str) -> None:
    path = HOOKS_DIR / name
    if path.exists():
        # .githooks 는 git 이 추적하는 정본이다. 세션 시작 훅(.claude/settings.json)이 매번 이 설치기를 돌리는데, 내장 템플릿은
        # 정본보다 오래돼 덮어쓰면 게이트 8개 연결(96줄)이 사라진 채 `git add -A` 로 커밋됐다(2026-10-08 PR #162 사고).
        # 없을 때만 만들고, 있으면 내용은 건드리지 않고 실행 권한만 맞춘다.
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"[install_git_hooks] {name} 이미 있음 — 내용은 덮어쓰지 않음: {path}")
        return
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"[install_git_hooks] {name} 설치 완료: {path}")


def _git_config(root: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", str(root), "config", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.returncode, (proc.stdout or "").strip()


def ensure_hooks_path(root: Path = ROOT, git_config: Callable[..., tuple[int, str]] = _git_config) -> str:
    """`core.hooksPath` 가 `.githooks` 를 가리키게 맞춘다. 훅 파일만 쓰고 이 설정이 없으면 git 이 훅을 실행하지 않는다.

    새로 복제한 저장소·다른 PC 는 로컬 설정이 비어 있어 훅이 "설치됨"인데 동작하지 않던 문제(2026-10-04 실측)를 막는다.
    이미 다른 값이 설정돼 있으면 덮어쓰지 않고 알리기만 한다. 반환: 'ok' | 'set' | 'other' | 'failed'.
    """
    code, current = git_config(root, "--get", "core.hooksPath")
    if code == 0 and current == ".githooks":
        return "ok"
    if code == 0 and current:
        print(
            f"[install_git_hooks] core.hooksPath 가 이미 '{current}' 로 설정돼 있어 바꾸지 않았습니다(.githooks 훅이 동작하지 않을 수 있음)"
        )
        return "other"
    code, out = git_config(root, "core.hooksPath", ".githooks")
    if code != 0:
        print(f"[install_git_hooks] core.hooksPath 설정 실패: {out}")
        return "failed"
    print("[install_git_hooks] core.hooksPath=.githooks 를 설정했습니다(이전에는 비어 있어 훅이 동작하지 않았음)")
    return "set"


def main() -> None:
    if not HOOKS_DIR.exists():
        print(f"[install_git_hooks] .git/hooks 디렉터리를 찾을 수 없습니다: {HOOKS_DIR}")
        sys.exit(1)
    # 커밋 전 체크리스트 래퍼(.githooks/install_commit_checklist.py)가 설치돼 있으면 래퍼를
    # 덮어쓰지 않고 래퍼가 호출하는 pre-commit.orig 만 갱신한다(덮어쓰면 비밀키 검사가 빠짐).
    pre = HOOKS_DIR / "pre-commit"
    wrapped = pre.exists() and CHECKLIST_MARKER in pre.read_text(encoding="utf-8", errors="replace")
    install("pre-commit.orig" if wrapped else "pre-commit", PRE_COMMIT)
    install("pre-push", PRE_PUSH)
    install("post-commit", POST_COMMIT)
    state = ensure_hooks_path()
    if state in ("ok", "set"):
        print("[install_git_hooks] 완료. pre-commit(ruff) + pre-push(AI 검수) + post-commit(작업기록) 활성화됨.")
    else:
        print(
            "[install_git_hooks] 훅 파일은 설치했지만 core.hooksPath 문제로 git 이 실행하지 않을 수 있습니다(위 안내 참고)."
        )


if __name__ == "__main__":
    main()
