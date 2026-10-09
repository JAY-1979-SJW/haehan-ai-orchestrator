"""APP_LLM_BOUNDARY — 앱 런타임은 유료 AI API 0(2026-09-24 OpenAI 삭제), AI는 Claude Code가 MCP로.

원칙(아키텍처 경계):
  • 앱 런타임(ai_orchestrator·scripts/naver·community)은 더 이상 유료 AI API를
    호출하지 않는다(``ai_orchestrator.llm.app_llm.APP_LLM_PROVIDER == "none"``).
  • 판단·글쓰기·에이전트 작업은 Claude Code 가 MCP(``ai_orchestrator/server/mcp_server.py``)로
    앱에 붙어서 수행한다 — 이 경로는 앱 런타임 프로세스 밖이므로 경계 대상이 아니다.
  • Claude(Anthropic) 직접 호출은 '경계 허용목록'에서만 — provider 명시 opt-in, 레거시 데드모듈.

이 테스트는 경계 밖 Anthropic 직접호출을 영구 차단하고(회귀 방지), 앱 런타임에
유료 AI 공급자 상수가 남아있지 않은지 검증한다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 앱 런타임 스캔 대상 (ops/dev 도구·빌드·테스트는 제외)
SCAN_DIRS = ["ai_orchestrator", "scripts/naver", "scripts/community"]

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
    from ai_orchestrator.llm import app_llm

    assert app_llm.APP_LLM_PROVIDER == "none"


def test_no_openai_model_constants_in_app_runtime():
    """gpt-4/gpt-3 모델 리터럴이 앱 런타임에 남아있지 않은지(허용목록 제외) 검증."""
    pat = re.compile(r"gpt-[43]")
    offenders = []
    for p, rel in _iter_app_py():
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if pat.search(line):
                offenders.append(f"{rel}:{i}: {line.strip()[:90]}")
    assert not offenders, "앱 런타임에 GPT 모델 리터럴이 남아있음:\n" + "\n".join(offenders)
