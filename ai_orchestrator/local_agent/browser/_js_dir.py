"""엔진 JS 자산(`_js/`) 위치의 단일 정본 (T4 C1).

믹스인(`browser/mixins/*.py`)과 `scripts/naver/cafe/collection/{cafe_scraper,
cafe_attachments}.py`가 각자 `Path(__file__)` 상대 계산으로 이 디렉터리를 찾고 있었다.
믹스인이 도구 집으로(C12a), 엔진이 `scripts/browser/agent/`로(C12b) 서로 다른 시점에
옮겨지면 그 상대 계산들이 다 깨진다 — 이 상수 하나로 통일해, 나중에 엔진이 옮겨질 때
여기 한 줄만 고치면 된다.

지금 값과 완전히 동일(ai_orchestrator/local_agent/browser/_js).
"""

from __future__ import annotations

from ai_orchestrator.paths import repo_root

JS_DIR = repo_root() / "ai_orchestrator" / "local_agent" / "browser" / "_js"
