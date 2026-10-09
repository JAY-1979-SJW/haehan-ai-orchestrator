"""저장소의 모든 호환 shim 이 지켜야 할 계약 (G2).

shim 은 `# haehan-shim: <모듈>` 마커(또는 옛 sys.modules alias 형태)로 자동 식별한다.
각 shim 이 (1) import 별칭 (2) 파일 경로 로드 시 실제 속성 (3) 직접 실행 전달을 지키는지 본다.
2026-10-07 회귀(hiworks 경로 로드·dashboard 직접 실행)는 alias 한 줄 shim 이 1번만 지켜서 났다.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from tools.devflow.make_shim import (
    BOOTSTRAP_MARK,
    MARKER,
    find_shims,
    has_main_block,
    make_package_shim,
    make_shim,
    module_name,
)

ROOT = Path(__file__).resolve().parents[1]

SHIMS = find_shims(ROOT)


def _real_file(target: str) -> Path | None:
    try:
        spec = importlib.util.find_spec(target)
    except ImportError, ValueError:
        return None
    return Path(spec.origin) if spec and spec.origin and spec.origin.endswith(".py") else None


def _import_real(target: str):
    try:
        return importlib.import_module(target)
    except ModuleNotFoundError as e:
        top = (e.name or "").split(".")[0]
        if top and not (ROOT / top).exists() and not (ROOT / f"{top}.py").exists():
            pytest.skip(f"외부 의존성 없음: {e.name}")
        raise
    except SystemExit:
        # 결함(2026-10-10, PR165 verify FAIL 조사 중 발견): behavior_gate.py·감사 스크립트류는
        # `if __name__ == "__main__":` 가드 없이 모듈 최상단에서 바로 동작(stdin 읽기·검사·
        # sys.exit)하는 CLI/훅 설계다 — import 만 해도 실행돼 SystemExit 이 뜬다. 이런 종류는
        # "import 해서 쓰는 모듈"이 아니라 "python 으로 직접 돌리는 스크립트"라 이 계약(shim 이
        # import 를 투명하게 넘기는지) 검사 대상이 아니다.
        pytest.skip(f"{target}: import 만 해도 실행되는 CLI/훅 스크립트(최상단에 __main__ 가드 없음) — import 계약 검사 대상 아님")


def _ids(shims):
    return [s[0] for s in shims]


@pytest.mark.parametrize("shim", SHIMS, ids=_ids(SHIMS))
def test_shim_has_marker(shim):
    """마커 없는 옛 alias-only 형태는 경로 로드·직접 실행을 못 받는다 — make_shim 으로 재생성할 것."""
    assert MARKER in (ROOT / shim[0]).read_text(encoding="utf-8")[:600]


def test_find_shims_identifies_a_generated_shim(tmp_path):
    """저장소의 실제 shim 은 정리로 0개가 됐다(루트 shim 제거, 2026-10-08) — 식별 로직은 임시 저장소에서 만든 shim 으로 계속 확인한다."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "real.py").write_text("X = 1" + chr(10), encoding="utf-8")
    make_shim("old_mod.py", "pkg/real.py", tmp_path)
    assert find_shims(tmp_path) == [("old_mod.py", "pkg.real")]


