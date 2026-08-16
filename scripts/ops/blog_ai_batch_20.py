"""AI 블로그 20편 일괄 작성 (bigsun2024).

흐름:
  1. data/blog_topic_cache.json 로드 (없으면 빈 캐시 생성)
  2. Unsplash API로 AI 관련 이미지 수집 (주제별 3장)
  3. AIResponder로 주제 20개 생성 (캐시에 없는 것만)
  4. 각 주제: 제목+본문 생성 → 이미지 3장 다운로드 → BlogWriter로 발행
  5. 발행 성공 시 캐시 업데이트

실행:
  python scripts/ops/blog_ai_batch_20.py [--dry-run] [--count N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, ".")

from ai_orchestrator.config import get_local_data_dir
from scripts.logger import get_logger
from scripts.naver.automation.ai_responder import AIResponder

_log = get_logger(__name__)

CACHE_FILE = Path("data/blog_topic_cache.json")


def _img_dir():
    return get_local_data_dir() / "images" / "blog_ai_batch"


def _unsplash_key() -> str:
    import os

    return os.environ.get("UNSPLASH_ACCESS_KEY", "")


# AI 관련 Unsplash 검색 쿼리 — 20포스트 × 3장 = 60장 필요
# 12개 쿼리 × 5장 = 60장 확보 (포스트마다 완전히 다른 이미지 3장)
UNSPLASH_QUERIES = [
    ("artificial intelligence chip", "인공지능 칩"),
    ("machine learning neural network", "머신러닝"),
    ("robot automation technology", "로봇 자동화"),
    ("data science analytics dashboard", "데이터 사이언스"),
    ("chatbot digital assistant interface", "챗봇 인터페이스"),
    ("deep learning algorithm brain", "딥러닝"),
    ("future technology computer", "미래 기술"),
    ("programmer coding laptop", "코딩 개발"),
    ("digital transformation business", "디지털 전환"),
    ("cloud computing network", "클라우드 컴퓨팅"),
    ("smartphone AI app technology", "스마트폰 AI"),
    ("office productivity work technology", "업무 생산성"),
]

# AI 블로그 주제 풀 (AIResponder가 이 중에서 새로운 주제를 선택/확장)
TOPIC_SEED = [
    "ChatGPT 활용법 완벽 가이드",
    "AI가 바꾸는 직장 생활의 미래",
    "프롬프트 엔지니어링 핵심 기술",
    "AI 이미지 생성 도구 비교 (Midjourney vs DALL-E vs Stable Diffusion)",
    "생성형 AI로 업무 생산성 3배 높이기",
    "AI 코딩 도구 GitHub Copilot 실전 후기",
    "딥러닝이란 무엇인가 — 비개발자를 위한 쉬운 설명",
    "AI 시대 필수 디지털 리터러시",
    "LLM(대형언어모델) 원리와 활용",
    "AI 자동화로 반복 업무 제거하기",
    "ChatGPT API 활용 나만의 AI 비서 만들기",
    "AI 윤리와 저작권 — 알아야 할 기본 지식",
    "클로드(Claude) vs ChatGPT — 어떤 AI가 더 나을까",
    "AI 번역 도구 DeepL vs 파파고 vs ChatGPT 비교",
    "구글 Gemini AI 완벽 활용 가이드",
    "AI로 블로그 글 쓰기 — 실전 프롬프트 10가지",
    "소상공인을 위한 AI 마케팅 자동화",
    "AI 음성 합성 기술의 현재와 미래",
    "AI로 유튜브 영상 기획·제작하기",
    "노코드 AI 도구로 앱 만들기",
    "AI 검색 엔진 Perplexity 완벽 가이드",
    "RAG(검색 증강 생성) 기술이란",
    "AI 에이전트 시대 — 자율 AI의 등장",
    "국내 AI 스타트업 현황과 투자 트렌드",
    "AI 자막·번역 도구로 글로벌 콘텐츠 만들기",
    "오픈소스 AI 모델 활용 — Llama, Mistral 입문",
    "AI 헬스케어 — 의료 분야 인공지능 활용",
    "AI로 PPT 발표 자료 만들기",
    "직장인 ChatGPT 업무 활용 10가지 방법",
    "AI 시대 필요한 새로운 직업과 역할",
]


# ── 캐시 관리 ─────────────────────────────────────────────────────────────


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"topics": [], "posted": []}


def save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def topic_key(title: str) -> str:
    return hashlib.md5(title.strip().lower().encode()).hexdigest()[:12]


def is_duplicate(title: str, cache: dict) -> bool:
    key = topic_key(title)
    used_keys = {p.get("key") for p in cache.get("posted", [])}
    used_titles = {p.get("title", "").strip().lower() for p in cache.get("posted", [])}
    return key in used_keys or title.strip().lower() in used_titles


# ── Unsplash 이미지 수집 ──────────────────────────────────────────────────


def fetch_unsplash_images(count_per_query: int = 5) -> list[dict]:
    images = []
    for q_en, q_ko in UNSPLASH_QUERIES:
        try:
            r = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": q_en, "per_page": count_per_query, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {_unsplash_key()}"},
                timeout=10,
            )
            if r.status_code == 200:
                for ph in r.json().get("results", []):
                    images.append(
                        {
                            "query": q_ko,
                            "url": ph["urls"]["regular"],
                            "small": ph["urls"]["small"],
                            "desc": (ph.get("description") or ph.get("alt_description") or "AI")[:60],
                            "author": ph["user"]["name"],
                            "download_location": ph["links"]["download_location"],
                        }
                    )
            else:
                _log.warning("Unsplash %s: %s", q_en, r.status_code)
        except Exception as e:
            _log.warning("Unsplash fetch error: %s", e)
        time.sleep(0.3)
    return images


def download_image(url: str, filename: str) -> str | None:
    img_dir = _img_dir()
    img_dir.mkdir(parents=True, exist_ok=True)
    path = img_dir / filename
    if path.exists():
        return str(path)
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "HaehanAI/1.0"})
        r.raise_for_status()
        path.write_bytes(r.content)
        return str(path)
    except Exception as e:
        _log.warning("이미지 다운로드 실패 %s: %s", url, e)
        return None


def pick_3_images(all_images: list[dict], idx: int) -> list[str]:
    """포스트 인덱스 기준으로 이미지 3장 선택.

    60장이면 포스트마다 완전히 다른 이미지(0~2, 3~5, ..., 57~59).
    이미지가 부족하면 순환 할당.
    """
    n = len(all_images)
    if n == 0:
        return []
    start = (idx * 3) % n
    selected = [all_images[(start + j) % n] for j in range(3)]
    paths = []
    for i, img in enumerate(selected):
        fn = f"post{idx:02d}_img{i + 1}_{topic_key(img['url'])}.jpg"
        path = download_image(img["url"], fn)
        if path:
            paths.append(path)
        # Unsplash 다운로드 트리거 (정책 준수)
        try:
            requests.get(
                img["download_location"],
                headers={"Authorization": f"Client-ID {_unsplash_key()}"},
                timeout=5,
            )
        except Exception:
            pass
        time.sleep(0.2)
    return paths


# ── AI 주제 생성 ──────────────────────────────────────────────────────────


def generate_topics(cache: dict, count: int, dry_run: bool = False) -> list[dict]:
    """캐시에 없는 AI 주제 count개 생성."""
    ai = AIResponder()
    used_titles = [p.get("title", "") for p in cache.get("posted", [])]
    used_str = "\n".join(f"- {t}" for t in used_titles[-50:]) if used_titles else "(없음)"

    prompt = f"""당신은 한국 네이버 블로그 AI 전문 작가입니다.
