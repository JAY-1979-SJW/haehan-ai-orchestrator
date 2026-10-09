"""subprocess 로 `scripts/browser/<x>.py` 를 직접 실행하는 곳은 그 파일에 `__main__` 이 있어야 한다.

결함: cdp_client.py 는 라이브러리로 분리돼(S1-c) `__main__` 이 없는데, local_agent·cdp_daemon·gongmu 가 이를 스크립트로 실행해
아무 일도 하지 않고(종료 코드 0) 끝났다. 실행 진입부는 cdp_cli.py 다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALLERS = [
    "core/agent_runtime/connection/actions.py",
    "scripts/browser/cdp/cdp_daemon.py",
    "ai_orchestrator/gongmu/fetch_nts_interpretations.py",
    "ai_orchestrator/gongmu/fetch_tax_precedent_summary.py",
]
_TARGET = re.compile(r'(?:scripts/(browser|entry)/|"(browser|entry)"\s*/\s*")(\w+)\.py')


def test_script_targets_launched_by_subprocess_have_a_main():
    problems = []
    for rel in CALLERS:
        found = {(a or b, name) for a, b, name in _TARGET.findall((ROOT / rel).read_text(encoding="utf-8"))}
        assert found, f"{rel}: 실행 대상 스크립트 경로를 찾지 못했다(시험이 눈을 잃었다)"
        for folder, name in sorted(found):
            target = ROOT / "scripts" / folder / f"{name}.py"
            if not target.is_file() or '__name__ == "__main__"' not in target.read_text(encoding="utf-8"):
                problems.append(f"{rel} → scripts/{folder}/{name}.py (실행부 없음)")
    assert not problems, problems


def test_cdp_cli_runs_as_a_script_from_any_working_directory(tmp_path):
    """안내 문구가 `python scripts/entry/cdp_cli.py <명령>` 이므로 직접 실행도 scripts 패키지를 찾아야 한다(사용법 출력, 종료 코드 0)."""
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["HAEHAN_NO_BROWSER_LAUNCH"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"  # 한글 사용법을 파이프로 받으므로 출력 인코딩을 고정(이 시험의 관심사는 경로 해석)
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "entry" / "cdp_cli.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert r.returncode == 0, r.stderr[-500:]
    assert "CDP" in r.stdout
