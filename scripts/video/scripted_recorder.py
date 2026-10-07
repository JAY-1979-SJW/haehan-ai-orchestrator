"""대본(JSON) → 화면 녹화 + TTS 나레이션 → 장면별 mp4 → 합본.

`record_promo.py`(2026-06-13)와 같은 원리(gdigrab 화면 녹화 + CDP 조작)지만
세 가지가 다르다. 기존 파일은 그대로 두고 새로 만든 이유다.

  1. 장면·URL·나레이션이 코드에 하드코딩돼 있지 않고 **대본 JSON**에서 온다
  2. 스크롤뿐 아니라 **클릭·타이핑·select·키입력**을 타임라인으로 실행한다
     → "AI가 실제로 일하는 화면"을 보여주려면 조작이 필수다
  3. ffmpeg 를 PATH 에서 찾는다 (기존 하드코딩 경로는 이 PC 에 없다 — 실측)

카드 장면(제목/목록/표)은 HTML 을 만들어 브라우저에 띄우고 같이 녹화한다.
별도 편집 도구 없이 한 파이프라인으로 끝내기 위함.

사용:
    python -m scripts.video.scripted_recorder data/video_scripts/x.json --tts
    python -m scripts.video.scripted_recorder data/video_scripts/x.json --record
    python -m scripts.video.scripted_recorder data/video_scripts/x.json --merge
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import html
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_orchestrator.core.config import get_local_data_dir  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

_log = get_logger(__name__)

CDP_URL = "http://127.0.0.1:9222"
VOICE = "ko-KR-InJoonNeural"

# 녹화 영역 — Chrome 창을 이 위치·크기로 옮긴 뒤 그 영역만 잡는다.
# 16:9 로 맞춰야 유튜브에서 레터박스가 생기지 않는다.
RECORD_X, RECORD_Y = 60, 40
RECORD_W, RECORD_H = 1600, 900


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg 를 PATH 에서 찾을 수 없습니다.")
    return exe


def _dirs(script_id: str) -> dict[str, Path]:
    base = get_local_data_dir() / "video" / script_id
    d = {
        "base": base,
        "narration": base / "narration",
        "raw": base / "raw",
        "cards": base / "cards",
        "out": base,
    }
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    return d


def load_script(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("id", "scenes"):
        if not data.get(key):
            raise ValueError(f"대본에 '{key}' 가 없습니다")
    return data


# ── TTS ────────────────────────────────────────────────────────────────────


async def _tts_one(text: str, out: Path) -> None:
    import edge_tts  # type: ignore[import-not-found]  # 선택적 의존성(docs_registry.toml 등록)

    await edge_tts.Communicate(text, VOICE).save(str(out))


def build_narration(script: dict, force: bool = False) -> list[Path]:
    d = _dirs(script["id"])
    made = []
    for sc in script["scenes"]:
        out = d["narration"] / f"scene_{sc['id']:02d}.mp3"
        if out.exists() and not force:
            made.append(out)
            continue
        asyncio.run(_tts_one(sc["narration"], out))
        made.append(out)
        print(f"  TTS {out.name}  ({audio_seconds(out):.1f}초)")
    return made


def audio_seconds(mp3: Path) -> float:
    r = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(mp3),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ── 카드 장면 HTML ──────────────────────────────────────────────────────────

_CARD_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{width:100vw;height:100vh;display:flex;align-items:center;justify-content:center;
 background:#0d1b2a;color:#fff;font-family:'Malgun Gothic','맑은 고딕',sans-serif}
.wrap{text-align:center;padding:0 90px;max-width:1500px}
h1{font-size:96px;font-weight:800;line-height:1.25;letter-spacing:-2px}
.sub{margin-top:34px;font-size:40px;color:#8ecae6}
ul{list-style:none;text-align:left;display:inline-block}
li{font-size:52px;line-height:1.75;opacity:0;animation:in .5s forwards}
li b{color:#ffd166;margin-right:18px}
table{border-collapse:collapse;font-size:56px}
td{padding:16px 46px;border-bottom:1px solid #24405c}
td.v{font-weight:800;text-align:right}
.hi{color:#ffd166}.lo{color:#ff8fa3}
@keyframes in{to{opacity:1;transform:none}}
"""


