"""워크플로 공통 UTF-8 환경 — Windows 러너의 기본 인코딩(cp1252)에서 한국어 출력이 죽지 않게 한다.

배경(2026-10-07): 첫 앱 빌드(desktop-release run 37616567839)가 'PyInstaller — haehan-server' 단계에서
haehan-server.spec:186 의 한국어 print 로 UnicodeEncodeError('charmap')를 내며 실패했다. 파일마다 고치지 않고
워크플로 최상위 env 로 모든 python 단계를 UTF-8 로 맞춘다. 이 시험은 그 env 가 빠지지 않게 고정한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ["desktop-release.yml", "ci.yml"]


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", WORKFLOWS)
def test_workflow_top_level_env_forces_utf8(name):
    env = _load(name).get("env") or {}
    assert env.get("PYTHONUTF8") == "1", f"{name}: 최상위 env PYTHONUTF8 가 '1' 이어야 한다"
    assert env.get("PYTHONIOENCODING") == "utf-8", f"{name}: 최상위 env PYTHONIOENCODING 이 'utf-8' 이어야 한다"


@pytest.mark.parametrize("name", WORKFLOWS)
def test_no_job_overrides_the_encoding_env_away(name):
    """job·step 단위 env 가 이 값을 다른 인코딩으로 덮어쓰지 않는다."""
    wf = _load(name)
    for job_name, job in (wf.get("jobs") or {}).items():
        for scope, env in [(f"job {job_name}", job.get("env") or {})] + [
            (f"step {s.get('name', '?')}", s.get("env") or {}) for s in job.get("steps", [])
        ]:
            for key, want in (("PYTHONUTF8", "1"), ("PYTHONIOENCODING", "utf-8")):
                if key in env:
                    assert str(env[key]).lower() == want, f"{name} {scope}: {key}={env[key]!r} 로 덮어씀"


def test_the_spec_that_failed_prints_korean_so_the_env_is_needed():
    """근거 고정: 첫 빌드가 죽은 spec 은 실제로 한국어를 출력한다(UTF-8 환경 없이는 cp1252 에서 인코딩 오류)."""
    text = (ROOT / "haehan-server.spec").read_text(encoding="utf-8")
    korean_prints = [ln for ln in text.splitlines() if "print(" in ln and any("가" <= c <= "힣" for c in ln)]
    assert korean_prints, "spec 의 한국어 print 가 없어졌다면 이 시험과 워크플로 주석의 근거를 다시 확인할 것"
