"""YouTube 영상 분석 프로그램 - 1단계: 키워드 검색 → 바이럴 스크리닝.

사용법:
    python cli.py search "키워드" --max 20 --days 7
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.errors import HttpError
from yt_dlp.utils import DownloadError

load_dotenv(Path(__file__).parent / ".env")

from connectors.keyframe_extractor import extract_keyframes, find_transcript_context  # noqa: E402
from connectors.transcriber import get_transcript  # noqa: E402
from connectors.youtube_data_api import get_video_snippet, get_video_statistics, search_videos  # noqa: E402
from connectors.yt_dlp_downloader import download_video  # noqa: E402
from core.report_builder import build_report  # noqa: E402
from core.url_parser import extract_video_id  # noqa: E402
from core.viral_score import compute_scores  # noqa: E402

_TRANSCRIPT_DIR = Path(__file__).parent / "data" / "transcripts"
_VIDEO_DOWNLOAD_DIR = Path(__file__).parent / "data" / "downloads"
_FRAME_DIR = Path(__file__).parent / "data" / "frames"
_REPORT_DIR = Path(__file__).parent / "data" / "reports"


def cmd_search(query: str, max_results: int, days: int) -> None:
    published_after = None
    if days > 0:
        published_after = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    videos = search_videos(query, max_results=max_results, published_after=published_after)
    if not videos:
        print("검색 결과가 없습니다.")
        return

    stats = get_video_statistics([v["video_id"] for v in videos])
    merged = [{**v, **stats.get(v["video_id"], {})} for v in videos]
    scored = compute_scores(merged)
    vph_reliable = all(v["vph_reliable"] for v in scored)
    sort_label = "VPH" if vph_reliable else "조회수"

    print(f"\n'{query}' 검색 결과 (최근 {days}일, {len(scored)}건) — {sort_label} 내림차순\n")
    if not vph_reliable:
        print(
            "※ 게시 30일 초과 영상이 포함되어 VPH(시간당 조회수)가 최근 급상승세를 "
            "반영하지 못합니다. 조회수 기준으로 정렬했습니다. 최근 급상승 스크리닝은 "
            "--days 값을 30 이하로 줄여서 재실행하세요.\n"
        )
    print(f"{'제목':<40} {'채널':<20} {'조회수':>10} {'VPH':>8} {'참여율':>7}")
    print("-" * 90)
    for v in scored:
        title = v["title"][:38] + ".." if len(v["title"]) > 40 else v["title"]
        channel = v["channel_title"][:18] + ".." if len(v["channel_title"]) > 20 else v["channel_title"]
        vph_display = f"{v['vph']:>8,.0f}" if v["vph_reliable"] else f"{'(참고용)':>8}"
        print(f"{title:<40} {channel:<20} {v.get('view_count', 0):>10,} {vph_display} {v['engagement_rate']:>6.2f}%")
        print(f"  https://youtube.com/watch?v={v['video_id']}")


def cmd_transcribe(video_id: str, model_size: str) -> None:
    print(f"[1/2] '{video_id}' 다운로드 중 (오디오 + 자막 확인)...")
    downloaded = download_video(video_id, audio_only=True)
    print(f"  제목: {downloaded['title']}")
    print(
        f"  자막: {'있음(' + downloaded['subtitle_path'] + ')' if downloaded['subtitle_path'] else '없음 → Whisper 전사 예정'}"
    )

    print(f"[2/2] 전사 중 (source={'자막' if downloaded['subtitle_path'] else f'whisper:{model_size}'})...")
    transcript = get_transcript(
        video_id,
        subtitle_path=downloaded["subtitle_path"],
        audio_path=downloaded["media_path"],
        model_size=model_size,
    )

    _TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _TRANSCRIPT_DIR / f"{video_id}.json"
    out_path.write_text(
        json.dumps({**transcript, "title": downloaded["title"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n완료: {len(transcript['segments'])}개 구간, 저장 위치: {out_path}\n")
    preview = transcript["full_text"][:300]
    print(f"미리보기: {preview}{'...' if len(transcript['full_text']) > 300 else ''}")


def cmd_frames(video_id: str, max_frames: int = 12) -> None:
    transcript_path = _TRANSCRIPT_DIR / f"{video_id}.json"
    segments = []
    if transcript_path.exists():
        segments = json.loads(transcript_path.read_text(encoding="utf-8"))["segments"]
    else:
        print(
            "※ 전사 데이터가 없습니다 (frames 만 추출, 장면-자막 매핑 없이 진행). "
            "먼저 'transcribe' 를 실행하면 장면별 대사도 함께 볼 수 있습니다."
        )

    video_matches = list(_VIDEO_DOWNLOAD_DIR.glob(f"{video_id}.*"))
    video_file = next(
        (p for p in video_matches if p.suffix.lower() not in (".vtt", ".mp3", ".m4a", ".json")),
        None,
    )
    if video_file is None:
        print(f"[1/2] '{video_id}' 영상(화질 포함) 다운로드 중...")
        downloaded = download_video(video_id, audio_only=False)
        video_file = Path(downloaded["media_path"])
    else:
        print(f"[1/2] 기존 다운로드 파일 재사용: {video_file}")

    print("[2/2] 장면전환 키프레임 추출 중...")
    frames = extract_keyframes(video_id, str(video_file), max_frames=max_frames)

    frame_meta_path = _FRAME_DIR / video_id / "_meta.json"
    frame_meta_path.write_text(json.dumps(frames, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n완료: {len(frames)}개 키프레임 추출\n")
    for f in frames:
        ts = f["timestamp"]
        context = find_transcript_context(ts, segments) if ts is not None and segments else ""
        ts_display = f"{ts:.1f}" if ts is not None else "?"
        print(f"  #{f['index']} @ {ts_display}s  {f['path']}")
        if context:
            print(f"    대사: {context}")


def cmd_report(video_id: str, descriptions_path: str | None) -> None:
    transcript_path = _TRANSCRIPT_DIR / f"{video_id}.json"
    if not transcript_path.exists():
        raise RuntimeError(f"전사 데이터가 없습니다. 먼저 'transcribe {video_id}' 를 실행하세요.")
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

    frame_meta_path = _FRAME_DIR / video_id / "_meta.json"
    if not frame_meta_path.exists():
        raise RuntimeError(f"키프레임이 없습니다. 먼저 'frames {video_id}' 를 실행하세요.")
    frames_meta = json.loads(frame_meta_path.read_text(encoding="utf-8"))

    descriptions: dict[str, str] = {}
    if descriptions_path:
        descriptions = json.loads(Path(descriptions_path).read_text(encoding="utf-8"))

    segments = transcript["segments"]
    frames_with_desc = []
    for f in frames_meta:
        ts = f["timestamp"]
        context = find_transcript_context(ts, segments) if ts is not None and segments else ""
        frames_with_desc.append(
            {
                "index": f["index"],
                "timestamp": ts,
                "path": f["path"],
                "description": descriptions.get(
                    str(f["index"]), "(미판독 — Claude 가 이미지를 Read 한 뒤 --descriptions 로 전달)"
                ),
                "transcript_context": context,
            }
        )

    stats = None
    raw_stats = get_video_statistics([video_id]).get(video_id)
    snippet = get_video_snippet(video_id)
    if raw_stats and snippet:
        stats = compute_scores([{**raw_stats, "published_at": snippet["published_at"]}])[0]

    report_title = snippet["title"] if snippet else transcript.get("title", video_id)
    md = build_report(video_id, report_title, stats, transcript, frames_with_desc)

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _REPORT_DIR / f"{video_id}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"리포트 저장: {out_path}")


def cmd_analyze(video_id: str, model_size: str, max_frames: int = 12) -> None:
    """transcribe + frames 를 연달아 실행. 장면 판독(descriptions)과 report 는 그 결과를 보고 이어서 진행."""
    print("=== [analyze 1/2] 전사 ===")
    cmd_transcribe(video_id, model_size)
    print("\n=== [analyze 2/2] 키프레임 추출 ===")
    cmd_frames(video_id, max_frames=max_frames)
    print(
        f"\n다음 단계: data/frames/{video_id}/ 의 프레임 이미지를 판독해 descriptions.json 을 만든 뒤 "
        f"'python cli.py report {video_id} --descriptions data/frames/{video_id}/descriptions.json' 실행"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube 영상 분석 프로그램")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="키워드로 급상승/고조회수 영상 검색")
    search_parser.add_argument("query", help="검색 키워드")
    search_parser.add_argument("--max", type=int, default=20, dest="max_results")
    search_parser.add_argument("--days", type=int, default=7, help="최근 N일 이내 (0=제한없음)")

    transcribe_parser = subparsers.add_parser("transcribe", help="영상 다운로드 + 전사")
    transcribe_parser.add_argument("video_id", help="YouTube video ID (URL의 v= 뒤 값)")
    transcribe_parser.add_argument(
        "--model",
        default="base",
        dest="model_size",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper 모델 크기 (자막 없을 때만 사용, 기본 base)",
    )

    frames_parser = subparsers.add_parser("frames", help="키프레임 추출 (장면전환 감지)")
    frames_parser.add_argument("video_id", help="YouTube video ID")
    frames_parser.add_argument(
        "--count",
        type=int,
        default=12,
        dest="max_frames",
        help="추출할 최대 프레임 수 (기본 12, Claude Read 판독 비용 고려해 필요시만 상향)",
    )

    report_parser = subparsers.add_parser("report", help="종합 마크다운 리포트 생성")
    report_parser.add_argument("video_id", help="YouTube video ID")
    report_parser.add_argument(
        "--descriptions",
        dest="descriptions_path",
        default=None,
        help="{인덱스: 장면설명} JSON 파일 경로 (Claude 가 프레임을 Read 한 뒤 생성)",
    )

    analyze_parser = subparsers.add_parser("analyze", help="URL/video_id 하나로 전사+키프레임 추출까지 자동 실행")
    analyze_parser.add_argument("video_id", help="YouTube URL 또는 video ID")
    analyze_parser.add_argument(
        "--model",
        default="base",
        dest="model_size",
        choices=["tiny", "base", "small", "medium", "large"],
    )
    analyze_parser.add_argument(
        "--count",
        type=int,
        default=12,
        dest="max_frames",
        help="추출할 최대 프레임 수 (기본 12)",
    )

    args = parser.parse_args()

    if args.command in ("transcribe", "frames", "report", "analyze"):
        try:
            args.video_id = extract_video_id(args.video_id)
        except ValueError as e:
            print(f"오류: {e}", file=sys.stderr)
            sys.exit(1)

    if args.command == "search":
        if args.max_results <= 0:
            print("오류: --max 는 1 이상이어야 합니다.", file=sys.stderr)
            sys.exit(1)
        if args.days < 0:
            print("오류: --days 는 0 이상이어야 합니다 (0=제한없음).", file=sys.stderr)
            sys.exit(1)
        try:
            cmd_search(args.query, args.max_results, args.days)
        except RuntimeError as e:
            print(f"오류: {e}", file=sys.stderr)
            sys.exit(1)
        except HttpError as e:
            print(f"YouTube API 오류 (키/쿼터 확인 필요): {e.reason}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "transcribe":
        try:
            cmd_transcribe(args.video_id, args.model_size)
        except RuntimeError as e:
            print(f"오류: {e}", file=sys.stderr)
            sys.exit(1)
        except DownloadError as e:
            print(f"다운로드 오류 (video_id 확인 필요): {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "report":
        try:
            cmd_report(args.video_id, args.descriptions_path)
        except RuntimeError as e:
            print(f"오류: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "frames":
        try:
            cmd_frames(args.video_id, max_frames=args.max_frames)
        except RuntimeError as e:
            print(f"오류: {e}", file=sys.stderr)
            sys.exit(1)
        except DownloadError as e:
            print(f"다운로드 오류 (video_id 확인 필요): {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "analyze":
        try:
            cmd_analyze(args.video_id, args.model_size, max_frames=args.max_frames)
        except RuntimeError as e:
            print(f"오류: {e}", file=sys.stderr)
            sys.exit(1)
        except DownloadError as e:
            print(f"다운로드 오류 (video_id 확인 필요): {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