def _card_html(scene: dict) -> str:
    shot = scene.get("shot", "title_card")
    if shot == "steps_card":
        items = "".join(
            f'<li style="animation-delay:{0.55 * i + 0.4:.2f}s">{html.escape(s)}</li>'
            for i, s in enumerate(scene.get("steps", []))
        )
        inner = f"<ul>{items}</ul>"
    elif shot == "accuracy_card":
        rows = ""
        for name, val in scene.get("rows", []):
            pct = int(str(val).rstrip("%") or 0)
            cls = "hi" if pct >= 90 else "lo"
            rows += f'<tr><td>{html.escape(name)}</td><td class="v {cls}">{html.escape(val)}</td></tr>'
        inner = f"<table>{rows}</table>"
    else:
        text = html.escape(scene.get("text", ""))
        sub = scene.get("sub", "")
        inner = f"<h1>{text}</h1>" + (f'<div class="sub">{html.escape(sub)}</div>' if sub else "")
    return f"<!doctype html><meta charset='utf-8'><style>{_CARD_CSS}</style><div class='wrap'>{inner}</div>"


def write_cards(script: dict) -> None:
    d = _dirs(script["id"])
    for sc in script["scenes"]:
        if sc.get("shot", "").endswith("_card"):
            p = d["cards"] / f"scene_{sc['id']:02d}.html"
            p.write_text(_card_html(sc), encoding="utf-8")


# ── 창 위치 고정 ────────────────────────────────────────────────────────────


def place_chrome() -> None:
    """Chrome 창을 녹화 영역에 맞춰 이동. 창이 어긋나면 엉뚱한 화면이 찍힌다."""
    user32 = ctypes.windll.user32
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process chrome | Where-Object {$_.MainWindowHandle -ne 0}"
            " | Select-Object -ExpandProperty MainWindowHandle",
        ],
        capture_output=True,
        timeout=10,
    )
    for line in r.stdout.decode("utf-8", "ignore").splitlines():
        if line.strip().isdigit():
            hwnd = int(line.strip())
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            user32.MoveWindow(hwnd, RECORD_X, RECORD_Y, RECORD_W, RECORD_H + 88, True)
            break
    time.sleep(0.8)


# ── 장면 녹화 ───────────────────────────────────────────────────────────────


async def _perform_action(page, act, do, sel):
    if do == "click":
        await page.click(sel, timeout=8000)
    elif do == "type":
        await page.click(sel, timeout=8000)
        await page.fill(sel, "")
        await page.type(sel, act.get("text", ""), delay=act.get("delay", 85))
    elif do == "key":
        await page.keyboard.press(act.get("key", "Enter"))
    elif do == "select":
        await page.select_option(sel, label=act.get("value", ""), timeout=8000)
    elif do == "scroll":
        await page.evaluate(f"window.scrollBy({{top:{act.get('px', 400)},behavior:'smooth'}})")
    elif do == "scroll_top":
        await page.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
    elif do == "hover":
        await page.hover(sel, timeout=8000)


async def _run_actions(page, actions: list[dict], t0: float) -> None:
    """타임라인 순서대로 조작 실행. at 은 녹화 시작 기준 초."""
    for act in sorted(actions, key=lambda a: a.get("at", 0)):
        delay = act.get("at", 0) - (time.time() - t0)
        if delay > 0:
            await asyncio.sleep(delay)
        do = act.get("do")
        sel = act.get("selector", "")
        try:
            await _perform_action(page, act, do, sel)
        except Exception as e:  # 조작 실패해도 녹화는 계속 — 장면을 통째로 잃지 않는다  # noqa: BLE001 - 녹화 스크립트 동작(클릭/스크롤/호버 등) 실패 시 경고 로그만 남기고 녹화 자체는 계속 진행 — 주석에 명시된 의도된 best-effort(장면을 통째로 잃지 않기 위함).
            _log.warning("[rec] 조작 실패 %s %s: %s", do, sel, str(e)[:90])


