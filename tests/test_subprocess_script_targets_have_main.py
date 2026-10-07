"""subprocess 로 `scripts/browser/<x>.py` 를 직접 실행하는 곳은 그 파일에 `__main__` 이 있어야 한다.

결함: cdp_client.py 는 라이브러리로 분리돼(S1-c) `__main__` 이 없는데, local_agent·cdp_daemon·gongmu 가 이를 스크립트로 실행해
아무 일도 하지 않고(종료 코드 0) 끝났다. 실행 진입부는 cdp_cli.py 다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALLERS = [
    "local_agent/actions.py",
    "scripts/browser/cdp/cdp_daemon.py",
    "ai_orchestrator/gongmu/fetch_nts_interpretations.py",
    "ai_orchestrator/gongmu/fetch_tax_precedent_summary.py",
]
_TARGET = re.compile(r'(?:scripts/browser/|"browser"\s*/\s*")(\w+)\.py')


def test_script_targets_launched_by_subprocess_have_a_main():
    problems = []
    for rel in CALLERS:
        for name in sorted(set(_TARGET.findall((ROOT / rel).read_text(encoding="utf-8")))):
            target = ROOT / "scripts" / "browser" / f"{name}.py"
            if not target.is_file() or '__name__ == "__main__"' not in target.read_text(encoding="utf-8"):
                problems.append(f"{rel} → scripts/browser/{name}.py (실행부 없음)")
    assert not problems, problems
