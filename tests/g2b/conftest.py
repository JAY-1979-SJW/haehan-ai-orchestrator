"""tests/g2b/ 공통 — HAEHAN_AGENT_WS_ENABLED 를 이 폴더의 테스트 파일들이 import 하기 전에 고정.

core/agent_runtime/common/config.py:53 `WEBSOCKET_ENABLED = os.getenv("HAEHAN_AGENT_WS_ENABLED",
"false") == "true"` 가 import 시점에 이 env 를 읽어 모듈 상수로 고정한다 — ai_orchestrator.
browser_tool.* 를 import 하는 g2b 시험 파일들은 그 전에 이 값을 "false" 로 못박아야 한다.

재발방지 전수조사(run38015451820) 중 발견: 예전엔 각 시험 파일 최상단에서 직접
`os.environ.setdefault(...)` 를 했는데, 복원이 없어 수집되는 순간 세션 끝까지(다른 폴더
시험에까지) env 가 바뀐 채로 남았다. conftest.py 는 pytest 가 같은 폴더의 test_*.py 보다
먼저 import 하므로(수집 순서 보장), env 설정을 여기 한 곳으로 모으면 "import 전에 설정"
요건은 그대로 지키면서 각 파일에 중복으로 안 둬도 된다. `setdefault` 라 이미 설정된 값은
안 건드리고, 기본값("false")은 config.py 자체의 기본값과 같아 실질적으로 상태를 바꾸지
않는다(이미 "false"가 기본이던 동작을 그대로 못박을 뿐) — 그래도 한곳으로 모아 중복을
없애고 의도를 명시한다.
"""

import os

os.environ.setdefault("HAEHAN_AGENT_WS_ENABLED", "false")
