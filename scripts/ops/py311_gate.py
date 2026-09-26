# module_category: audit
# primary_trade: common
"""Python 3.11(운영 Dockerfile 과 동일) 검증 게이트(기준서 G1).

3.11 인터프리터가 없으면 조용히 통과하지 않고 '미검증'을 반환한다.
검사: 바뀐 .py py_compile / route_check import 스모크 / configs/verify_change.json 의 py311_tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

UNVERIFIED = "미검증(3.11 인터프리터 없음)"


def find_py311() -> list[str] | None:
    for cmd in (["py", "-3.11"], ["python3.11"]):
        try:
            r = subprocess.run(
                [*cmd, "-c", "import sys;print(sys.version_info[:2]==(3,11))"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and r.stdout.strip() == "True":
            return cmd
    return None


def run_gate(tree: Path, changed_py: list[str], route_check: str = "", tests: list[str] | None = None) -> list[str]:
    """새 문제 목록 반환. 3.11 없으면 [UNVERIFIED] 한 줄(FAIL 로 취급되어 보고서에 표시)."""
    py = find_py311()
    if py is None:
        return [UNVERIFIED]
    probs: list[str] = []
    for f in changed_py:
        if (tree / f).exists():
            r = subprocess.run([*py, "-m", "py_compile", f], cwd=str(tree), capture_output=True, text=True)
            if r.returncode:
                probs.append(f"py_compile {f}: {(r.stderr or '').strip()[-200:]}")
    env = {**os.environ, "AUTH_ENABLED": "false", "HAEHAN_NO_BROWSER_LAUNCH": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    if route_check:
        r = subprocess.run(
            [*py, "-c", route_check], cwd=str(tree), capture_output=True, text=True, timeout=600, env=env
        )
        if r.returncode:
            probs.append(f"import 스모크 실패: {(r.stderr or '').strip()[-200:]}")
    if tests:
        r = subprocess.run(
            [*py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
            cwd=str(tree),
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        if r.returncode:
            probs.append(f"py311 테스트 실패: {r.stdout.strip()[-200:]}")
    return probs


def main() -> int:
    root = Path.cwd()
    cfg: dict = {}
    p = root / "configs" / "verify_change.json"
    if p.exists():
        cfg = json.loads(p.read_text(encoding="utf-8"))
    probs = run_gate(root, sys.argv[1:], cfg.get("route_check", ""), cfg.get("py311_tests", []))
    print("\n".join(probs) or "py311 OK")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
