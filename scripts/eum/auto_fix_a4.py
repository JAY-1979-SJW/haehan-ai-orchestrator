"""AI 지적 이슈를 자동 분석·수정·재검증하는 자동화 루프.

흐름:
  render → ai_check → 이슈 파싱 → 코드 수정 → 재render → 재check
  최대 MAX_ITER 반복, A등급 달성 시 종료.

사용법:
    python scripts/eum/auto_fix_a4.py <xlsx_파일경로>
    python scripts/eum/auto_fix_a4.py data/견적서_아람정보통신_v7.xlsx
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = ROOT / "scripts" / "ops"
MAX_ITER = 3  # 최대 자동 수정 반복 횟수


# ── AI 검사 실행 + 결과 파싱 ──────────────────────────────────────────────────


def run_ai_check(file_path: str) -> dict:
    """ai_check_a4.py 를 실행하고 JSON 결과를 반환."""
    # ai_check_a4 는 콘솔 출력 전용이므로 내부 함수 직접 호출
    sys.path.insert(0, str(OPS_DIR))
    from ai_check_a4 import ai_evaluate, extract_sheet_data

    data = extract_sheet_data(file_path)
    result = ai_evaluate(data)
    return result


# ── 이슈 → 수정 매핑 ─────────────────────────────────────────────────────────


def fix_border(issue: dict) -> bool:
    """테두리 미닫힘 → layout_schema 에서 border=None 셀을 border='thin' 으로 수정."""
    schema_path = ROOT / "scripts" / "eum" / "shared" / "layout_schema.py"
    src = schema_path.read_text(encoding="utf-8")

    # date, greeting 셀의 border=None → border="thin"
    targets = [
        (
            'id="date", rows=(3, 3), cols=(2, 5),\n        preset="body", border=None',
            'id="date", rows=(3, 3), cols=(2, 5),\n        preset="body", border="thin"',
        ),
        (
            'id="greeting", rows=(6, 6), cols=(2, 5),\n        preset="body", border=None',
            'id="greeting", rows=(6, 6), cols=(2, 5),\n        preset="body", border="thin"',
        ),
    ]
    changed = False
    for old, new in targets:
        if old in src:
            src = src.replace(old, new)
            changed = True

    if changed:
        schema_path.write_text(src, encoding="utf-8")
        print("[auto_fix] ✅ 테두리 수정: date·greeting 셀 border=None → thin")
    return changed


def fix_background(issue: dict) -> bool:
    """배경색 일관성 → sup_value 프리셋에 연한 회색 배경 추가."""
    presets_path = ROOT / "scripts" / "eum" / "shared" / "style_presets.py"
    src = presets_path.read_text(encoding="utf-8")

    old = '    "sup_value": dict(\n        bold=False, size=9, italic=False,\n        halign="left", valign="center",\n        wrap=True, bg=C_NONE, fg=C_BLACK,\n    ),'
    new = '    "sup_value": dict(\n        bold=False, size=9, italic=False,\n        halign="left", valign="center",\n        wrap=True, bg=C_GRAY, fg=C_BLACK,\n    ),'

    if old in src:
        src = src.replace(old, new)
        presets_path.write_text(src, encoding="utf-8")
        print("[auto_fix] ✅ 배경색 수정: sup_value bg=C_NONE → C_GRAY")
        return True
    return False


def fix_readability(issue: dict) -> bool:
    """가독성 이슈 — 현재 자동 수정 대상 없음."""
    print(f"[auto_fix] ℹ️  가독성 이슈 수동 확인 필요: {issue.get('detail', '')}")
    return False


def fix_margin(issue: dict) -> bool:
    """여백 이슈 — 현재 자동 수정 대상 없음."""
    print(f"[auto_fix] ℹ️  여백 이슈 수동 확인 필요: {issue.get('detail', '')}")
    return False


ISSUE_FIXERS: list[tuple[str, callable]] = [
    (r"테두리|border|R\)|B\)", fix_border),
    (r"배경색|background|fill|bg", fix_background),
    (r"가독성|폰트|font|size", fix_readability),
    (r"여백|margin", fix_margin),
]


def _match_fixer(issue: dict) -> callable | None:
    text = f"{issue.get('item', '')} {issue.get('detail', '')}".lower()
    for pattern, fn in ISSUE_FIXERS:
        if re.search(pattern, text, re.IGNORECASE):
            return fn
    return None


# ── 재렌더 ────────────────────────────────────────────────────────────────────


def re_render(file_path: str) -> None:
    """layout_openpyxl 으로 파일 재생성."""
    # 모듈 캐시 무효화 (코드 수정 후 reload 필요)
    import importlib

    import scripts.eum.shared.layout_openpyxl as lo
    import scripts.eum.shared.layout_schema as ls
    import scripts.eum.shared.style_presets as sp

    importlib.reload(ls)
    importlib.reload(sp)
    importlib.reload(lo)
    lo.render_to_file(file_path, recipient="")
    print(f"[auto_fix] 재렌더 완료: {file_path}")


# ── 메인 루프 ─────────────────────────────────────────────────────────────────


def run(file_path: str) -> bool:
    path = Path(file_path)
    if not path.exists():
        print(f"[auto_fix] ❌ 파일 없음: {path}")
        return False

    for iteration in range(1, MAX_ITER + 1):
        print(f"\n{'=' * 50}")
        print(f"[auto_fix] 반복 {iteration}/{MAX_ITER} — AI 검사 중...")
        print(f"{'=' * 50}")

        result = run_ai_check(file_path)
        grade = result.get("grade", "?")
        issues = result.get("issues", [])

        print(f"  등급: {grade}   이슈: {len(issues)}건")

        if grade == "A" and not issues:
            print("[auto_fix] ✅ A등급 달성 — 완료")
            return True

        if not issues:
            print(f"[auto_fix] 등급 {grade} 이지만 이슈 목록 없음 — 종료")
            return grade == "A"

        # 이슈별 자동 수정 시도
        any_fixed = False
        for iss in issues:
            fixer = _match_fixer(iss)
            if fixer:
                fixed = fixer(iss)
                any_fixed = any_fixed or fixed
            else:
                print(f"[auto_fix] ⚠️  자동 수정 불가: [{iss.get('item', '')}] {iss.get('detail', '')[:60]}")

        if not any_fixed:
            print("[auto_fix] 자동 수정 가능한 이슈 없음 — 수동 확인 필요")
            return False

        # 코드 수정 후 재렌더
        re_render(file_path)

    print(f"[auto_fix] ❌ {MAX_ITER}회 반복 후 미달 — 수동 확인 필요")
    return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python scripts/eum/auto_fix_a4.py <xlsx_파일경로>")
        sys.exit(1)
    ok = run(sys.argv[1])
    sys.exit(0 if ok else 1)
