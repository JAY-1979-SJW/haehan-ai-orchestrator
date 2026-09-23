"""APP_LLM_BOUNDARY — 앱 런타임은 GPT 전용, Claude(Anthropic 직접호출)는 경계에만.

원칙(아키텍처 경계):
  • 앱 런타임(ai_orchestrator·scripts/naver·community·browser_agent)의 모든
    AI 기능 = GPT(OpenAI). 모델명은 ai_orchestrator.app_llm 단일 출처에서 가져온다.
  • Claude(Anthropic) 직접 호출은 '경계 허용목록'에서만 — 터미널 Claude Code 연동
    (MCP 서버·git훅 리뷰·OpenAI부재 CLI폴백), provider 명시 opt-in, 레거시 데드모듈.

이 테스트는 경계 밖 Anthropic 직접호출을 영구 차단한다(회귀 방지).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 앱 런타임 스캔 대상 (ops/dev 도구·빌드·테스트는 제외)
SCAN_DIRS = ["ai_orchestrator", "scripts/naver", "scripts/community", "scripts/browser_agent"]

# Anthropic '실호출' 신호 — 도메인 허용목록 상수("api.anthropic.com")와 구분되는 패턴만.
CALL_PATTERNS = [
    re.compile(r"import anthropic\b"),
    re.compile(r"anthropic\.Anthropic\("),
    re.compile(r"anthropic-version"),  # raw HTTP 호출 헤더
    re.compile(r"\bclaude-(haiku|sonnet|opus)"),  # Claude 모델명
    re.compile(r"_call_claude\b"),
]

# 경계(Claude 허용) — 여기서만 Anthropic 가능
BOUNDARY_ALLOWLIST = {
    "scripts/naver/automation/integration/ai_responder.py",  # provider="anthropic" opt-in
    "scripts/naver/smartstore/product/ai_description_writer.py",  # 레거시 Claude writer(데드)
}

EXCLUDE_PARTS = {"__pycache__", "dist-build-tmp", "dist-build", "dist-electron", "dist-electron-new"}


def _iter_app_py():
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if any(part in EXCLUDE_PARTS for part in p.parts):
                continue
            rel = p.relative_to(ROOT).as_posix()
            if rel in BOUNDARY_ALLOWLIST:
                continue
            yield p, rel


def test_no_anthropic_calls_outside_boundary():
    offenders = []
    for p, rel in _iter_app_py():
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if line.lstrip().startswith("#"):  # 주석은 제외
                continue
            if any(pat.search(line) for pat in CALL_PATTERNS):
                offenders.append(f"{rel}:{i}: {line.strip()[:90]}")
    assert not offenders, "앱 런타임에 경계 밖 Anthropic 직접호출:\n" + "\n".join(offenders)


def test_app_llm_is_single_source():
    from ai_orchestrator import app_llm

    assert app_llm.APP_LLM_PROVIDER == "openai"
    assert app_llm.APP_LLM_MODEL.startswith("gpt")
    assert app_llm.APP_LLM_QUALITY_MODEL.startswith("gpt")


def test_app_features_reference_single_source():
    from ai_orchestrator import app_llm
    from ai_orchestrator.connectors.gabia.chat import GPT_MODEL as GABIA
    from ai_orchestrator.connectors.smartstore.chat import GPT_MODEL as SS
    from ai_orchestrator.openai_proxy_caller import DEFAULT_MODEL as PROXY

    assert SS == app_llm.APP_LLM_MODEL
    assert GABIA == app_llm.APP_LLM_MODEL
    assert PROXY == app_llm.APP_LLM_QUALITY_MODEL
