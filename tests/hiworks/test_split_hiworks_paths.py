"""도구 분리 1단계(hiworks) — hiworks_mail_router 가 루트 hiworks_mail_reader.py 를 찾는 경로가 저장소 루트 기준 그대로인지 고정한다."""

from __future__ import annotations

import inspect

from ai_orchestrator.connectors.hiworks import mail_router as r
from ai_orchestrator.paths import repo_root


def test_inbox_route_resolves_the_reader_from_the_repo_root():
    src = inspect.getsource(r.api_inbox)
    assert 'repo_root() / "hiworks_mail_reader.py"' in src
    assert (repo_root() / "hiworks_mail_reader.py").exists()
