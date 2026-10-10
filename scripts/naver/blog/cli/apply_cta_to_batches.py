"""어제(v2)+오늘(gov2) 발행 40편에 명확한 CTA(문의 연락처)를 소급 적용.

edit_post()의 clear_body()는 본문 영역을 텍스트+이미지 전체 삭제하므로,
이미지 없이 텍스트만 넘기면 사진이 사라진다. 그래서 원래 발행 스크립트와
동일하게 대표사진(Unsplash) + 차트 이미지를 body_segments/images로 함께
다시 넣어준다([[CHART]] 마커 기준으로 분리).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.common.gate import force_approved  # noqa: E402
from scripts.naver.blog.core.writer import edit_post  # noqa: E402
from scripts.naver.blog.unsplash_images import resolve_unsplash_images as _resolve_unsplash_images  # noqa: E402

UPLOAD_DIR = ROOT / "data" / "blog_uploads"


def resolve_topic_image(title: str) -> str | None:
    try:
        names = _resolve_unsplash_images(title, [], count=1)
    except Exception as e:  # noqa: BLE001 - 대표사진(Unsplash) 소싱 실패시 사진 없이 진행, 게시물 수정(edit_post) 실패는 ok:False로 로그에 기록되어 성공으로 위장되지 않음
        print(f"  대표사진 소싱 실패(무시): {e}")
        return None
    for n in names:
        p = UPLOAD_DIR / n if not Path(n).is_absolute() else Path(n)
        if p.exists():
            return str(p)
    return None


V2_FULL = ROOT / "data" / "marketing" / "ep_batch_full.json"
V2_LOG = ROOT / "data" / "marketing" / "ep_batch_publish_log_v2.jsonl"
GOV2_FULL = ROOT / "data" / "marketing" / "ep_batch_full_gov2.json"
GOV2_LOG = ROOT / "data" / "marketing" / "ep_batch_gov2_publish_log.jsonl"
RESULT_LOG = ROOT / "data" / "marketing" / "ep_batch_cta_apply_log.jsonl"

OLD_CTA_V2 = "\n\n더 많은 AI 업무자동화 사례는 홈페이지(haehan-ai.kr)와 유튜브 채널(@해한ai)에서 확인하실 수 있습니다."
NEW_CTA_V2 = (
    "\n\n이런 AI 자동화를 실제 업무에 바로 적용해보고 싶으시면 편하게 문의 주세요.\n"
    "해한소프트(AI 건설 공무 자동화) | 전화 010-7387-6635 | haehan-ai.kr"
)

OLD_CTA_GOV2 = "\n\n정부점검 대비 AI 자체점검 1시간 무상 방문교육 문의: 해한 AI 엔지니어링 신재우 대표 010-3538-6635"
NEW_CTA_GOV2 = (
    "\n\n정부점검 대비 AI 자체점검, 대표님 회사 자료 1건으로 직접 실습하는 "
    "1시간 무상 방문교육을 신청하실 수 있습니다.\n"
    "실무형 AI 교육 문의 | 전화 010-7387-6635 | haehan-ai.kr"
)


def load_batch(full_path: Path, log_path: Path, old_cta: str, new_cta: str) -> list[dict]:
    full = {item["index"]: item for item in json.loads(full_path.read_text(encoding="utf-8"))}
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    out = []
    for line in lines:
        rec = json.loads(line)
        if not rec["result"].get("ok"):
            continue
        idx = rec["index"]
        item = full.get(idx)
        if not item:
            continue
        body = item["body"]
        if old_cta in body:
            new_body = body.replace(old_cta, new_cta)
        else:
            new_body = body + new_cta
        out.append(
            {
                "index": idx,
                "title": item["title"],
                "blog_id": rec["result"]["blog_id"],
                "log_no": rec["result"]["log_no"],
                "body": new_body,
                "chart": item.get("chart"),
            }
        )
    return out


def main() -> int:
    # 사용법: python apply_cta_to_batches.py [건너뛸 개수] --confirm=<승인 문구(사용자가 직접 입력)>
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    confirm = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--confirm=")), None)
    skip_n = int(args[0]) if args else 0
    from scripts.common.gate import GateBlocked, require_approved

    try:  # force_approved() 로 게이트를 우회하기 전에, 사용자가 입력한 승인 문구를 먼저 확인한다
        require_approved("blog_publish", confirm, via="apply_cta_to_batches")
    except GateBlocked as exc:
        raise SystemExit(f"발행 차단: {exc.result.reason} (사용자가 직접 입력한 승인 문구가 필요합니다)") from exc
    batch = load_batch(V2_FULL, V2_LOG, OLD_CTA_V2, NEW_CTA_V2) + load_batch(
        GOV2_FULL, GOV2_LOG, OLD_CTA_GOV2, NEW_CTA_GOV2
    )
    page = get_page()

    for n, item in enumerate(batch, 1):
        if n <= skip_n:
            continue
        print(f"[{n}/{len(batch)}] CTA 적용: {item['title']} (log_no={item['log_no']})")

        body = item["body"]
        chart_path = UPLOAD_DIR / item["chart"] if item.get("chart") else None
        if "[[CHART]]" in body:
            seg1, seg2 = body.split("[[CHART]]", 1)
        else:
            seg1, seg2 = body, ""
        topic_img = resolve_topic_image(item["title"])
        images = [p for p in [topic_img, str(chart_path) if chart_path and chart_path.exists() else None] if p]
        body_segments = [seg1, seg2] if seg2 else [seg1]

        try:
            with force_approved():
                result = edit_post(
                    page,
                    blog_id=item["blog_id"],
                    log_no=item["log_no"],
                    title=item["title"],
                    body=body,
                    body_segments=body_segments,
                    images=images or None,
                    visibility="public",
                )
        except Exception as e:  # noqa: BLE001 - 대표사진(Unsplash) 소싱 실패시 사진 없이 진행, 게시물 수정(edit_post) 실패는 ok:False로 로그에 기록되어 성공으로 위장되지 않음
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}

        record = {
            "n": n,
            "title": item["title"],
            "log_no": item["log_no"],
            "result": result,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with RESULT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        status = "OK" if result.get("ok") else "FAIL"
        print(f"  -> {status}: {result.get('url') or result.get('error')}")
        time.sleep(6)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
