"""홍보 영상 녹화 스크립트 — 장면별 CDP 화면 조작 + FFmpeg gdigrab + 나레이션 합성.

실행:
  python scripts/video/record_promo.py           # 전체 녹화
  python scripts/video/record_promo.py --scene 1 # 특정 장면만
  python scripts/video/record_promo.py --merge   # 녹화된 장면 합치기만

출력:
  data/video/raw/scene_XX_*.mp4     # 장면별 raw 녹화
  data/video/final_promo.mp4        # 최종 합본
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ai_orchestrator.core.config import get_local_data_dir  # noqa: E402
from scripts.browser.session.browser_paths import find_ffmpeg  # noqa: E402

NARR_DIR = get_local_data_dir() / "video" / "narration"
RAW_DIR = get_local_data_dir() / "video" / "raw"
FINAL = get_local_data_dir() / "video" / "final_promo.mp4"
FFMPEG = find_ffmpeg() or "ffmpeg"  # 못 찾으면 이름만 넘겨 subprocess 가 FileNotFoundError 로 분명히 알린다
APP_BASE = "http://localhost:3000"
CDP_URL = "http://127.0.0.1:9222"

# 화면 녹화 영역 (Chrome for Testing 창 기준)
RECORD_X = 100
RECORD_Y = 50
RECORD_W = 1280
RECORD_H = 900

SCENES = [
    {"id": 0, "name": "intro", "url": f"{APP_BASE}/", "scroll_pause": 2, "actions": []},
    {
        "id": 1,
        "name": "smartstore",
        "url": f"{APP_BASE}/naver/smartstore",
        "scroll_pause": 2,
        "actions": ["scroll_down"],
    },
    {"id": 2, "name": "eum", "url": f"{APP_BASE}/eum", "scroll_pause": 2, "actions": ["scroll_down"]},
    {
        "id": 3,
        "name": "naver_collection",
        "url": f"{APP_BASE}/naver/blog",
        "scroll_pause": 2,
        "actions": ["scroll_down"],
    },
    {"id": 4, "name": "grant_radar", "url": f"{APP_BASE}/grant-radar", "scroll_pause": 2, "actions": ["scroll_down"]},
    {"id": 5, "name": "outro", "url": f"{APP_BASE}/", "scroll_pause": 2, "actions": []},
]


# ──────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────


def get_audio_duration(mp3: Path) -> float:
    r = subprocess.run(
        [FFMPEG, "-i", str(mp3), "-f", "null", "-"],
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
    )
    for line in (r.stdout + r.stderr).splitlines():
        if "Duration" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = parts.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 30.0


def bring_chrome_to_front() -> None:
    """Chrome for Testing 창을 전면으로."""
    user32 = ctypes.windll.user32
    import subprocess as sp

    r = sp.run(
        [
            "powershell",
            "-Command",
            "Get-Process chrome | Where-Object {$_.MainWindowHandle -ne 0}"
            " | Select-Object -ExpandProperty MainWindowHandle",
        ],
        capture_output=True,
        timeout=5,
    )
    handles = [int(h.strip()) for h in r.stdout.decode("utf-8", errors="ignore").splitlines() if h.strip().isdigit()]
    for hwnd in handles:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        user32.MoveWindow(hwnd, RECORD_X, RECORD_Y, RECORD_W, RECORD_H, True)
        break
    time.sleep(0.5)


async def navigate_and_prepare(page, scene: dict) -> None:
    """CDP로 페이지 이동 및 초기 준비."""
    await page.goto(scene["url"], wait_until="networkidle", timeout=15000)
    await asyncio.sleep(1.5)
    if "scroll_down" in scene.get("actions", []):
        # 천천히 스크롤 다운해서 콘텐츠 보여주기
        await page.evaluate("window.scrollBy({top: 300, behavior: 'smooth'})")
        await asyncio.sleep(0.8)
        await page.evaluate("window.scrollBy({top: 300, behavior: 'smooth'})")
        await asyncio.sleep(0.5)
        await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        await asyncio.sleep(0.5)


async def record_scene(scene: dict) -> Path:
    from playwright.async_api import async_playwright

    narr_dir = get_local_data_dir() / "video" / "narration"
    raw_dir = get_local_data_dir() / "video" / "raw"
    scene_id = scene["id"]
    name = scene["name"]
    mp3 = narr_dir / f"scene_{scene_id:02d}_{name}.mp3"
    if not mp3.exists():
        raise FileNotFoundError(f"나레이션 없음: {mp3}")

    duration = get_audio_duration(mp3)
    # 앞뒤 여유 추가
    record_duration = duration + 3.0

    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_video = raw_dir / f"scene_{scene_id:02d}_{name}_video.mp4"
    out_mp4 = raw_dir / f"scene_{scene_id:02d}_{name}.mp4"

    print(f"\n[장면 {scene_id}] {name} — 나레이션 {duration:.1f}초, 녹화 {record_duration:.1f}초")
    print(f"  URL: {scene['url']}")

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        # 기존 페이지 재사용 또는 신규 생성
        pages = context.pages
        page = pages[0] if pages else await context.new_page()
        await page.set_viewport_size({"width": RECORD_W - 16, "height": RECORD_H - 90})

        # 창 전면으로 이동
        bring_chrome_to_front()

        # 페이지 이동
        print("  페이지 이동 중...", end="", flush=True)
        await navigate_and_prepare(page, scene)
        print(" ✓")

        # FFmpeg 녹화 시작
        print(f"  녹화 시작 ({record_duration:.1f}초)...")
        ffmpeg_cmd = [
            FFMPEG,
            "-y",
            "-f",
            "gdigrab",
            "-framerate",
            "30",
            "-offset_x",
            str(RECORD_X),
            "-offset_y",
            str(RECORD_Y),
            "-video_size",
            f"{RECORD_W}x{RECORD_H}",
            "-i",
            "desktop",
            "-t",
            str(record_duration),
            "-vcodec",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(raw_video),
        ]
        ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 1초 후 스크롤 애니메이션 실행
        await asyncio.sleep(1.0)
        if "scroll_down" in scene.get("actions", []):
            for _ in range(3):
                await page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'})")
                await asyncio.sleep(1.5)
            await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")

        # 녹화 완료 대기
        ffmpeg_proc.wait()
        print(f"  녹화 완료 → {raw_video.name}")
        # browser.close()는 Chrome 자체를 종료하므로 호출하지 않음
        # async_playwright context manager 종료 시 자동으로 연결 해제됨

    # 오디오 합성
    print("  오디오 합성 중...")
    _merge_audio(raw_video, mp3, out_mp4, duration)
    print(f"  ✓ 완료 → {out_mp4.name}")
    return out_mp4


def _merge_audio(video: Path, audio: Path, out: Path, audio_dur: float) -> None:
    """영상 + 나레이션 합성. 나레이션은 1초 후 시작."""
    # gdigrab 녹화본에는 오디오 트랙 없음 → 오디오만 직접 추가
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-filter_complex",
            "[1:a]adelay=1000|1000[aout]",
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(out),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def merge_all_scenes(scene_ids: list[int] | None = None) -> Path:
    """녹화된 장면들을 하나의 영상으로 합칩니다."""
    raw_dir = get_local_data_dir() / "video" / "raw"
    final = get_local_data_dir() / "video" / "final_promo.mp4"
    scenes = SCENES if scene_ids is None else [s for s in SCENES if s["id"] in scene_ids]
    files = []
    for s in scenes:
        f = raw_dir / f"scene_{s['id']:02d}_{s['name']}.mp4"
        if f.exists():
            files.append(f)
        else:
            print(f"  ⚠ {f.name} 없음 — 건너뜀")

    if not files:
        raise FileNotFoundError("합칠 영상 파일이 없습니다.")

    concat_txt = raw_dir / "concat_list.txt"
    concat_txt.write_text("\n".join(f"file '{f}'" for f in files), encoding="utf-8")

    print(f"\n[합본] {len(files)}개 장면 합치는 중...")
    final.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-c",
            "copy",
            str(final),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"✓ 최종 영상 → {final}")
    dur = get_audio_duration(final)
    print(f"  총 재생 시간: {int(dur // 60)}분 {int(dur % 60)}초")
    return final


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────


async def run_all(scene_ids: list[int] | None = None) -> None:
    targets = SCENES if scene_ids is None else [s for s in SCENES if s["id"] in scene_ids]
    print(f"[녹화 시작] 총 {len(targets)}개 장면\n")
    for scene in targets:
        await record_scene(scene)
    if scene_ids is None:
        merge_all_scenes()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=int, nargs="+")
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()

    if args.merge:
        merge_all_scenes(args.scene)
    else:
        asyncio.run(run_all(args.scene))
