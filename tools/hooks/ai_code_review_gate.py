"""Claude Code AI 코드 검수 게이트 (pre-push).

[LLM 경계] 개발/터미널 도구 — 앱 런타임 아님. git 훅에서 Claude Code CLI 사용은
의도된 경계(터미널=Claude Code). 앱 기능 LLM 은 GPT(ai_orchestrator.llm.app_llm) 전용.

git push 직전에 origin/master 대비 변경 diff를 Claude Code CLI로 리뷰한다.
VERDICT: BLOCK 이 나오면 push를 차단한다.

실행:
  python tools/hooks/ai_code_review_gate.py

환경:
  AI_REVIEW_ENABLED=false  → 검수 건너뜀 (기본 true)
  AI_REVIEW_MODEL=haiku    → haiku(기본) / sonnet / opus
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
REPORT_PATH = ROOT / "data" / "runtime" / "ai_review_latest.json"

PROMPT_TEMPLATE = """당신은 시니어 시큐리티 코드 리뷰어입니다.
아래 git diff를 검토하고 다음 항목만 판단하세요:

검사 항목:
1. 명백한 버그 (NullPointer, 오프바이원, 타입 불일치 등)
2. 보안 취약점 (secret 노출, SQL 인젝션, SSRF, hardcoded credential 등)
3. 레이어 위반 (router에 SQL, UI에 업무 산식 등)
4. 운영 위험 (DB drop/truncate, 인증 우회, 데이터 삭제 등)

판정 규칙:
- 위 항목 중 하나라도 발견되면: VERDICT: BLOCK
- 발견 없으면: VERDICT: PASS
- 스타일·주석·리팩터·성능 제안은 무시
- 판정 외 설명은 간결하게 (3줄 이내)

응답 형식:
VERDICT: PASS 또는 VERDICT: BLOCK
[발견된 경우] 문제: <파일명:줄> <한줄 설명>

--- DIFF START ---
{diff}
--- DIFF END ---"""


def _enabled() -> bool:
    return os.environ.get("AI_REVIEW_ENABLED", "true").lower() not in {"false", "0", "no"}


def _model_flag() -> list[str]:
    model = os.environ.get("AI_REVIEW_MODEL", "haiku").lower()
    model_map = {
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-8",
    }
    return ["--model", model_map.get(model, model_map["haiku"])]


def get_diff() -> str:
    """origin/master 대비 현재 HEAD까지의 diff를 반환한다."""
    # push 예정 커밋 diff
    try:
        result = subprocess.run(
            ["git", "diff", "origin/master..HEAD", "--", "*.py"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # Windows 기본 코드페이지(cp949)가 UTF-8 diff에서 깨지는 문제 방지(2026-09-28)
            timeout=30,
        )
        diff = result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        diff = ""

    if not diff:
        # staged 변경으로 폴백
        result = subprocess.run(
            ["git", "diff", "--cached", "--", "*.py"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        diff = result.stdout.strip()

    return diff


def run_review(diff: str) -> dict:
    """Claude Code CLI로 diff를 리뷰하고 결과를 반환한다."""
    if not diff:
        return {"verdict": "PASS", "reason": "no_python_changes", "skipped": True}

    # diff가 너무 크면 앞부분만 사용 (컨텍스트 제한)
    max_diff_chars = 40_000
    truncated = len(diff) > max_diff_chars
    if truncated:
        diff = diff[:max_diff_chars] + "\n... (truncated)"

    prompt = PROMPT_TEMPLATE.format(diff=diff)

    cmd = ["claude", "-p", prompt, *_model_flag()]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        output = result.stdout.strip()
    except FileNotFoundError:
        # claude CLI 없으면 건너뜀
        return {"verdict": "PASS", "reason": "claude_cli_not_found", "skipped": True}
    except subprocess.TimeoutExpired:
        return {"verdict": "PASS", "reason": "review_timeout", "skipped": True}

    verdict = "PASS"
    if "VERDICT: BLOCK" in output:
        verdict = "BLOCK"

    return {
        "verdict": verdict,
        "output": output,
        "truncated": truncated,
        "skipped": False,
    }


def save_report(payload: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload["created_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    payload["secret_values_output"] = False
    REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    # Windows 콘솔 기본 코드페이지(cp949)가 이모지·em-dash 등 출력을 못 받아 죽는 문제 방지
    # (2026-09-28 발견 — git push 시 pre-push 훅에서 이 스크립트가 크래시함)
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8")

    if not _enabled():
        # 2026-09-30 수정(defect_index #5): 예전엔 콘솔 출력만 하고 아무 흔적도 안 남겨서
        # "누가 언제 왜 껐는지" 사후 확인이 불가능했다. 강제 사유 입력(대화형 프롬프트)은
        # 비대화형 자동화 push에서 항상 막힐 위험이 있어 요구하지 않되, 최소한 우회 사실
        # 자체를 리포트 파일에 남겨 조용한 우회는 막는다 — 사유는 선택적 환경변수
        # AI_REVIEW_BYPASS_REASON 으로 남길 수 있게(안 남기면 "(사유 미기록)"으로 기록).
        reason = os.environ.get("AI_REVIEW_BYPASS_REASON", "").strip() or "(사유 미기록)"
        print(f"[ai-review] AI_REVIEW_ENABLED=false — 검수 건너뜀 (사유: {reason})")
        save_report({"verdict": "SKIPPED", "reason": "ai_review_disabled", "bypass_reason": reason})
        return 0

    print("[ai-review] diff 추출 중...")
    diff = get_diff()
    if not diff:
        print("[ai-review] Python 변경 없음 — PASS")
        save_report({"verdict": "PASS", "reason": "no_python_changes"})
        return 0

    lines = diff.count("\n")
    print(f"[ai-review] Claude Code로 검수 중... ({lines}줄 diff)")
    result = run_review(diff)
    save_report(result)

    verdict = result.get("verdict", "PASS")
    if result.get("skipped"):
        print(f"[ai-review] 건너뜀: {result.get('reason')} — PASS")
        return 0

    if result.get("truncated"):
        print("[ai-review] 경고: diff가 커서 앞부분만 검수됨")

    output = result.get("output", "")
    if verdict == "BLOCK":
        print("\n[ai-review] ⛔ BLOCK — 아래 문제를 수정 후 재push하세요:\n")
        print(output)
        print(f"\n리뷰 전체 결과: {REPORT_PATH}")
        return 1

    print(f"[ai-review] ✅ PASS\n{output[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
