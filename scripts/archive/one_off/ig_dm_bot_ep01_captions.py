"""인스타 DM 봇 1편 — 자막(SRT) 생성 + 번인.

각 장면의 실제 나레이션 대본을 문장 단위로 쪼개, 그 장면의 실측 길이(scene_durations.json)
안에서 글자수 비례로 타이밍을 배분한다(TTS 단어별 타임스탬프가 한국어 음성에서 지원되지
않아 이 방식을 씀 — scene_durations.json 자체가 이미 실측 TTS 길이라 장면 경계는 정확함).

실행:
  python scripts/archive/one_off/ig_dm_bot_ep01_captions.py
출력: data/video/ig_dm_bot_ep01/captions.srt, final_captioned.mp4
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.core.config import get_local_data_dir  # noqa: E402
from scripts.archive.one_off.ig_dm_bot_ep01 import SCENES  # noqa: E402

OUT_DIR = get_local_data_dir() / "video" / "ig_dm_bot_ep01"


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.?!])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _srt_timestamp(sec: float) -> str:
    ms = round(sec * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt() -> Path:
    durations = json.loads((OUT_DIR / "scene_durations.json").read_text(encoding="utf-8"))
    scene_order = ["teaser", "hook", "architecture", "demo", "cta"]

    cues: list[tuple[float, float, str]] = []
    cursor = 0.0
    gap = 0.15  # 문장 사이 짧은 여백

    for name in scene_order:
        scene = next(s for s in SCENES if s["name"] == name)
        scene_dur = durations[name]
        sentences = _split_sentences(scene["text"])
        total_chars = sum(len(s) for s in sentences) or 1
        usable = scene_dur - gap * len(sentences)
        t = cursor
        for sent in sentences:
            dur = max(0.8, usable * (len(sent) / total_chars))
            cues.append((t, t + dur, sent))
            t += dur + gap
        cursor += scene_dur

    idx = 1
    lines = []
    for start, end, text in cues:
        # 자막 한 줄이 너무 길면 두 줄로 쪼갠다
        if len(text) > 24:
            mid = len(text) // 2
            split_at = text.rfind(" ", 0, mid) or mid
            text = text[:split_at].strip() + "\n" + text[split_at:].strip()
        lines.append(str(idx))
        lines.append(f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
        idx += 1

    srt_path = OUT_DIR / "captions.srt"
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return srt_path


def burn_in(video_path: Path, srt_path: Path, out_path: Path) -> Path:
    # libass가 srt 경로의 드라이브 콜론(:)을 필터 인자 구분자로 오인하므로 이스케이프한다.
    srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
    style = (
        "FontName=Malgun Gothic,FontSize=15,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00181614,BorderStyle=1,Outline=2,Shadow=0,"
        "MarginV=40,Alignment=2"
    )
    vf = f"subtitles='{srt_escaped}':force_style='{style}'"
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vf", vf, "-c:a", "copy", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"자막 번인 실패: {proc.stderr[-3000:]}")
    return out_path


def main() -> None:
    srt = build_srt()
    print(f"자막 생성 완료: {srt}")
    final = OUT_DIR / "final.mp4"
    captioned = OUT_DIR / "final_captioned.mp4"
    burn_in(final, srt, captioned)
    print(f"자막 번인 완료: {captioned}")


if __name__ == "__main__":
    main()
