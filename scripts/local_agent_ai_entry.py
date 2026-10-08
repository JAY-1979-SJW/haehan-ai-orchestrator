"""데스크톱 번들(PyInstaller local-agent-ai) 진입점 — AI 작업 콘솔용 로컬 에이전트(local_agent.agent).

PyInstaller 는 진입 파일을 패키지 밖 단독 스크립트로 실행하므로 `local_agent/agent.py`(상대 import 사용)를
그대로 진입점으로 쓸 수 없다(`attempted relative import with no known parent package`). 이 파일은 상대 import
없이 패키지 경로로 불러 실행한다. `python -m local_agent.agent` 와 인자·동작이 같다.

부모 감시: 앱(Electron)이 환경변수 HAEHAN_PARENT_PID 로 넘긴 부모 PID 가 사라지면 스스로 종료한다
(서버 진입점 desktop_entry 와 같은 도우미 재사용) — 강제 종료·크래시 때 고아 에이전트가 남지 않게.

scripts/local_agent.py(스마트스토어 전용 옛 에이전트, local-agent.exe)와는 별개 프로그램이다.
"""

import contextlib
import sys

# PyInstaller 번들 exe 는 stdout/stderr 가 파이프로 리다이렉트될 때 콘솔 코드페이지(cp949 등)로
# 떨어져 로그 파일(local-agent-ai.log)의 한글이 깨진다(scripts/local_agent.py 의 같은 사고와 동일
# 원인 — PYTHONIOENCODING/PYTHONUTF8 환경변수가 frozen exe 까지 전달되지 않는 경우에도 안전하도록
# 코드에서 직접 강제). best-effort — 실패해도 에이전트 기동 자체는 막지 않는다.
with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
with contextlib.suppress(Exception):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

from ai_orchestrator.server.desktop_entry import start_parent_watchdog
from local_agent import agent


def main() -> int:
    start_parent_watchdog()
    return agent.main()


if __name__ == "__main__":
    sys.exit(main())
