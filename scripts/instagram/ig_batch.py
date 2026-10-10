"""인스타그램(big.sun2024) 다음 시공사례 발행 CLI.

사용:
    python scripts/instagram/ig_batch.py --dry-run          # 후보 확인만
    python scripts/instagram/ig_batch.py                     # 업로드+캡션까지 (미발행)
    python scripts/instagram/ig_batch.py --confirmed         # 실제 발행 (매번 사용자 승인 후에만 사용)
    python scripts/instagram/ig_batch.py --category 펜던트     # 카테고리 지정
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.instagram.caption import build_caption  # noqa: E402
from scripts.instagram.cases import next_case  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="시공사례", help="기본값 시공사례 — 캡션 템플릿이 실제 시공 사진 전용")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirmed", action="store_true", help="실제 게시(공유하기)까지 진행 — --confirm 승인 문구도 필요")
    from scripts.common.gate import CONFIRM_TEXTS

    ap.add_argument("--confirm", default=None, help=f"실제 게시 승인 문구(직접 입력): {CONFIRM_TEXTS['instagram_publish']}")
    args = ap.parse_args()

    case = next_case(args.category)
    if case is None:
        print("발행할 새 시공사례가 없습니다 (모두 발행됨 또는 폴더 비어있음).")
        return

    print(f"[다음 사례] {case.case_id} — 이미지 {len(case.images)}장")
    for img in case.images:
        print(f"  - {img.name}")
    print("\n[캡션 미리보기]\n" + "-" * 40)
    print(build_caption(case))
    print("-" * 40)

    if args.dry_run:
        print("\n[DRY-RUN] 업로드/발행 생략")
        return

    from scripts.instagram.publish import publish_case

    from scripts.common.gate import GateBlocked

    try:
        result = publish_case(case, confirmed=args.confirmed, approval=args.confirm)
    except GateBlocked as exc:
        raise SystemExit(f"게시 차단: {exc.result.reason} (사용자가 직접 입력한 승인 문구가 필요합니다)") from exc
    if result["posted"]:
        print(f"\n✅ 발행 완료: {case.case_id}")
    else:
        print("\n[대기] 업로드+캡션까지 완료, 실제 발행은 안 함 (--confirmed 필요)")


if __name__ == "__main__":
    main()
