"""카카오 파일 자동 다운로드 CLI.

사용법:
  python scripts/kakao_download.py --last                  # 마지막 파일 다운로드
  python scripts/kakao_download.py --all                   # 화면에 보이는 전체
  python scripts/kakao_download.py --capture               # 화면 캡처 (디버그)
  python scripts/kakao_download.py --register-template 이름  # 템플릿 등록
  python scripts/kakao_download.py --app kakaotalk --last  # 카카오톡 대상
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.local_agent.desktop.screen_downloader import KakaoScreenDownloader


def main():
    args = sys.argv[1:]
    app = "kakaowork"
    if "--app" in args:
        idx = args.index("--app")
        if idx + 1 < len(args):
            app = args[idx + 1]

    dl = KakaoScreenDownloader()
    print(f"대상 앱: {app}  /  저장 경로: {dl.save_dir}")

    if "--capture" in args:
        path = dl.capture_and_show(app)
        print(f"캡처 저장: {path}")

    elif "--register-template" in args:
        idx = args.index("--register-template")
        name = args[idx + 1] if idx + 1 < len(args) else "download_btn"
        dl.register_template_interactive(name)

    elif "--all" in args:
        n = dl.download_all_visible(app)
        print(f"다운로드 완료: {n}건")

    elif "--last" in args:
        ok = dl.download_last_file(app)
        print("완료" if ok else "실패 — 템플릿 등록 필요")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
