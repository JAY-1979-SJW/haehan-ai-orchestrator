#!/usr/bin/env python3
"""
Stop 훅: AI 응답에서 금지 행동 패턴 감지 → exit(2)로 차단.
Claude Code가 응답을 완성하기 직전 실행됨.
"""

import contextlib
import json
import re
import sys
from pathlib import Path

# 훅 출력은 하네스가 UTF-8 로 읽는다. 파이프로 연결되면 파이썬 기본 인코딩이 cp949 라 한글이 깨져
# 사용자에게 안내 문구(예: /clear 안내)가 읽히지 않았다(2026-10-01).
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(Exception):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# stop_hook_active 시 무한루프 방지
data = {}
try:
    raw = sys.stdin.read()
    if raw.strip():
        data = json.loads(raw)
except Exception:  # noqa: BLE001 - stdin JSON 파싱 실패 시 무시하고 빈 dict로 계속 — 훅이 죽지 않고 통과하도록 하는 의도된 fail-open
    pass

if data.get("stop_hook_active"):
    sys.exit(0)

# ── 금지 패턴 ──────────────────────────────────────────────────────────────
FORBIDDEN: list[tuple[str, str]] = [
    (r"터미널에서\s*(실행|입력)", "터미널 직접 실행 요청"),
    (r"직접\s*(입력|실행|확인|진행)하", "직접 입력/실행 요청"),
    (r"수동으로\s*(진행|처리|실행|확인)", "수동 진행 요청"),
    (r"콘솔에서\s*직접", "콘솔 직접 확인 요청"),
    (r"오류\s*(내용|메시지)를?\s*(보여|알려)", "오류 내용 보고 요청"),
    (r"어떤\s*오류인지\s*(알려|확인해)", "오류 확인 요청"),
    (r"다음\s*명령(어|을)?\s*(을\s*)?(실행|입력)하", "명령어 직접 실행 요청"),
    (r"!\s*python\s+\S+.*입력", "! python 명령 입력 요청"),
    (r"(실행해|입력해)\s*주세요", "직접 실행 요청 문구"),
    (r"아래\s*(명령|커맨드)(를|을|어)?\s*(실행|입력)", "명령어 직접 실행 요청"),
]

# ── transcript 에서 마지막 assistant 메시지 추출 ──────────────────────────
transcript_path = data.get("transcript_path", "")
last_text = ""

if transcript_path and Path(transcript_path).exists():
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8", errors="replace").splitlines()
        # jsonl 형식: 각 줄이 JSON 객체
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("role") == "assistant":
                    content = obj.get("content", "")
                    if isinstance(content, list):
                        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                        last_text = " ".join(parts)
                    elif isinstance(content, str):
                        last_text = content
                    break
            except Exception:  # noqa: BLE001 - Stop 훅: AI 응답 텍스트에서 금지행동 패턴을 감지해 exit(2)로 차단 — stdin JSON 파싱 실패나 transcript 개별 줄 파싱 실패는 검사를 건너뛰고 통과시키는 의도된 fail-open(훅 진입점 패턴), 패턴이 실제로 매칭되면 여전히 차단됨
                continue
    except Exception:  # noqa: BLE001 - stdin JSON 파싱 실패 시 무시하고 빈 dict로 계속 — 훅이 죽지 않고 통과하도록 하는 의도된 fail-open
        pass

if not last_text:
    sys.exit(0)

# ── 패턴 매칭 ─────────────────────────────────────────────────────────────
hits = []
for pattern, label in FORBIDDEN:
    if re.search(pattern, last_text):
        hits.append(label)

if hits:
    print(f"[behavior_gate] ❌ 금지 행동 감지: {', '.join(hits)}", file=sys.stderr)
    print("[behavior_gate] CLAUDE.md 원칙: AI가 도구로 직접 수행해야 합니다. 응답을 수정하세요.", file=sys.stderr)
    sys.exit(2)

sys.exit(0)
