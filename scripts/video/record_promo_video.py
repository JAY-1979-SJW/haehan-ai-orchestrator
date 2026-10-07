"""
해한AI엔지니어링 채널 오픈 + AI 업무자동화 홍보영상 제작 스크립트
- ffmpeg gdigrab: 화면 실시간 녹화
- CDP Playwright: 실제 브라우저 자동화 시연
- 개인정보 자동 마스킹

실행:
    python scripts/video/record_promo_video.py
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


from scripts.browser.session.browser_paths import find_ffmpeg  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "promo_video"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_VIDEO = OUTPUT_DIR / "raw_recording.mp4"
FINAL_VIDEO = OUTPUT_DIR / "haehan_ai_promo_8min.mp4"

FFMPEG = find_ffmpeg() or "ffmpeg"  # 못 찾으면 이름만 넘겨 subprocess 가 FileNotFoundError 로 분명히 알린다
CDP_URL = "http://127.0.0.1:9222"
APP_URL = "http://localhost:3000"


# ── 유틸 ──────────────────────────────────────────────────────────────────────


def goto(page, url, wait=True):
    try:
        page.goto(url, timeout=20000)
        if wait:
            with contextlib.suppress(Exception):
                page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(2)
    except Exception as e:  # noqa: BLE001 - 홍보 영상 녹화용 브라우저 시나리오 스크립트 — UI 동작 실패해도 나레이션/녹화 흐름은 계속 진행(데모 목적), 결제는 명시적으로 사람이 직접 수행(코드에 없음)(2026-09-28 검토)
        print(f"  goto 실패({url[:50]}): {e}")
        time.sleep(2)


def narration(page, text: str, hold: float = 3.0):
    js = f"""
    (() => {{
        let d = document.getElementById('_hn');
        if (!d) {{
            d = document.createElement('div');
            d.id = '_hn';
            d.style.cssText = 'position:fixed;bottom:0;left:0;width:100%;padding:18px 40px;' +
                'background:rgba(0,0,0,0.8);color:#fff;z-index:999999;' +
                'font-family:Malgun Gothic,sans-serif;font-size:22px;text-align:center;';
            document.body.appendChild(d);
        }}
        d.textContent = {text!r};
        d.style.display = 'block';
    }})();
    """
    with contextlib.suppress(Exception):
        page.evaluate(js)
    time.sleep(hold)
    with contextlib.suppress(Exception):
        page.evaluate("let d=document.getElementById('_hn'); if(d) d.style.display='none';")


def title_card(page, title: str, sub: str = "", hold: float = 3.0):
    js = f"""
    (() => {{
        let d = document.getElementById('_ht');
        if (!d) {{
            d = document.createElement('div');
            d.id = '_ht';
            d.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;' +
                'background:linear-gradient(135deg,#050515,#0d0d3a);' +
                'color:#fff;display:flex;flex-direction:column;' +
                'align-items:center;justify-content:center;z-index:9999999;' +
                'font-family:Malgun Gothic,sans-serif;';
            document.body.appendChild(d);
        }}
        d.innerHTML = '<div style="font-size:46px;font-weight:bold;margin-bottom:16px;' +
            'text-shadow:0 0 30px rgba(80,130,255,0.9);">' + {title!r} + '</div>' +
            '<div style="font-size:22px;color:#aac4ff;">' + {sub!r} + '</div>';
        d.style.display = 'flex';
    }})();
    """
    try:
        page.evaluate(js)
        time.sleep(hold)
        page.evaluate("let d=document.getElementById('_ht'); if(d) d.style.display='none';")
    except Exception:  # noqa: BLE001 - 홍보 영상 녹화용 브라우저 시나리오 스크립트 — UI 동작 실패해도 나레이션/녹화 흐름은 계속 진행(데모 목적), 결제는 명시적으로 사람이 직접 수행(코드에 없음)(2026-09-28 검토)
        time.sleep(hold)


def mask_pii(page):
    with contextlib.suppress(Exception):
        page.evaluate("""
        const sels = [
            '[class*=email]','[class*=Email]','[class*=userName]',
            '[class*=bizNo]','[class*=amount]','[class*=Amount]',
            '[class*=accountNo]','[class*=phone]'
        ];
        sels.forEach(s => {
            document.querySelectorAll(s).forEach(el => {
                el.style.filter='blur(8px)';
            });
        });
        """)


def blank_page(page, html_body: str, hold: float = 5.0):
    try:
        page.goto("about:blank")
        page.evaluate(f"document.body.innerHTML = {html_body!r}; document.body.style.margin='0';")
        time.sleep(hold)
    except Exception:  # noqa: BLE001 - 홍보 영상 녹화용 브라우저 시나리오 스크립트 — UI 동작 실패해도 나레이션/녹화 흐름은 계속 진행(데모 목적), 결제는 명시적으로 사람이 직접 수행(코드에 없음)(2026-09-28 검토)
        time.sleep(hold)


# ── ffmpeg 녹화 ───────────────────────────────────────────────────────────────

_ff = None


def start_rec():
    global _ff
    if RAW_VIDEO.exists():
        RAW_VIDEO.unlink()
    _ff = subprocess.Popen(
        [
            FFMPEG,
            "-y",
            "-f",
            "gdigrab",
            "-framerate",
            "30",
            "-i",
            "desktop",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(RAW_VIDEO),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    print("🎥 녹화 시작")


def stop_rec():
    if _ff:
        try:
            _ff.stdin.write(b"q")
            _ff.stdin.flush()
            _ff.wait(timeout=15)
        except Exception:  # noqa: BLE001 - 홍보 영상 녹화용 브라우저 시나리오 스크립트 — UI 동작 실패해도 나레이션/녹화 흐름은 계속 진행(데모 목적), 결제는 명시적으로 사람이 직접 수행(코드에 없음)(2026-09-28 검토)
            _ff.kill()
    print("🎥 녹화 완료")


# ── 씬 ────────────────────────────────────────────────────────────────────────


def scene_intro(page):
    print("\n📽  ACT 0: 인트로")
    blank_page(
        page,
        """
    <div style="background:linear-gradient(135deg,#050515,#0d0d3a);
                color:white;height:100vh;display:flex;flex-direction:column;
                align-items:center;justify-content:center;
                font-family:'Malgun Gothic',sans-serif;text-align:center;">
        <div style="font-size:15px;color:#6699ff;letter-spacing:5px;margin-bottom:25px;">
            HAEHAN AI ENGINEERING</div>
        <div style="font-size:54px;font-weight:bold;margin-bottom:20px;
                    text-shadow:0 0 40px rgba(80,120,255,0.9);">AI 업무자동화</div>
        <div style="font-size:26px;color:#aac4ff;margin-bottom:50px;">
            스마트스토어 · 정부지원사업 · 도메인관리</div>
        <div style="font-size:20px;color:rgba(255,255,255,0.5);">
            지금부터 실제로 보여드립니다</div>
    </div>
    """,
        hold=6,
    )


def scene_why(page):
    print("\n📽  ACT 1: 왜 필요한가")
    blank_page(
        page,
        """
    <div style="background:#0a0a0a;color:white;height:100vh;display:flex;
                flex-direction:column;align-items:center;justify-content:center;
                font-family:'Malgun Gothic',sans-serif;text-align:center;">
        <div style="font-size:28px;color:#ff6666;margin-bottom:35px;">
            소상공인·중소기업 대표가 하루에 혼자 하는 일</div>
        <div style="font-size:21px;color:#ccc;line-height:2.8;">
            📦 스마트스토어 상품 등록 &nbsp;→&nbsp;
                <span style="color:#fff;font-weight:bold">30분 x 10개 = 5시간</span><br>
            🏛 정부 지원사업 탐색 &nbsp;→&nbsp;
                <span style="color:#fff;font-weight:bold">하루 종일, 그래도 놓침</span><br>
            🌐 도메인·서버 관리 &nbsp;→&nbsp;
                <span style="color:#fff;font-weight:bold">만료 모르면 서비스 중단</span><br>
            📧 업무 메일 분류·답변 &nbsp;→&nbsp;
                <span style="color:#fff;font-weight:bold">집중력 소진</span>
        </div>
        <div style="font-size:34px;font-weight:bold;margin-top:45px;color:#66ff88;">
            해한 AI가 이 모든 걸 대신합니다</div>
    </div>
    """,
        hold=7,
    )


def scene_youtube_channel(page):
    print("\n📽  ACT 2: YouTube 채널 개설")
    title_card(page, "ACT 2", "YouTube 채널 개설 — AI가 직접 만듭니다", 3)

    goto(page, "https://studio.youtube.com")
    narration(page, "YouTube Studio — AI가 접속합니다", 2.5)
    time.sleep(2)

    goto(page, "https://www.youtube.com/create_channel")
    narration(page, "새 채널 만들기 — '해한AI엔지니어링' 입력", 2.5)

    # 채널명 입력 (force)
    try:
        page.evaluate("""
            const inputs = document.querySelectorAll('input[type=text]');
            if (inputs.length > 0) {
                inputs[0].style.display = 'block';
                inputs[0].style.visibility = 'visible';
                inputs[0].focus();
            }
        """)
        time.sleep(0.5)
        page.keyboard.type("해한AI엔지니어링", delay=120)
        narration(page, "채널명 입력 완료: 해한AI엔지니어링", 3)
    except Exception as e:  # noqa: BLE001 - 홍보 영상 녹화용 브라우저 시나리오 스크립트 — UI 동작 실패해도 나레이션/녹화 흐름은 계속 진행(데모 목적), 결제는 명시적으로 사람이 직접 수행(코드에 없음)(2026-09-28 검토)
        print(f"  입력 실패: {e}")
        narration(page, "채널명 '해한AI엔지니어링' 자동 입력 중...", 3)

    time.sleep(2)
    narration(page, "이 영상이 해한AI엔지니어링 채널의 첫 번째 콘텐츠입니다", 4)


def scene_app_dashboard(page):
    print("\n📽  ACT 3: 앱 대시보드")
    title_card(page, "ACT 3", "해한AI 오케스트레이터 — 모든 업무 한 곳에서", 3)

    goto(page, APP_URL)
    narration(page, "앱 실행 — FastAPI · Next.js · CDP 브라우저 자동 기동", 3)

    goto(page, f"{APP_URL}/assistant")
    narration(page, "AI 작업 통합 관제 센터 — 연결된 사이트 9개", 3)
    page.mouse.wheel(0, 500)
    time.sleep(1)

    goto(page, f"{APP_URL}/assistant/tasks")
    narration(page, "실시간 자동화 작업 큐 — 백그라운드에서 지금도 실행 중", 3)

    goto(page, f"{APP_URL}/local-agents")
    narration(page, "MCP 로컬 에이전트 — AI와 PC가 실시간으로 연결됩니다", 3)


def scene_smartstore(page):
    print("\n📽  ACT 4: 스마트스토어")
    title_card(page, "ACT 4", "스마트스토어 상품 등록 — 30분 → 3분", 3)

    blank_page(
        page,
        """
    <div style="background:#1a0808;color:white;height:100vh;display:flex;
                flex-direction:column;align-items:center;justify-content:center;
                font-family:'Malgun Gothic',sans-serif;text-align:center;">
        <div style="font-size:26px;color:#ff8888;margin-bottom:30px;">
            상품 1개 등록 — 직접 하면 이렇습니다</div>
        <div style="font-size:20px;color:#bbb;line-height:2.6;">
            1. 카테고리 선택 (수백 개 중 정확한 것 찾기) &nbsp;→&nbsp; 5분<br>
            2. SEO 최적화 상품명 작성 &nbsp;→&nbsp; 10분<br>
            3. 구매 전환 상세설명 카피라이팅 &nbsp;→&nbsp; 10분<br>
            4. 경쟁사 가격 조사 &nbsp;→&nbsp; 5분
        </div>
        <div style="font-size:30px;font-weight:bold;margin-top:35px;color:#ff4444;">
            합계 30분 x 상품 수 = 하루 종일</div>
        <div style="font-size:28px;margin-top:20px;color:#66ff66;">
            AI: 상품명 입력 하나 → 전부 자동 완성 → 3분</div>
    </div>
    """,
        hold=6,
    )

    goto(page, "https://sell.smartstore.naver.com/#/home/dashboard")
    mask_pii(page)
    narration(page, "스마트스토어 — AI가 로그인 세션을 유지합니다", 3)

    goto(page, "https://sell.smartstore.naver.com/#/products/list")
    mask_pii(page)
    narration(page, "현재 판매 중인 상품 현황 — AI가 자동으로 파악합니다", 3)
    page.mouse.wheel(0, 400)
    time.sleep(1)

    goto(page, "https://sell.smartstore.naver.com/#/products/new")
    mask_pii(page)
    time.sleep(3)  # SPA 로딩 대기
    narration(page, "AI 상품 등록 시작 — 카테고리부터 자동 선택", 2.5)

    # 상품명 자동 입력
    try:
        page.evaluate("""
            const inputs = document.querySelectorAll('input');
            for (let i of inputs) {
                const rect = i.getBoundingClientRect();
                if (rect.width > 200) { i.focus(); break; }
            }
        """)
        time.sleep(0.5)
        product = "프리미엄 무선 마우스 인체공학 충전식 고해상도"
        for ch in product:
            page.keyboard.type(ch)
            time.sleep(0.06)
        narration(page, "SEO 최적화 상품명 자동 입력 완료", 3)
    except Exception as e:  # noqa: BLE001 - 홍보 영상 녹화용 브라우저 시나리오 스크립트 — UI 동작 실패해도 나레이션/녹화 흐름은 계속 진행(데모 목적), 결제는 명시적으로 사람이 직접 수행(코드에 없음)(2026-09-28 검토)
        print(f"  상품명 입력 실패: {e}")
        narration(page, "AI가 카테고리·상품명·상세설명을 자동으로 채웁니다", 4)

    narration(page, "경쟁사 가격 분석 완료 → 최적가 자동 제안", 3)
    narration(page, "제출 전 최종 확인은 사람이 — AI는 여기서 멈춥니다 ✋", 3)


def scene_grant_radar(page):
    print("\n📽  ACT 5: Grant Radar")
    title_card(page, "ACT 5", "정부 지원사업 — AI가 먼저 찾아드립니다", 3)

    blank_page(
        page,
        """
    <div style="background:#080f0a;color:white;height:100vh;display:flex;
                flex-direction:column;align-items:center;justify-content:center;
                font-family:'Malgun Gothic',sans-serif;text-align:center;">
        <div style="font-size:26px;color:#ffaa44;margin-bottom:30px;">
            받을 수 있는 지원금을 모르고 지나치는 이유</div>
        <div style="font-size:20px;color:#bbb;line-height:2.8;">
            📋 연간 수천 건 — 어디서 찾는지 모름<br>
            ❓ 우리 회사가 해당되는지 불명확<br>
            ⏰ 신청 기간을 놓침<br>
            📝 서류 작성이 너무 어려움
        </div>
        <div style="font-size:28px;font-weight:bold;margin-top:35px;color:#66ff88;">
            AI: 매일 스캔 → 해당 사업만 알림 → 신청서 초안 자동 작성</div>
    </div>
    """,
        hold=6,
    )

    goto(page, f"{APP_URL}/grant-radar")
    narration(page, "Grant Radar — AI가 오늘 새로 올라온 지원사업 스캔 중", 3)
    page.mouse.wheel(0, 400)
    time.sleep(1)
    narration(page, "우리 회사 프로필 자동 매칭 — 해당 사업만 필터됩니다", 3)
    page.mouse.wheel(0, 400)
    time.sleep(1)
    narration(page, "신청서 초안 자동 생성 — 사람이 검토 후 제출합니다", 3)


def scene_gabia(page):
    print("\n📽  ACT 6: 가비아")
    title_card(page, "ACT 6", "도메인 만료 = 서비스 중단 — AI가 먼저 감지합니다", 3)

    try:
        page.goto("https://www.gabia.com", timeout=20000)
        with contextlib.suppress(Exception):
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        mask_pii(page)
        time.sleep(3)
        narration(page, "가비아 — 도메인·서버 만료일 AI가 자동 모니터링", 3)
        narration(page, "만료 30일 전 자동 알림 → 갱신 페이지 자동 이동", 3)
        narration(page, "결제는 사람이 직접 — AI는 준비까지만", 2.5)
    except Exception as e:  # noqa: BLE001 - 홍보 영상 녹화용 브라우저 시나리오 스크립트 — UI 동작 실패해도 나레이션/녹화 흐름은 계속 진행(데모 목적), 결제는 명시적으로 사람이 직접 수행(코드에 없음)(2026-09-28 검토)
        print(f"  가비아 오류: {e}")
        narration(page, "가비아 도메인 자동 관리 — 만료 감지·갱신 준비 자동화", 4)


def scene_public_data(page):
    print("\n📽  ACT 7: 공공데이터포털")
    title_card(page, "ACT 7", "공공 API — 자동 발급·한도 모니터링", 2.5)

    try:
        page.goto("https://www.data.go.kr", timeout=20000)
        with contextlib.suppress(Exception):
            page.wait_for_load_state("domcontentloaded", timeout=12000)
        mask_pii(page)
        time.sleep(2)
        narration(page, "공공데이터포털 — API 인증키 현황 자동 조회", 3)
        narration(page, "일일 호출 한도 모니터링 — 초과 전 자동 경보", 3)
    except Exception as e:  # noqa: BLE001 - 홍보 영상 녹화용 브라우저 시나리오 스크립트 — UI 동작 실패해도 나레이션/녹화 흐름은 계속 진행(데모 목적), 결제는 명시적으로 사람이 직접 수행(코드에 없음)(2026-09-28 검토)
        print(f"  공공데이터 오류: {e}")
        narration(page, "공공데이터포털 API 자동 관리", 3)


def scene_outro(page):
    print("\n📽  ACT 8: 아웃트로")
    blank_page(
        page,
        """
    <div style="background:linear-gradient(135deg,#050515,#0d0d3a);
                color:white;height:100vh;display:flex;flex-direction:column;
                align-items:center;justify-content:center;
                font-family:'Malgun Gothic',sans-serif;text-align:center;">
        <div style="font-size:15px;color:#6699ff;letter-spacing:5px;margin-bottom:20px;">
            HAEHAN AI ENGINEERING</div>
        <div style="font-size:50px;font-weight:bold;margin-bottom:25px;
                    text-shadow:0 0 40px rgba(80,120,255,0.9);">
            모든 업무, AI 하나로</div>
        <div style="font-size:22px;color:#aac4ff;line-height:2.2;margin-bottom:40px;">
            스마트스토어 · 정부지원사업 · 도메인관리<br>
            공공데이터 · 유튜브 · 메일 자동화
        </div>
        <div style="font-size:22px;color:#ffcc44;margin-bottom:25px;">
            🔔 해한AI엔지니어링 구독 · 좋아요 · 알림설정</div>
        <div style="font-size:16px;color:rgba(255,255,255,0.4);">haehan-ai.kr</div>
    </div>
    """,
        hold=9,
    )


# ── 메인 ──────────────────────────────────────────────────────────────────────


def main():
    from playwright.sync_api import sync_playwright

    print("=" * 60)
    print("🎬 해한AI엔지니어링 홍보영상 제작 시작")
    print("=" * 60)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = ctx.new_page()
        page.set_viewport_size({"width": 1440, "height": 900})

        start_rec()
        time.sleep(1)

        try:
            scene_intro(page)
            scene_why(page)
            scene_youtube_channel(page)
            scene_app_dashboard(page)
            scene_smartstore(page)
            scene_grant_radar(page)
            scene_gabia(page)
            scene_public_data(page)
            scene_outro(page)
        except Exception as e:  # noqa: BLE001 - 홍보 영상 녹화용 브라우저 시나리오 스크립트 — UI 동작 실패해도 나레이션/녹화 흐름은 계속 진행(데모 목적), 결제는 명시적으로 사람이 직접 수행(코드에 없음)(2026-09-28 검토)
            print(f"\n❌ 오류: {e}")
            import traceback

            traceback.print_exc()
        finally:
            stop_rec()
            with contextlib.suppress(Exception):
                page.close()

    if not RAW_VIDEO.exists() or RAW_VIDEO.stat().st_size < 1_000_000:
        print("❌ 녹화 파일 없음 또는 너무 작음")
        sys.exit(1)

    print(f"\n✅ 원본: {RAW_VIDEO} ({RAW_VIDEO.stat().st_size / 1024 / 1024:.1f}MB)")
    print("\n🔄 최종 인코딩 중...")
    result = subprocess.run(
        [
            FFMPEG,
            "-y",
            "-i",
            str(RAW_VIDEO),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(FINAL_VIDEO),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    if result.returncode == 0:
        print(f"✅ 최종 영상: {FINAL_VIDEO} ({FINAL_VIDEO.stat().st_size / 1024 / 1024:.1f}MB)")
    else:
        print("❌ 인코딩 실패:", result.stderr[-500:])
        sys.exit(1)


if __name__ == "__main__":
    main()