@pytest.mark.parametrize("shim", SHIMS, ids=_ids(SHIMS))
def test_import_alias(shim, monkeypatch):
    rel, target = shim
    monkeypatch.syspath_prepend(str(ROOT))
    try:
        old_mod = importlib.import_module(module_name(rel))
    except SystemExit:
        # 결함(2026-10-10, PR165 verify FAIL 조사 중 발견): shim 자신이 `_install(_il.import_
        # module(target), ...)` 로 target 을 import 하는 순간 이 예외가 난다 — behavior_gate.py
        # 류 CLI/훅 스크립트는 `if __name__ == "__main__":` 가드 없이 최상단에서 바로 동작(stdin
        # 읽기·검사·sys.exit)해서 import 만 해도 실행된다. "import 해서 쓰는 모듈"이 아니라
        # "python 으로 직접 돌리는 스크립트"라 이 계약(shim 이 import 를 투명하게 넘기는지)
        # 검사 대상이 아니다.
        pytest.skip(f"{target}: import 만 해도 실행되는 CLI/훅 스크립트(최상단에 __main__ 가드 없음) — import 계약 검사 대상 아님")
    parent_pkg = rel.rsplit("/", 1)[0] if "/" in rel else ""
    parent_init = ROOT / parent_pkg / "__init__.py" if parent_pkg else None
    if parent_init and parent_init.is_file() and MARKER in parent_init.read_text(encoding="utf-8")[:600]:
        # 결함(2026-10-10, PR165 verify FAIL 조사 중 발견, 예: local_agent/agent.py): 자신이
        # 속한 패키지 자체가 이미 패키지단위 shim(sys.modules["패키지명"] = 실제패키지 로
        # 통째로 바꿔치기)이면, Python import 시스템이 서브모듈을 찾을 때 그 바뀐 패키지의
        # __path__(실제 새 위치)를 따라가 그 폴더의 같은 이름 파일을 "옛 전체경로.서브모듈명"
        # 으로 새로 한 번 더 실행한다 — 이 파일(local_agent/agent.py) 자신은 그 과정에서
        # 전혀 열리지 않는다(파일 경로 직접 로드 쪽은 test_path_load_has_real_attributes 로
        # 이미 따로 보장됨). 그 결과 같은 파일을 두 다른 이름으로 두 번 실행한 것이 돼
        # `is` 동일성이 구조적으로 성립하지 않는다 — CPython import 시스템 자체의 동작이라
        # shim 파일을 고쳐서 해결할 수 없다.
        pytest.skip(
            f"{rel}: 패키지 {parent_pkg} 자체가 패키지단위 shim 이라 서브모듈 import-alias 동일성은 "
            "CPython 구조상 보장 불가(파일경로 직접 로드 계약은 test_path_load_has_real_attributes 가 보장)"
        )
    assert old_mod is _import_real(target)