아래 이미 사용한 주제와 겹치지 않는 AI 관련 블로그 주제 {count}개를 생성하세요.

[이미 사용한 주제]
{used_str}

[참고 주제 풀]
{chr(10).join("- " + t for t in TOPIC_SEED)}

출력 형식 (JSON 배열, 다른 텍스트 없이):
[
  {{"topic": "주제명", "keywords": ["키워드1", "키워드2", "키워드3"], "angle": "독특한 접근 각도"}},
  ...
]

조건:
- AI, 인공지능, 자동화, 머신러닝, LLM, ChatGPT, 생성형AI 관련
- 주제가 서로 겹치지 않게
- 한국 독자 대상, 실용적·정보성 주제
- 이미 사용한 주제와 유사한 것도 제외"""

    if dry_run:
        print("\n[DRY-RUN] AI 주제 생성 프롬프트 (실제 API 미호출)")
        print(f"  생성 요청 수: {count}개")
        print(f"  기존 캐시 주제 수: {len(used_titles)}개")
        # 드라이런: TOPIC_SEED에서 미사용 주제 반환
        result = []
        for t in TOPIC_SEED:
            if not is_duplicate(t, cache) and len(result) < count:
                result.append({"topic": t, "keywords": ["AI", "인공지능", "자동화"], "angle": "실용 가이드"})
        return result

    r = ai._call(
        "한국 블로그 AI 주제 생성 전문가",
        prompt,
        max_tokens=2000,
    )
    if not r.get("ok"):
        _log.error("주제 생성 실패: %s", r)
        return []

    text = r["text"].strip()
    # JSON 추출
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        _log.error("JSON 파싱 실패: %s", text[:200])
        return []

    try:
        topics = json.loads(text[start:end])
    except Exception as e:
        _log.error("JSON 파싱 오류: %s | %s", e, text[start:end][:200])
        return []

    # 중복 필터
    filtered = [t for t in topics if not is_duplicate(t.get("topic", ""), cache)]
    return filtered[:count]


# ── AI 본문 생성 ──────────────────────────────────────────────────────────


def generate_post(topic_info: dict, dry_run: bool = False) -> dict | None:
    topic = topic_info["topic"]
    keywords = topic_info.get("keywords", [])
    angle = topic_info.get("angle", "실용 가이드")

    if dry_run:
        title = f"[AI 가이드] {topic} — 실전 완벽 정리"
        body = f"""안녕하세요! 오늘은 '{topic}'에 대해 깊이 있게 알아보겠습니다.