async def record_scene(script: dict, scene: dict, base_url: str) -> Path:
    """장면 1개를 녹화한다.

    ⚠️ 바탕화면 캡처(gdigrab)를 쓰지 않는다. 2026-08-20 실측 사고:
    gdigrab 은 지정 좌표의 **화면 영역**을 찍기 때문에, 녹화 중 창 포커스가
    바뀌면 그 자리에 있던 다른 창(터미널, 다른 탭)이 그대로 영상에 들어간다.
    실제로 무관한 창들이 녹화돼 파일을 폐기했다. 외부에 올릴 영상에서
    이건 치명적이다.

    그래서 **Playwright 전용 브라우저를 새로 띄워 그 페이지만** 녹화한다.
    - 다른 창이 물리적으로 들어올 수 없다 (화면이 아니라 페이지를 찍는다)
    - 사용자의 로그인 프로필과 분리된다 (개인 정보가 섞이지 않는다)
    - 대상이 localhost 견적 프로그램이라 로그인 세션도 필요 없다
    """
    from playwright.async_api import async_playwright

    d = _dirs(script["id"])
    sid = scene["id"]
    mp3 = d["narration"] / f"scene_{sid:02d}.mp3"
    if not mp3.exists():
        raise FileNotFoundError(f"나레이션 없음: {mp3} — 먼저 --tts 실행")

    dur = audio_seconds(mp3)
    rec_dur = dur + 1.2
    out = d["raw"] / f"scene_{sid:02d}.mp4"
    vid_dir = d["raw"] / f"_pw_{sid:02d}"
    if vid_dir.exists():
        shutil.rmtree(vid_dir)
    vid_dir.mkdir(parents=True, exist_ok=True)

    if scene.get("shot", "").endswith("_card"):
        url = (d["cards"] / f"scene_{sid:02d}.html").as_uri()
    else:
        url = base_url.rstrip("/") + scene.get("path", "/")

    print(f"\n[{sid}] {scene['name']} — 나레이션 {dur:.1f}s / 녹화 {rec_dur:.1f}s")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--force-device-scale-factor=1", "--hide-scrollbars"])
        ctx = await browser.new_context(
            viewport={"width": RECORD_W, "height": RECORD_H},
            record_video_dir=str(vid_dir),
            record_video_size={"width": RECORD_W, "height": RECORD_H},
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(1.8)
            t0 = time.time()
            await _run_actions(page, scene.get("actions", []), t0)
            left = rec_dur - (time.time() - t0)
            if left > 0:
                await asyncio.sleep(left)
        finally:
            await ctx.close()  # 이 시점에 webm 이 flush 된다
            await browser.close()

    webms = sorted(vid_dir.glob("*.webm"))
    if not webms:
        raise RuntimeError(f"장면 {sid} 녹화 실패 — webm 없음")
    _merge_audio(webms[0], mp3, out, dur)
    shutil.rmtree(vid_dir, ignore_errors=True)
    print(f"  ✓ {out.name}")
    return out


def _merge_audio(video: Path, mp3: Path, out: Path, dur: float) -> None:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-i",
            str(video),
            "-i",
            str(mp3),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-t",
            f"{dur + 0.7:.2f}",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=600,
    )


def merge_all(script: dict) -> Path:
    d = _dirs(script["id"])
    parts = [d["raw"] / f"scene_{sc['id']:02d}.mp4" for sc in script["scenes"]]
    parts = [p for p in parts if p.exists()]
    if not parts:
        raise RuntimeError("합칠 장면이 없습니다")
    lst = d["raw"] / "concat.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    out = d["out"] / f"{script['id']}.mp4"
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=900,
    )
    print(f"\n✅ 합본 {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--base-url", default="http://127.0.0.1:8900")
    ap.add_argument("--tts", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--scene", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    script = load_script(args.script)
    if args.tts:
        print("나레이션 생성")
        build_narration(script, force=args.force)
        total = sum(
            audio_seconds(_dirs(script["id"])["narration"] / f"scene_{s['id']:02d}.mp3") for s in script["scenes"]
        )
        print(f"\n총 길이 {total:.0f}초 ({total / 60:.1f}분)")
    if args.record:
        write_cards(script)
        scenes = [s for s in script["scenes"] if args.scene in (None, s["id"])]
        for sc in scenes:
            asyncio.run(record_scene(script, sc, args.base_url))
    if args.merge:
        merge_all(script)


if __name__ == "__main__":
    main()