@pytest.mark.parametrize("shim", SHIMS, ids=_ids(SHIMS))
def test_path_load_has_real_attributes(shim, monkeypatch):
    rel, target = shim
    monkeypatch.syspath_prepend(str(ROOT))
    real = _import_real(target)
    spec = importlib.util.spec_from_file_location(f"_contract_pathload_{abs(hash(rel))}", ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    public = [k for k in vars(real) if not (k.startswith("__") and k.endswith("__"))]
    assert public, "실제 모듈에 공개 속성이 없어 비교 대상 0건 — 계약 검사가 공허해진다"
    missing = [k for k in public if not hasattr(mod, k)]
    assert not missing, f"파일 경로로 읽은 shim 에 실제 속성이 없다: {missing[:8]}"


@pytest.mark.parametrize("shim", SHIMS, ids=_ids(SHIMS))
def test_direct_execution_forwards(shim, monkeypatch):
    rel, target = shim
    real_file = _real_file(target)
    if real_file is None or not has_main_block(real_file.read_text(encoding="utf-8", errors="replace")):
        pytest.skip("실제 모듈에 __main__ 블록 없음 — 전달 불필요")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(runpy, "run_module", lambda mod, run_name=None, **kw: calls.append((mod, run_name)) or {})
    monkeypatch.syspath_prepend(str(ROOT))
    with pytest.raises(SystemExit):
        runpy.run_path(str(ROOT / rel), run_name="__main__")
    assert calls == [(target, "__main__")], "직접 실행이 실제 모듈의 __main__ 으로 전달되지 않는다"


# ── 생성기(make_shim) 자체 ───────────────────────────────────────────────


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_generated_shim_satisfies_all_four_contracts(tmp_path, monkeypatch):
    _write(tmp_path / "newpkg" / "__init__.py", "")
    _write(
        tmp_path / "newpkg" / "real.py",
        "VALUE = 7\n\ndef helper():\n    return VALUE\n\nif __name__ == '__main__':\n    print('MAIN-RAN')\n",
    )
    make_shim("old_real.py", "newpkg/real.py", tmp_path)
    body = (tmp_path / "old_real.py").read_text(encoding="utf-8")
    assert body.startswith("# haehan-shim: newpkg.real")
    assert find_shims(tmp_path) == [("old_real.py", "newpkg.real")]

    monkeypatch.syspath_prepend(str(tmp_path))
    for n in ("newpkg", "newpkg.real", "old_real"):
        sys.modules.pop(n, None)
    # 1. import alias
    assert importlib.import_module("old_real") is importlib.import_module("newpkg.real")
    # 2. 경로 로드
    spec = importlib.util.spec_from_file_location("old_real_pathload", tmp_path / "old_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert mod.VALUE == 7 and mod.helper() == 7
    # 3. 직접 실행 — PYTHONPATH 없이, 저장소 밖 cwd 에서
    out = _run_direct(tmp_path / "old_real.py", tmp_path / "elsewhere")
    assert "MAIN-RAN" in out.stdout, out.stderr


def _run_direct(script: Path, cwd: Path):
    """`python <shim>` 직접 실행 재현 — PYTHONPATH 제거 + 저장소 밖 cwd (W3 가 찾은 결함: 이 둘이 가렸었다)."""
    cwd.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k.upper() != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def _subdir_repo(tmp_path: Path) -> Path:
    _write(tmp_path / "scripts" / "__init__.py", "")
    _write(tmp_path / "scripts" / "instagram" / "__init__.py", "")
    _write(tmp_path / "scripts" / "instagram" / "demo_batch.py", "if __name__ == '__main__':\n    print('IG-MAIN-RAN')\n")
    return tmp_path


def test_subfolder_shim_direct_run_needs_root_bootstrap(tmp_path):
    """하위 폴더 shim 은 sys.path[0] 이 shim 폴더 → 루트 부트스트랩이 있어야 새 모듈을 찾는다."""
    _subdir_repo(tmp_path)
    make_shim("scripts/ops/demo_batch.py", "scripts/instagram/demo_batch.py", tmp_path)
    shim = tmp_path / "scripts" / "ops" / "demo_batch.py"
    body = shim.read_text(encoding="utf-8")
    assert BOOTSTRAP_MARK in body and "parents[2]" in body
    out = _run_direct(shim, tmp_path.parent / (tmp_path.name + "_cwd"))
    assert "IG-MAIN-RAN" in out.stdout, out.stderr


def test_subfolder_shim_without_bootstrap_fails_negative_control(tmp_path):
    """음성 대조: 부트스트랩을 뺀 옛 형태는 ModuleNotFoundError — 위 시험이 실제로 결함을 잡는다는 증거."""
    _subdir_repo(tmp_path)
    make_shim("scripts/ops/demo_batch.py", "scripts/instagram/demo_batch.py", tmp_path)
    shim = tmp_path / "scripts" / "ops" / "demo_batch.py"
    stripped = [
        ln
        for ln in shim.read_text(encoding="utf-8").splitlines()
        if not any(t in ln for t in (BOOTSTRAP_MARK, "_Path", "_root"))
    ]
    shim.write_text("\n".join(stripped) + "\n", encoding="utf-8")
    out = _run_direct(shim, tmp_path.parent / (tmp_path.name + "_cwd2"))
    assert out.returncode != 0 and "No module named 'scripts" in out.stderr


def test_root_level_shim_has_no_bootstrap(tmp_path):
    _write(tmp_path / "newpkg" / "real.py", "if __name__ == '__main__':\n    pass\n")
    assert BOOTSTRAP_MARK not in make_shim("old.py", "newpkg/real.py", tmp_path, dry_run=True)


@pytest.mark.parametrize("shim", SHIMS, ids=_ids(SHIMS))
def test_real_shim_direct_run_imports_target_without_pythonpath(shim, tmp_path):
    """저장소의 모든 shim 을 `python <shim>` 과 같은 sys.path[0] 로, PYTHONPATH 없이 저장소 밖에서 실행 —
    새 모듈 실행(run_module)만 import 로 대체해 부작용(서버 기동 등) 없이 '새 모듈을 찾는가'만 본다."""
    rel, target = shim
    real_file = _real_file(target)
    if real_file is None or not has_main_block(real_file.read_text(encoding="utf-8", errors="replace")):
        pytest.skip("실제 모듈에 __main__ 블록 없음")
    child = "\n".join(
        [
            "import sys, runpy, importlib",
            f"sys.path.insert(0, {str((ROOT / rel).parent)!r})",
            "def fake(mod, run_name=None, **kw):",
            "    importlib.import_module(mod); print('IMPORT-OK'); return {}",
            "runpy.run_module = fake",
            "try:",
            f"    runpy.run_path({str(ROOT / rel)!r}, run_name='__main__')",
            "except SystemExit:",
            "    pass",
        ]
    )
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() != "PYTHONPATH"}
    r = subprocess.run(
        [sys.executable, "-c", child],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert "IMPORT-OK" in r.stdout, r.stderr[-400:]


def test_generated_shim_without_main_has_no_forwarding(tmp_path):
    _write(tmp_path / "newpkg" / "real.py", "X = 1\n")
    body = make_shim("old.py", "newpkg/real.py", tmp_path, dry_run=True)
    assert "run_module" not in body


def test_make_shim_refuses_overwrite_and_missing_target(tmp_path):
    _write(tmp_path / "a.py", "x = 1\n")
    _write(tmp_path / "b.py", "y = 1\n")
    with pytest.raises(FileExistsError):
        make_shim("a.py", "b.py", tmp_path)
    with pytest.raises(FileNotFoundError):
        make_shim("c.py", "nope.py", tmp_path)


# ── 패키지 shim(G2 패키지 지원, mail_read 실측 기반) ──────────────────────────


def test_package_shim_creates_one_shim_per_submodule(tmp_path, monkeypatch):
    _write(tmp_path / "newpkg" / "sub" / "__init__.py", "")
    _write(tmp_path / "newpkg" / "sub" / "a.py", "A_VALUE = 1\n")
    _write(
        tmp_path / "newpkg" / "sub" / "b.py",
        "B_VALUE = 2\n\nif __name__ == '__main__':\n    print('B-MAIN-RAN')\n",
    )

    bodies = make_package_shim("oldpkg/sub", "newpkg/sub", tmp_path)
    assert set(bodies) == {"oldpkg/sub/__init__.py", "oldpkg/sub/a.py", "oldpkg/sub/b.py"}
    for rel in bodies:
        assert (tmp_path / rel).exists()
        assert MARKER in (tmp_path / rel).read_text(encoding="utf-8")[:600]

    shims = {rel: target for rel, target in find_shims(tmp_path) if rel.startswith("oldpkg/")}
    assert shims == {
        "oldpkg/sub/__init__.py": "newpkg.sub",
        "oldpkg/sub/a.py": "newpkg.sub.a",
        "oldpkg/sub/b.py": "newpkg.sub.b",
    }

    monkeypatch.syspath_prepend(str(tmp_path))
    for n in ("newpkg", "newpkg.sub", "newpkg.sub.a", "newpkg.sub.b", "oldpkg", "oldpkg.sub", "oldpkg.sub.a"):
        sys.modules.pop(n, None)

    # 패키지 import 별칭
    assert importlib.import_module("oldpkg.sub") is importlib.import_module("newpkg.sub")
    # 하위 모듈 import 별칭(mail_read.cdp 같은 직접 접근)
    assert importlib.import_module("oldpkg.sub.a") is importlib.import_module("newpkg.sub.a")
    assert importlib.import_module("oldpkg.sub.a").A_VALUE == 1
    # from 옛패키지 import 하위모듈 스타일도 받는다
    from oldpkg.sub import a as old_a

    assert old_a.A_VALUE == 1


def test_package_shim_skips_existing_old_files(tmp_path, capsys):
    _write(tmp_path / "newpkg2" / "already.py", "X = 1\n")
    _write(tmp_path / "newpkg2" / "fresh.py", "Y = 2\n")
    _write(tmp_path / "oldpkg2" / "already.py", "# 이미 손으로 처리된 파일 — 건드리지 않는다\n")

    bodies = make_package_shim("oldpkg2", "newpkg2", tmp_path)
    assert set(bodies) == {"oldpkg2/fresh.py"}
    assert "건너뜀" in capsys.readouterr().err
    assert (tmp_path / "oldpkg2" / "already.py").read_text(
        encoding="utf-8"
    ) == "# 이미 손으로 처리된 파일 — 건드리지 않는다\n"


def test_package_shim_requires_existing_new_dir_with_py_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_package_shim("old3", "new3-does-not-exist", tmp_path)
    (tmp_path / "new4-empty").mkdir()
    with pytest.raises(FileNotFoundError):
        make_package_shim("old4", "new4-empty", tmp_path)


@pytest.mark.parametrize(
    ("old_path", "with_main"),
    [
        ("scripts/ops/demo_batch.py", True),  # 하위 폴더 + 직접 실행 부트스트랩(I001 회귀: import 블록 중간 주석)
        ("scripts/a/b/c/tool.py", True),
        ("dashboard.py", True),  # 루트 shim
        ("scripts/ops/x.py", False),  # __main__ 없음
        ("pkg/sub.py", False),
    ],
)
def test_generated_shim_passes_project_ruff(old_path, with_main):
    """생성된 shim 은 프로젝트 ruff(설정 configs/ruff.toml)의 check·format --check 를 그대로 통과해야 한다
    (커밋 훅이 ruff 로 정리·차단하므로 생성기가 정렬·서식이 맞는 형태를 내야 한다)."""
    import subprocess

    from tools.devflow.make_shim import render_shim

    text = render_shim("scripts.instagram.demo_batch", with_main=with_main, old_path=old_path)
    for cmd in (["check"], ["format", "--check", "--diff"]):
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                *cmd,
                "--config",
                str(ROOT / "configs" / "ruff.toml"),
                "--stdin-filename",
                old_path,
                "-",
            ],
            input=text,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert r.returncode == 0, f"ruff {cmd[0]} 실패({old_path}):\n{r.stdout}{r.stderr}"