## {topic}란?

{topic}은(는) 현대 AI 기술의 핵심 분야 중 하나입니다. {angle}의 관점에서 살펴보겠습니다.

## 핵심 개념 이해

키워드: {", ".join(keywords)}

실제 현장에서 어떻게 활용되는지, 그리고 우리 일상에 어떤 영향을 미치는지 구체적인 사례를 통해 알아봅니다.

## 실전 활용 방법

1. 기초 개념 파악부터 시작하세요
2. 실제 도구를 직접 체험해 보세요
3. 내 업무/생활에 적용할 포인트를 찾으세요

## 마무리

오늘 다룬 '{topic}' 내용이 도움이 되셨길 바랍니다.
앞으로도 AI 관련 실용 정보를 꾸준히 공유하겠습니다. 구독과 공감 부탁드려요!

#AI #인공지능 #{keywords[0] if keywords else "AI활용"}"""
        return {"title": title, "body": body, "tags": keywords[:7]}

    ai = AIResponder()

    # 제목
    title_r = ai._call(
        "한국 블로그 SEO 전문가. 클릭률 높은 제목 1개만 출력.",
        f"주제: {topic}\n각도: {angle}\n키워드: {', '.join(keywords)}\n조건: 30~50자, 숫자/이모지 적절 활용\n제목:",
        max_tokens=80,
    )
    if not title_r.get("ok"):
        return None
    title = title_r["text"].split("\n")[0].strip().strip('"').strip("'")

    # 본문 (2500~3500자)
    body_prompt = f"""주제: {topic}
각도: {angle}
키워드: {", ".join(keywords)}
대상: 한국 일반 직장인·블로거·소상공인

아래 구조로 실용적인 블로그 본문을 작성하세요 (총 2500자 이상):
1. 도입부 — 독자가 공감할 상황/문제 제시 (300자)
2. 핵심 개념 설명 — 쉽고 명확하게 (600자)
3. 실전 활용법 — 구체적 방법 3~5가지 번호 목록 (800자)
4. 장점·주의사항 비교 (400자)
5. 실제 사례 또는 팁 (400자)
6. 마무리 — 행동 촉구 + 구독 유도 (200자)

본문만 출력 (제목 제외):"""

    body_r = ai._call(
        "한국 블로그 전문 작가. 실용적이고 읽기 쉬운 글 작성.",
        body_prompt,
        max_tokens=3000,
    )
    if not body_r.get("ok"):
        return None

    body = body_r["text"].strip()
    tags = keywords[:7] if keywords else ["AI", "인공지능"]
    segments = _split_body(body, parts=3)

    return {"title": title, "body": body, "body_segments": segments, "tags": tags}


