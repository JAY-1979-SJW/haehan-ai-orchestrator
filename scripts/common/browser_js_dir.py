"""엔진 JS 자산(`_js/`) 위치의 단일 정본 (T4 C1).

믹스인(`browser/mixins/*.py`)과 `scripts/naver/cafe/collection/{cafe_scraper,
cafe_attachments}.py`가 각자 `Path(__file__)` 상대 계산으로 이 디렉터리를 찾고 있었다.
믹스인이 도구 집으로(C12a), 엔진이 `scripts/browser/agent/`로(C12b) 서로 다른 시점에
옮겨지면 그 상대 계산들이 다 깨진다 — 이 상수 하나로 통일했고, C12b 에서 엔진과 함께
이 한 줄만 새 위치로 바꿨다(이동 전 값: ai_orchestrator/local_agent/browser/_js).

엔진(scripts/browser/agent)과 사이트 믹스인(scripts/naver/*)이 서로를 import 하지 않도록(엔진 ↔ 믹스인 순환 방지, T4 C12) 공용 위치(scripts/common)에 둔다.
"""

from __future__ import annotations

from ai_orchestrator.paths import repo_root

JS_DIR = repo_root() / "scripts" / "browser" / "agent" / "_js"
