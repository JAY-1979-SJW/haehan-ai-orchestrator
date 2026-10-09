"""이식성 표준(docs/specs/2026-10-04_portability_standard.md) 유지 시험 + make_constraints 도구 시험.

다른 PC 에 설치해도 같은 방식으로 돌게 하는 약속이 깨지면(훅에 파이썬 마이너 버전 고정·개인 절대경로, 제약 파일과 requirements 의 불일치) 실패한다.
"""

from __future__ import annotations

import json
import re
from importlib import metadata
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from tools.devflow import make_constraints as mc

ROOT = Path(__file__).resolve().parents[2]


# ── 저장소의 이식성 약속 ──────────────────────────────────────────────────


def _hook_commands() -> list[str]:
    data = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return [h["command"] for entries in data["hooks"].values() for e in entries for h in e.get("hooks", []) if h.get("type") == "command"]


def test_hooks_do_not_pin_python_minor_version():
    """`py -3.14` 처럼 마이너 버전을 박으면 그 버전이 없는 PC 에서 안전 훅(호출 차단·세션 보호)이 전부 실패한다."""
    assert _hook_commands()  # 훅 명령을 실제로 읽었다(비어 있으면 아래 검사가 항상 통과해 버린다)
    pinned = [c[:80] for c in _hook_commands() if re.search(r"\bpy -3\.\d+", c)]
    assert pinned == []


def test_hooks_have_no_machine_specific_absolute_paths():
    assert _hook_commands()
    bad = [c[:80] for c in _hook_commands() if re.search(r"[A-Za-z]:[\\/]+(Users|work)[\\/]", c)]
    assert bad == []  # 저장소 위치는 git rev-parse 로 찾는다


def test_constraints_file_is_well_formed_and_covers_requirements():
    lines = [ln for ln in (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
    pins = {}
    for ln in lines:
        match = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.!+\-]+)", ln)
        assert match, f"형식이 다른 줄: {ln!r}"
        assert match.group(1) not in pins, f"중복: {match.group(1)}"
        pins[match.group(1)] = match.group(2)
    for req in mc.read_requirements(ROOT / "requirements.txt"):
        if req.marker is not None and not req.marker.evaluate({"extra": ""}):
            continue  # 이 플랫폼에서는 설치하지 않는 요구(예: win32 전용)
        assert canonicalize_name(req.name) in pins, f"constraints.txt 에 {req.name} 가 없음 — python tools/devflow/make_constraints.py 로 다시 만드세요"


def test_constraints_satisfy_the_requirement_ranges():
    pins = dict(ln.split("==") for ln in (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines() if "==" in ln)
    for req in mc.read_requirements(ROOT / "requirements.txt"):
        version = pins.get(canonicalize_name(req.name))
        if version is not None:
            assert req.specifier.contains(version, prereleases=True), f"{req.name}=={version} 가 요구 범위 {req.specifier} 를 벗어남"


# ── make_constraints 도구 ────────────────────────────────────────────────


class FakeDist:
    def __init__(self, version: str, requires: list[str] | None = None) -> None:
        self.version, self.requires = version, requires


def fake_distribution(table: dict[str, FakeDist]):
    def lookup(name: str):
        key = canonicalize_name(name)
        if key not in table:
            raise metadata.PackageNotFoundError(name)
        return table[key]

    return lookup


def test_closure_follows_transitive_deps_extras_and_markers():
    table = {
        "app": FakeDist("1.0", ["lib>=1", "extra-only; extra == 'full'", "win-only; sys_platform == 'nope-os'"]),
        "lib": FakeDist("2.3", ["leaf"]),
        "leaf": FakeDist("0.5"),
        "extra-only": FakeDist("9.9"),
        "win-only": FakeDist("1.1"),
    }
    versions, missing = mc.closure([Requirement("app")], fake_distribution(table))
    assert versions == {"app": "1.0", "lib": "2.3", "leaf": "0.5"} and missing == []  # extra·다른 OS 전용은 제외
    with_extra, _ = mc.closure([Requirement("app[full]")], fake_distribution(table))
    assert "extra-only" in with_extra and "win-only" not in with_extra


def test_closure_reports_missing_and_handles_cycles():
    table = {"a": FakeDist("1", ["b"]), "b": FakeDist("2", ["a", "ghost"])}
    versions, missing = mc.closure([Requirement("a")], fake_distribution(table))
    assert versions == {"a": "1", "b": "2"} and missing == ["ghost"]  # 순환 의존도 끝난다


def test_read_requirements_skips_comments_options_and_rejects_garbage(tmp_path):
    f = tmp_path / "req.txt"
    f.write_text("# 주석\n\n-r other.txt\n--index-url https://x\nfoo>=1.0  # 메모\nbar[extra]>=2; sys_platform == 'win32'\n", encoding="utf-8")
    assert [r.name for r in mc.read_requirements(f)] == ["foo", "bar"]
    f.write_text("this is not a requirement !!\n", encoding="utf-8")
    with pytest.raises(ValueError, match="해석할 수 없습니다"):
        mc.read_requirements(f)


def test_render_is_sorted_stable_and_has_header():
    from datetime import date

    text = mc.render({"zlib": "1.0", "alpha": "2.0"}, today=date(2026, 10, 4))
    body = [ln for ln in text.splitlines() if not ln.startswith("#")]
    assert body == ["alpha==2.0", "zlib==1.0"] and text.splitlines()[1].startswith("# 생성: 2026-10-04")


def test_mcp_config_does_not_pin_python_minor_version():
    """`.mcp.json` 이 AI 에게 도구를 연결하는 명령도 `py -3.14` 로 박으면 그 버전이 없는 PC 에서 AI 가 앱 도구를 전혀 못 쓴다."""
    servers = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert servers  # 설정을 실제로 읽었다
    all_args = [str(a) for cfg in servers.values() for a in cfg.get("args", [])]
    assert all_args  # 명령 인자를 실제로 읽었다(비어 있으면 아래 비교가 항상 통과해 버린다)
    pinned = [a for a in all_args if re.fullmatch(r"-3\.\d+", a)]
    assert pinned == []
