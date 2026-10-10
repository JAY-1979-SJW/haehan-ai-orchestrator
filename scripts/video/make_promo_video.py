"""
홍보영상 제작 스크립트 (공용)
- Playwright: 실제 브라우저 조작 녹화 (스크린샷 시퀀스)
- PIL: 한글+영어 자막 합성
- FFmpeg: MP4 변환

사용:
    python make_promo_video.py                          # 기본값
    python make_promo_video.py --url http://localhost:8080 --scenes scenes.json --out promo.mp4
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:3000", help="앱 베이스 URL")
    p.add_argument("--scenes", default=None, help="씬 정의 JSON 파일 경로 (없으면 기본값 사용)")
    p.add_argument("--out", default=None, help="출력 MP4 경로")
    p.add_argument("--watermark", default="Haehan AI — MVP Demo", help="우상단 워터마크 텍스트")
    return p.parse_args()


_ARGS = _parse_args()

ROOT = Path(__file__).resolve().parents[2]
PROMO_DIR = ROOT / "data" / "promo"
FRAMES_DIR = PROMO_DIR / "frames"
OUTPUT_VIDEO = Path(_ARGS.out) if _ARGS.out else PROMO_DIR / "promo.mp4"
BASE_URL = _ARGS.url

PROMO_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

# ── 자막 정의 (외부 JSON 또는 기본값) ────────────────────────────────────
_DEFAULT_SCENES = [
    {
        "url": "/assistant",
        "actions": [],
        "caption_ko": "Haehan AI 비서앱 MVP",
        "caption_en": "AI Assistant Dashboard — Real-time Status",
        "hold_sec": 4,
    },
    {
        "url": "/assistant",
        "actions": ["scroll_down"],
        "caption_ko": "백엔드 상태 카드 — API 실시간 조회",
        "caption_en": "Backend Status Cards via REST API",
        "hold_sec": 3,
    },
    {
        "url": "/assistant/tasks",
        "actions": [],
        "caption_ko": "작업 큐 — DRY_RUN 자동화 작업 목록",
        "caption_en": "Task Queue — DRY_RUN Only, No Execution",
        "hold_sec": 4,
    },
    {
        "url": "/assistant/tasks",
        "actions": ["click_filter"],
        "caption_ko": "상태별 필터 — 실시간 분류",
        "caption_en": "Status Filter — Instant Classification",
        "hold_sec": 3,
    },
    {
        "url": "/assistant/approval",
        "actions": [],
        "caption_ko": "승인 게이트 — 위험도별 차단 현황",
        "caption_en": "Approval Gates — Risk-level Blocking",
        "hold_sec": 4,
    },
    {
        "url": "/assistant/external-sites",
        "actions": [],
        "caption_ko": "외부 사이트 연동 현황 — 접속 버튼 없음",
        "caption_en": "External Providers — Read-Only View",
        "hold_sec": 4,
    },
    {
        "url": "/assistant/logs",
        "actions": [],
        "caption_ko": "로그 · 감사 통합 뷰 — 실시간 이벤트",
        "caption_en": "Audit Log — Unified Event Stream",
        "hold_sec": 4,
    },
    {
        "url": "/assistant/logs",
        "actions": ["click_filter_warn"],
        "caption_ko": "레벨 필터 — WARN / ERROR / BLOCKED 분류",
        "caption_en": "Level Filter — WARN / ERROR / BLOCKED",
        "hold_sec": 3,
    },
    {
        "url": "/assistant/storage",
        "actions": [],
        "caption_ko": "스토리지 상태 — 영속성 분류 및 B-3 감사",
        "caption_en": "Storage Status — Persistence & Audit Policy",
        "hold_sec": 4,
    },
    {
        "url": "/assistant/deployment",
        "actions": [],
        "caption_ko": "배포 상태 — SOP 안내 · 재시작 버튼 없음",
        "caption_en": "Deployment Status — SOP Guide, No Restart",
        "hold_sec": 4,
    },
    {
        "url": "/assistant",
        "actions": ["nav_tour"],
        "caption_ko": "7개 탭 통합 관리 — 읽기 전용 · DRY_RUN 전용",
        "caption_en": "7-Tab Integration — Read-Only · DRY_RUN Only",
        "hold_sec": 5,
    },
]

if _ARGS.scenes and Path(_ARGS.scenes).exists():
    SCENES = json.loads(Path(_ARGS.scenes).read_text(encoding="utf-8"))
else:
    SCENES = _DEFAULT_SCENES

FPS = 24
FONT_PATH_KO = "malgun.ttf"
FONT_PATH_EN = "arial.ttf"


def load_fonts():
    try:
        font_ko = ImageFont.truetype(FONT_PATH_KO, 28)
        font_en = ImageFont.truetype(FONT_PATH_EN, 20)
        font_ko_sm = ImageFont.truetype(FONT_PATH_KO, 18)
        # 좌상단 배지·워터마크: malgun.ttf (한글 지원) — arial은 한글 미지원으로 깨짐
        font_watermark = ImageFont.truetype(FONT_PATH_KO, 13)
    except Exception:  # noqa: BLE001 - 한글 폰트 로드 실패시 기본 폰트로 폴백, 프로모 영상 녹화 중 버튼 클릭 브라우저자동화 실패 무시(best-effort)
        font_ko = font_en = font_ko_sm = font_watermark = ImageFont.load_default()
    return font_ko, font_en, font_ko_sm, font_watermark


def add_caption(img: Image.Image, caption_ko: str, caption_en: str, fonts) -> Image.Image:
    font_ko, font_en, _, font_watermark = fonts
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # 자막 배경 (하단)
    bar_h = 90
    overlay = Image.new("RGBA", (w, bar_h), (0, 0, 0, 180))
    img = img.convert("RGBA")
    img.alpha_composite(overlay, (0, h - bar_h))
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    # 한글 자막
    draw.text((w // 2, h - bar_h + 16), caption_ko, font=font_ko, fill=(255, 255, 255), anchor="mt")
    # 영문 자막
    draw.text((w // 2, h - bar_h + 54), caption_en, font=font_en, fill=(180, 210, 255), anchor="mt")

    # 워터마크
    draw.text((w - 10, 10), _ARGS.watermark, font=font_watermark, fill=(255, 255, 255, 120), anchor="ra")

    # AI 자동화 배지 (좌상단) — 이모지 제거, malgun 폰트로 한글 정상 표시
    badge = "AI 자동화 작업 중"
    draw.rectangle([8, 8, 190, 30], fill=(30, 80, 200, 200))
    draw.text((14, 10), badge, font=font_watermark, fill=(255, 255, 255))

    return img


def take_screenshot(page, path: Path):
    page.wait_for_load_state("networkidle", timeout=5000)
    page.screenshot(path=str(path), full_page=False)


def write_frames(img: Image.Image, frame_dir: Path, start_idx: int, count: int) -> int:
    for i in range(count):
        img.save(frame_dir / f"frame_{start_idx + i:05d}.jpg", quality=92)
    return start_idx + count


def _apply_actions(page, scene, frame_idx, fonts):
    for action in scene.get("actions", []):
        if action == "scroll_down":
            page.mouse.wheel(0, 400)
            time.sleep(0.6)
        elif action == "click_filter":
            btns = page.locator("button").all()
            if len(btns) > 1:
                btns[1].click(timeout=1000)
                time.sleep(0.5)
        elif action == "click_filter_warn":
            warn_btn = page.locator("button", has_text="WARN").first
            try:
                warn_btn.click(timeout=2000)
                time.sleep(0.5)
            except Exception:  # noqa: BLE001 - 한글 폰트 로드 실패시 기본 폰트로 폴백, 프로모 영상 녹화 중 버튼 클릭 브라우저자동화 실패 무시(best-effort)
                pass
        elif action == "nav_tour":
            nav_links = [
                "/assistant/tasks",
                "/assistant/approval",
                "/assistant/external-sites",
                "/assistant/logs",
                "/assistant/storage",
                "/assistant/deployment",
                "/assistant",
            ]
            for link in nav_links:
                page.goto(BASE_URL + link)
                page.wait_for_load_state("domcontentloaded")
                time.sleep(0.7)
                ss_path = FRAMES_DIR / f"_tmp_{frame_idx:05d}.png"
                take_screenshot(page, ss_path)
                raw = Image.open(ss_path)
                captioned = add_caption(raw, scene["caption_ko"], scene["caption_en"], fonts)
                frame_idx = write_frames(captioned, FRAMES_DIR, frame_idx, FPS)
                ss_path.unlink(missing_ok=True)
            continue
    return frame_idx


def run():
    from playwright.sync_api import sync_playwright

    fonts = load_fonts()
    frame_idx = 0

    print("\n[1/3] 브라우저 조작 + 스크린샷 캡처 시작\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=400)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        for scene_no, scene in enumerate(SCENES):
            print(f"  Scene {scene_no + 1}/{len(SCENES)}: {scene['url']} — {scene['caption_ko']}")

            page.goto(BASE_URL + scene["url"])
            page.wait_for_load_state("domcontentloaded")
            time.sleep(1.2)

            # 액션 처리
            frame_idx = _apply_actions(page, scene, frame_idx, fonts)

            # 스크린샷
            ss_path = FRAMES_DIR / f"_tmp_{frame_idx:05d}.png"
            take_screenshot(page, ss_path)
            raw = Image.open(ss_path)
            captioned = add_caption(raw, scene["caption_ko"], scene["caption_en"], fonts)
            n_frames = int(scene["hold_sec"] * FPS)
            frame_idx = write_frames(captioned, FRAMES_DIR, frame_idx, n_frames)
            ss_path.unlink(missing_ok=True)

        browser.close()

    print(f"\n  총 {frame_idx}프레임 생성 완료\n")

    # ── FFmpeg MP4 변환 ──────────────────────────────────────────────────────
    print("[2/3] FFmpeg MP4 변환 중...")
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        str(FRAMES_DIR / "frame_%05d.jpg"),
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
        str(OUTPUT_VIDEO),
    ]
    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print("FFmpeg 오류:", result.stderr[-500:])
        sys.exit(1)

    print("\n[3/3] 완료!")
    print(f"  출력 파일: {OUTPUT_VIDEO}")
    size_mb = OUTPUT_VIDEO.stat().st_size / 1024 / 1024
    print(f"  파일 크기: {size_mb:.1f} MB")
    print(f"  해상도: 1440x900 / {FPS}fps\n")


if __name__ == "__main__":
    run()
