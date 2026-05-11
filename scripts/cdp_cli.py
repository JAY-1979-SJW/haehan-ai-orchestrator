"""CDP 자연어 CLI — "드라이브에서 파일 검색해줘" → cdp_client 실행

구조:
  사용자 입력 (자연어)
       ↓
  Haiku가 의도 분석 (site/task/args 추출)
       ↓
  cdp_client.py 함수 실행
       ↓
  결과 출력
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


# ── AI 라우팅 ────────────────────────────────────────────────────

def _build_haiku_client() -> tuple:
    """Haiku 클라이언트 + API 키 확인."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY 환경변수 필수")
    from openai import OpenAI
    return OpenAI(api_key=openai_key), "gpt-4o-mini"


def _parse_intent(client, model: str, user_input: str) -> dict:
    """Haiku가 자연어를 site/task/args로 분석."""
    system = """당신은 CDP 브라우저 자동화 시스템의 의도 분석 엔진입니다.
사용자의 자연어 요청을 분석해 다음 JSON을 반환합니다 (JSON만, 다른 텍스트 없음):

{
  "site": "google|gmail|naver|g2b|gov24|hiworks|kakao",
  "task": "구체적 작업명 (예: drive, list, compose, search)",
  "args": ["인수1", "인수2"],
  "confidence": 0.0~1.0,
  "reason": "분석 결과 한 줄"
}

매핑 규칙 (Google):
파일:
- "드라이브 파일 목록" → {site: "google", task: "drive", args: ["list"]}
- "드라이브 파일 검색" → {site: "google", task: "drive", args: ["search", "검색어"]}
- "파일명 변경" → {site: "google", task: "drive", args: ["rename", "현재명", "새이름"]}
- "파일 삭제" → {site: "google", task: "drive", args: ["delete", "파일명"]}
- "파일 업로드" → {site: "google", task: "drive", args: ["upload", "파일경로"]}
- "파일 다운로드" → {site: "google", task: "drive", args: ["download", "파일명"]}

메일:
- "메일 목록" → {site: "google", task: "list", args: ["inbox|sent|drafts"]}
- "메일 발송" → {site: "google", task: "compose", args: ["수신자", "제목", "본문"]}

캘린더:
- "오늘 일정" → {site: "google", task: "calendar", args: ["today"]}
- "주간 일정" → {site: "google", task: "calendar", args: ["week"]}
- "일정 생성" → {site: "google", task: "calendar", args: ["create", "제목", "날짜"]}
- "일정 삭제" → {site: "google", task: "calendar", args: ["delete", "일정명"]}

문서:
- "구글 문서 목록" → {site: "google", task: "docs", args: ["recent"]}
- "새 문서" → {site: "google", task: "docs", args: ["new"]}
- "문서 검색" → {site: "google", task: "docs", args: ["search", "검색어"]}
- "문서 열기" → {site: "google", task: "docs", args: ["open", "문서명"]}
- "문서 삭제" → {site: "google", task: "docs", args: ["delete", "문서명"]}

시트:
- "구글 시트 목록" → {site: "google", task: "sheets", args: ["recent"]}
- "새 시트" → {site: "google", task: "sheets", args: ["new"]}
- "시트 검색" → {site: "google", task: "sheets", args: ["search", "검색어"]}
- "시트 열기" → {site: "google", task: "sheets", args: ["open", "시트명"]}
- "시트 삭제" → {site: "google", task: "sheets", args: ["delete", "시트명"]}
- "시트에 행 추가" → {site: "google", task: "sheets", args: ["insert", "시트명", "데이터1", "데이터2"]}
- "시트 셀 편집" → {site: "google", task: "sheets", args: ["edit", "시트명", "A1", "새값"]}

다른 서비스:
- "소방 공고 검색" → {site: "g2b", task: "search", args: ["소방"]}
- "네이버 검색" → {site: "naver", task: "search", args: ["검색어"]}

불확실하면 confidence 낮추고, 못 파악하면 confidence: 0.

JSON만 반환합니다.
"""

    response = client.chat.completions.create(
        model=model,
        max_tokens=300,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_input},
        ],
    )

    raw = response.choices[0].message.content.strip()
    # JSON 추출
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"AI 응답 파싱 실패: {raw[:200]}")


def _run_cdp_task(site: str, task: str, args: list[str]) -> str:
    """cdp_client.py 실행 (subprocess)."""
    cmd = [sys.executable, str(ROOT / "scripts" / "cdp_client.py"), site]
    if task:
        cmd.append(task)
    cmd.extend(str(a) for a in args)
    cmd.append("--no-wait")

    print(f"\n  💬 실행: {' '.join(cmd)}\n")

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(ROOT))
    output = (proc.stdout or "") + (proc.stderr or "")

    if proc.returncode != 0:
        return f"[오류] {output[-500:]}"
    return output.strip()


# ── CLI REPL ────────────────────────────────────────────────────

def main():
    """자연어 CLI REPL."""
    try:
        client, model = _build_haiku_client()
    except Exception as e:
        print(f"[오류] 초기화 실패: {e}")
        return

    print("\n" + "="*60)
    print("  CDP 자연어 CLI — Chrome 자동화")
    print("="*60)
    print("  지원 사이트: Google(Mail/Drive), Gmail, Naver, G2B, Gov24, HiWorks")
    print("  예: '드라이브에서 파일 목록 보여줘'")
    print("  종료: exit, quit, q")
    print("="*60 + "\n")

    while True:
        try:
            user_input = input("👤 > ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("  👋 종료")
                break

            # 1. AI 의도 분석
            print("\n  🤖 AI 분석 중...")
            try:
                intent = _parse_intent(client, model, user_input)
            except Exception as e:
                print(f"  [오류] 분석 실패: {e}")
                continue

            confidence = intent.get("confidence", 0)
            reason = intent.get("reason", "")

            if confidence < 0.5:
                print(f"  ⚠️  신뢰도 낮음 ({confidence:.0%}): {reason}")
                print(f"  분석: site={intent.get('site')}, task={intent.get('task')}")
                response = input("  계속할까요? (y/n): ").strip().lower()
                if response != "y":
                    continue

            site = intent.get("site", "").strip()
            task = intent.get("task", "").strip()
            args = [str(a).strip() for a in (intent.get("args") or []) if str(a).strip()]

            if not site:
                print("  [오류] 사이트를 파악할 수 없습니다")
                continue

            print(f"  ✅ {reason}")
            print(f"  📋 site={site}, task={task}, args={args}\n")

            # 2. CDP 실행
            print("  ⏳ 실행 중...\n")
            try:
                output = _run_cdp_task(site, task, args)
                print("\n" + "="*60)
                print("📊 결과:")
                print("="*60)
                print(output)
                print("="*60 + "\n")
            except subprocess.TimeoutExpired:
                print("  [오류] 타임아웃 (180초 초과)")
            except Exception as e:
                print(f"  [오류] 실행 실패: {e}")

        except KeyboardInterrupt:
            print("\n  👋 중단됨")
            break
        except Exception as e:
            print(f"  [오류] {e}")


if __name__ == "__main__":
    main()