def _split_body(body: str, parts: int = 3) -> list[str]:
    """본문을 단락(빈 줄) 기준으로 parts 등분.

    이미지를 글 중간에 끼우기 위해 사용.
    단락이 부족하면 글자 수 기준으로 균등 분할.
    """
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if len(paragraphs) < parts:
        # 단락이 적으면 글자 수 기준 분할
        chunk = max(1, len(body) // parts)
        return [body[i * chunk : (i + 1) * chunk].strip() for i in range(parts)]

    per = len(paragraphs) // parts
    segments = []
    for i in range(parts):
        start = i * per
        end = (i + 1) * per if i < parts - 1 else len(paragraphs)
        segments.append("\n\n".join(paragraphs[start:end]))
    return segments


# ── 메인 실행 ─────────────────────────────────────────────────────────────


def run(count: int = 20, dry_run: bool = False) -> None:
    print(f"\n{'=' * 60}")
    print(f"  블로그 AI 일괄 작성 {'[DRY-RUN]' if dry_run else '[실행]'}")
    print(f"  대상 계정: bigsun2024  |  목표: {count}편")
    print(f"{'=' * 60}\n")

    # 1. 캐시 로드
    cache = load_cache()
    print(f"[캐시] 기존 발행 주제: {len(cache.get('posted', []))}개")

    # 2. 이미지 수집
    print("\n[이미지] Unsplash 수집 중...")
    if dry_run:
        print("  [DRY-RUN] Unsplash API 호출 스킵 — 기존 images 사용")
        all_images = []
        existing = Path("data/unsplash_images.json")
        if existing.exists():
            all_images = json.loads(existing.read_text(encoding="utf-8")).get("images", [])
        print(f"  기존 이미지: {len(all_images)}개")
    else:
        all_images = fetch_unsplash_images(count_per_query=5)
        print(f"  수집 완료: {len(all_images)}개")

    if len(all_images) < 3 and not dry_run:
        print("  경고: 이미지 부족. 기존 파일 보충...")
        existing = Path("data/unsplash_images.json")
        if existing.exists():
            all_images += json.loads(existing.read_text(encoding="utf-8")).get("images", [])

    # 3. 주제 생성
    print(f"\n[주제] AI 생성 중 ({count}개)...")
    topics = generate_topics(cache, count, dry_run=dry_run)
    print(f"  생성된 주제: {len(topics)}개")
    for i, t in enumerate(topics):
        print(f"  {i + 1:2d}. {t['topic']}")

    if not topics:
        print("주제 생성 실패. 종료.")
        return

    # 4. CDP 연결 (dry-run 제외)
    page = None
    browser = None
    if not dry_run:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        print(f"\n[CDP] 연결됨: {page.url}")

        # bigsun2024 로그인 확인
        from scripts.login_detector import detect_login_state

        page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        state = detect_login_state(page)
        current_user = state.get("user", "")
        print(f"[로그인] 현재 계정: {current_user}")

        if current_user != "bigsun2024":
            print(f"  → bigsun2024 재로그인 필요 (현재: {current_user})")
            from scripts.credentials import get_cred
            from scripts.naver.auth import login_naver

            cred = get_cred("naver")
            # 다른 사용자가 로그인 중이면 먼저 로그아웃  # session-ok
            if current_user:
                print("  → 현재 사용자 로그아웃 중...")
                page.goto(
                    "https://nid.naver.com/nidlogin.logout",  # session-ok
                    wait_until="domcontentloaded",
                    timeout=15000,  # session-ok
                )
                time.sleep(3)
                page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)
            # bigsun2024 비번은 credentials에서 로드, force_relogin으로 상태 체크 우회
            r = login_naver(page, naver_id="bigsun2024", naver_pw=cred.get("pw", ""), force_relogin=True)
            if not r.get("ok"):
                print(f"  로그인 실패: {r}")
                browser.close()
                pw.stop()
                return
            time.sleep(3)

    # 5. 포스트 작성 루프
    results = []
    for idx, topic_info in enumerate(topics[:count]):
        topic = topic_info["topic"]
        print(f"\n[{idx + 1}/{len(topics[:count])}] {topic}")
        print(f"  키워드: {topic_info.get('keywords', [])}")

        # 본문 생성
        post = generate_post(topic_info, dry_run=dry_run)
        if not post:
            print("  본문 생성 실패 — 건너뜀")
            results.append({"topic": topic, "ok": False, "reason": "content_gen_failed"})
            continue

        segs = post.get("body_segments", [])
        print(f"  제목: {post['title']}")
        print(f"  본문: {len(post['body'])}자 ({len(segs)}구간)  태그: {post['tags']}")

        # 이미지 3장 선택/다운로드
        if dry_run:
            img_paths = [f"[DRY] image{j + 1}.jpg" for j in range(3)]
        else:
            img_paths = pick_3_images(all_images, idx)
        print(f"  이미지: {len(img_paths)}장 — {[Path(p).name for p in img_paths]}")

        if dry_run:
            print("  [DRY-RUN] 발행 스킵")
            results.append(
                {
                    "topic": topic,
                    "title": post["title"],
                    "ok": True,
                    "dry_run": True,
                    "images": img_paths,
                    "body_len": len(post["body"]),
                }
            )
            # 캐시 드라이런 업데이트 (실제 파일은 안 씀)
            continue

        # BlogWriter로 발행 — body_segments + images 로 이미지를 글 중간에 배치
        from scripts.naver.blog.core.writer import write_post

        segments = post.get("body_segments") or []
        try:
            result = write_post(
                page,
                title=post["title"],
                body=post["body"],
                body_segments=segments if segments else None,
                tags=post["tags"],
                images=img_paths,
                visibility="public",
                require_approval=False,
            )
            ok = result.get("ok", False)
            log_no = result.get("log_no", "")
            print(f"  발행: {'✅ 성공' if ok else '❌ 실패'} log_no={log_no}")
        except Exception as e:
            ok = False
            log_no = ""
            print(f"  발행 오류: {e}")

        results.append(
            {
                "topic": topic,
                "title": post["title"],
                "ok": ok,
                "log_no": log_no,
                "posted_at": datetime.now().isoformat(),
                "images": img_paths,
            }
        )

        # 성공 시 캐시 업데이트
        if ok:
            entry = {
                "key": topic_key(post["title"]),
                "topic": topic,
                "title": post["title"],
                "tags": post["tags"],
                "log_no": log_no,
                "posted_at": datetime.now().isoformat(),
            }
            cache.setdefault("posted", []).append(entry)
            save_cache(cache)
            print(f"  캐시 저장 ({len(cache['posted'])}개 누적)")

        # 포스트 간 대기 (봇 감지 방지)
        if idx < len(topics[:count]) - 1:
            wait = 90
            print(f"  다음 포스트 대기 {wait}초...")
            time.sleep(wait)

    # 6. 결과 요약
    print(f"\n{'=' * 60}")
    print(f"  완료 요약 ({'DRY-RUN' if dry_run else '실제 발행'})")
    print(f"{'=' * 60}")
    success = sum(1 for r in results if r.get("ok"))
    print(f"  성공: {success}/{len(results)}")
    for r in results:
        status = "✅" if r.get("ok") else "❌"
        tag = " [DRY]" if r.get("dry_run") else ""
        print(f"  {status} {r.get('title', r.get('topic', '?'))[:50]}{tag}")

    if not dry_run:
        browser.close()
        pw.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="실제 발행 없이 시뮬레이션")
    parser.add_argument("--count", type=int, default=20, help="작성할 포스트 수")
    args = parser.parse_args()
    run(count=args.count, dry_run=args.dry_run)
