"""정부점검 대비 AI 자체점검 20편 배치 발행 (publish_ep_batch.py와 동일 구조,
data/marketing/ep_batch_full_gov2.json 을 읽어 발행)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.common.gate import force_approved  # noqa: E402
from scripts.naver.blog.core.writer import write_post  # noqa: E402
from scripts.naver.blog.unsplash_images import resolve_unsplash_images as _resolve_unsplash_images  # noqa: E402

FULL_PATH = ROOT / "data" / "marketing" / "ep_batch_full_gov2.json"
LOG_PATH = ROOT / "data" / "marketing" / "ep_batch_gov2_publish_log.jsonl"
UPLOAD_DIR = ROOT / "data" / "blog_uploads"
CATEGORY = "AI 업무자동화 연구소"


def resolve_topic_image(title: str) -> str | None:
    try:
        names = _resolve_unsplash_images(title, [], count=1)
    except Exception as e:  # noqa: BLE001 - 대표사진(Unsplash) 소싱 실패시 사진 없이 진행, 블로그 발행(write_post) 실패는 ok:False로 로그에 기록되어 성공으로 위장되지 않음
        print(f"  대표사진 소싱 실패(무시): {e}")
        return None
    for n in names:
        p = UPLOAD_DIR / n if not Path(n).is_absolute() else Path(n)
        if p.exists():
            return str(p)
    return None


def main() -> int:
    # 사용법: python publish_ep_batch_gov2.py [건너뛸 개수] --confirm=<승인 문구(사용자가 직접 입력)>
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    confirm = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--confirm=")), None)
    skip_n = int(args[0]) if args else 0
    from scripts.common.gate import GateBlocked, require_approved

    try:  # force_approved() 로 게이트를 우회하기 전에, 사용자가 입력한 승인 문구를 먼저 확인한다
        require_approved("blog_publish", confirm, via="publish_ep_batch_gov2")
    except GateBlocked as exc:
        raise SystemExit(f"발행 차단: {exc.result.reason} (사용자가 직접 입력한 승인 문구가 필요합니다)") from exc
    items = json.loads(FULL_PATH.read_text(encoding="utf-8"))
    page = get_page()

    for item in items:
        i = item["index"]
        if i <= skip_n:
            continue
        title = item["title"]
        body = item["body"]
        chart_path = UPLOAD_DIR / item["chart"]

        if "[[CHART]]" not in body:
            seg1, seg2 = body, ""
        else:
            seg1, seg2 = body.split("[[CHART]]", 1)

        topic_img = resolve_topic_image(title)
        images = [p for p in [topic_img, str(chart_path) if chart_path.exists() else None] if p]
        body_segments = [seg1, seg2] if seg2 else [seg1]

        print(f"[{i}/{len(items)}] 발행 시도: {title} (이미지 {len(images)}장)")
        try:
            with force_approved():
                result = write_post(
                    page,
                    title=title,
                    body=body,
                    body_segments=body_segments,
                    category=CATEGORY,
                    tags=None,
                    auto_tags=True,
                    images=images or None,
                    visibility="public",
                    require_approval=False,
                )
        except Exception as e:  # noqa: BLE001 - 대표사진(Unsplash) 소싱 실패시 사진 없이 진행, 블로그 발행(write_post) 실패는 ok:False로 로그에 기록되어 성공으로 위장되지 않음
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}

        record = {"index": i, "title": title, "result": result, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        status = "OK" if result.get("ok") else "FAIL"
        print(f"  -> {status}: {result.get('url') or result.get('error')}")
        time.sleep(6)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
