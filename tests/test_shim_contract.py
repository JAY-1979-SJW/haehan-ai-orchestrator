"""저장소의 모든 호환 shim 이 지켜야 할 계약 (G2).

shim 은 `# haehan-shim: <모듈>` 마커(또는 옛 sys.modules alias 형태)로 자동 식별한다.
각 shim 이 (1) import 별칭 (2) 파일 경로 로드 시 실제 속성 (3) 직접 실행 전달을 지키는지 본다.
2026-10-07 회귀(hiworks 경로 로드·dashboard 직접 실행)는 alias 한 줄 shim 이 1번만 지켜서 났다.
"""

from __future__ import annotations

import importlib
import importlib.util
import runpy
import sys
from pathlib import Path

import pytest

from scripts.ops.make_shim import MARKER, find_shims, has_main_block, make_shim

ROOT = Path(__file__).resolve().parents[1]

SHIMS = find_shims(ROOT)

# 계약을 아직 못 지키는 기존 shim. 마커(# haehan-shim:) 없는 1단계 alias-only shim 은 경로 로드 속성이 없다 —
# 이번 도구 이전 형태라 알려진 부채로 xfail(비엄격: 재생성하면 XPASS 로 통과). 새 shim 은 마커가 있어 예외 없다.
# dashboard 직접 실행 전달은 W3 b02dcbb7 이 고친다(병합되면 XPASS).
_LEGACY = {rel for rel, _ in SHIMS if MARKER not in (ROOT / rel).read_text(encoding="utf-8", errors="replace")[:600]}
KNOWN_GAPS: dict[tuple[str, str], str] = {
    **{(rel, "pathload"): "마커 없는 1단계 alias-only shim — make_shim 으로 재생성 필요" for rel in _LEGACY},
    ("dashboard.py", "direct"): "직접 실행 전달 없음 — W3 b02dcbb7 병합 대기",
}


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


def _ids(shims):
    return [s[0] for s in shims]


def _mark(shim: tuple[str, str], kind: str):
    reason = KNOWN_GAPS.get((shim[0], kind))
    return pytest.param(shim, marks=pytest.mark.xfail(strict=False, reason=reason)) if reason else shim


def test_shims_are_found():
    assert SHIMS, "shim 을 하나도 못 찾음 — 식별 로직 점검"


@pytest.mark.parametrize("shim", [_mark(s, "alias") for s in SHIMS], ids=_ids(SHIMS))
def test_import_alias(shim, monkeypatch):
    rel, target = shim
    monkeypatch.syspath_prepend(str(ROOT))
    old_mod = importlib.import_module(Path(rel).with_suffix("").as_posix().replace("/", "."))
    assert old_mod is _import_real(target)


@pytest.mark.parametrize("shim", [_mark(s, "pathload") for s in SHIMS], ids=_ids(SHIMS))
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


@pytest.mark.parametrize("shim", [_mark(s, "direct") for s in SHIMS], ids=_ids(SHIMS))
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
    # 3. 직접 실행
    import subprocess

    r = subprocess.run(
        [sys.executable, str(tmp_path / "old_real.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**__import__("os").environ, "PYTHONPATH": str(tmp_path)},
    )
    assert "MAIN-RAN" in r.stdout, r.stderr


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
