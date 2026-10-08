"""견적서 모듈 순차 검증 파이프라인.

단계별 게이트: 이전 단계 FAIL 시 중단.

사용법:
    python scripts/eum/validate_pipeline.py            # 전체 실행
    python scripts/eum/validate_pipeline.py --stage 3  # 3단계부터 재실행
    python scripts/eum/validate_pipeline.py --quick    # schema/style 만 (Excel 불필요)
"""

from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── 결과 타입 ─────────────────────────────────────────────────────────────────
@dataclass
class StageResult:
    name: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detail: str = ""


# ── 단계 1: layout_schema ─────────────────────────────────────────────────────
def stage_schema() -> StageResult:
    try:
        from scripts.eum.shared.layout_schema import ITEM_START, LAST_ROW, N_FILLER, validate_schema

        errs = validate_schema()
        return StageResult(
            name="schema",
            passed=len(errs) == 0,
            errors=errs,
            detail=f"ITEM_START={ITEM_START}, LAST_ROW={LAST_ROW}, N_FILLER={N_FILLER}",
        )
    except Exception as e:  # noqa: BLE001 - 견적서 생성 파이프라인 검증 스테이지(schema/style/엑셀엔진/생성기 등) - 각 stage 실패시 StageResult(passed=False, errors=[...]) 반환, 읽기전용 검증
        return StageResult(name="schema", passed=False, errors=[str(e)])


# ── 단계 2: style_presets ────────────────────────────────────────────────────
def stage_style() -> StageResult:
    try:
        from scripts.eum.shared.style_presets import STYLE_PRESETS, validate_style

        errs = validate_style()
        return StageResult(
            name="style",
            passed=len(errs) == 0,
            errors=errs,
            detail=f"프리셋 수: {len(STYLE_PRESETS)}",
        )
    except Exception as e:  # noqa: BLE001 - 견적서 생성 파이프라인 검증 스테이지(schema/style/엑셀엔진/생성기 등) - 각 stage 실패시 StageResult(passed=False, errors=[...]) 반환, 읽기전용 검증
        return StageResult(name="style", passed=False, errors=[str(e)])


# ── 단계 3: layout_engine (win32com) ─────────────────────────────────────────
def stage_engine() -> StageResult:
    """실제 Excel 인스턴스에 렌더 후 자가검증."""
    try:
        import win32com.client as win32

        from scripts.eum.shared.layout_engine import render, verify_layout

        try:
            xl = win32.GetActiveObject("Excel.Application")
        except Exception:  # noqa: BLE001 - 견적서 생성 파이프라인 검증 스테이지(schema/style/엑셀엔진/생성기 등) - 각 stage 실패시 StageResult(passed=False, errors=[...]) 반환, 읽기전용 검증
            return StageResult(
                name="engine",
                passed=False,
                errors=["Excel이 실행 중이지 않습니다. 견적서 파일을 열고 재실행하세요."],
            )

        wb = xl.ActiveWorkbook
        if wb is None:
            return StageResult(name="engine", passed=False, errors=["열린 Workbook 없음"])

        ws = wb.Sheets(1)
        render(ws, xl)
        result = verify_layout(ws)

        return StageResult(
            name="engine",
            passed=result.passed,
            errors=result.errors,
            warnings=result.warnings,
            detail="win32com 렌더 + 자가검증 완료",
        )
    except ImportError:
        return StageResult(
            name="engine",
            passed=False,
            errors=["win32com 없음 — Excel 환경에서만 실행 가능"],
        )
    except Exception:  # noqa: BLE001 - 견적서 생성 파이프라인 검증 스테이지(schema/style/엑셀엔진/생성기 등) - 각 stage 실패시 StageResult(passed=False, errors=[...]) 반환, 읽기전용 검증
        return StageResult(name="engine", passed=False, errors=[traceback.format_exc()])


# ── 단계 4: layout_openpyxl ──────────────────────────────────────────────────
def stage_openpyxl() -> StageResult:
    try:
        from scripts.eum.shared.layout_openpyxl import render_to_file, verify_file

        out = Path("data/validate_pipeline_test.xlsx")
        path = render_to_file(str(out), recipient="검증용 테스트 수신처")
        errs = verify_file(path)

        return StageResult(
            name="openpyxl",
            passed=len(errs) == 0,
            errors=errs,
            detail=f"저장 경로: {path}",
        )
    except Exception:  # noqa: BLE001 - 견적서 생성 파이프라인 검증 스테이지(schema/style/엑셀엔진/생성기 등) - 각 stage 실패시 StageResult(passed=False, errors=[...]) 반환, 읽기전용 검증
        return StageResult(name="openpyxl", passed=False, errors=[traceback.format_exc()])


# ── 단계 5: excel_live (경량화 후 동작 확인) ─────────────────────────────────
def stage_live() -> StageResult:
    try:
        import importlib
        import scripts.eum.excel_live as mod

        # 필수 속성 존재 여부만 확인 (실제 Excel 연결 없이)
        missing = []
        for attr in ("apply_full_format", "update_values", "watch_mode", "ITEM_START", "LAST_ROW", "STD_H"):
            if not hasattr(mod, attr):
                missing.append(attr)

        # ITEM_START 값 일치 확인
        from scripts.eum.shared.layout_schema import ITEM_START as SCHEMA_ITEM_START

        live_item_start = getattr(mod, "ITEM_START", None)
        if live_item_start != SCHEMA_ITEM_START:
            missing.append(f"ITEM_START 불일치: excel_live={live_item_start}, schema={SCHEMA_ITEM_START}")

        return StageResult(
            name="live",
            passed=len(missing) == 0,
            errors=missing,
            detail="excel_live.py import + 상수 일치 확인",
        )
    except Exception:  # noqa: BLE001 - 견적서 생성 파이프라인 검증 스테이지(schema/style/엑셀엔진/생성기 등) - 각 stage 실패시 StageResult(passed=False, errors=[...]) 반환, 읽기전용 검증
        return StageResult(name="live", passed=False, errors=[traceback.format_exc()])


# ── 단계 6: quote_generator ──────────────────────────────────────────────────
def stage_generator() -> StageResult:
    try:
        import importlib
        import scripts.eum.quote_generator as mod

        missing = []
        for attr in ("generate_quote_xlsx",):
            if not hasattr(mod, attr):
                missing.append(f"함수 없음: {attr}")

        return StageResult(
            name="generator",
            passed=len(missing) == 0,
            errors=missing,
            detail="quote_generator.py import + generate() 존재 확인",
        )
    except Exception:  # noqa: BLE001 - 견적서 생성 파이프라인 검증 스테이지(schema/style/엑셀엔진/생성기 등) - 각 stage 실패시 StageResult(passed=False, errors=[...]) 반환, 읽기전용 검증
        return StageResult(name="generator", passed=False, errors=[traceback.format_exc()])


# ── 파이프라인 실행 ──────────────────────────────────────────────────────────


STAGES = [
    (1, "schema", stage_schema),
    (2, "style", stage_style),
    (3, "engine", stage_engine),
    (4, "openpyxl", stage_openpyxl),
    (5, "live", stage_live),
    (6, "generator", stage_generator),
]


def run(start_stage: int = 1, quick: bool = False) -> bool:
    stages = STAGES
    if quick:
        stages = [(n, nm, fn) for n, nm, fn in STAGES if n <= 2]
    else:
        stages = [(n, nm, fn) for n, nm, fn in STAGES if n >= start_stage]

    print(f"\n{'=' * 55}")
    print(f"  견적서 모듈 검증 파이프라인  (시작 단계: {start_stage})")
    print(f"{'=' * 55}")

    all_passed = True
    for num, name, fn in stages:
        print(f"\n[{num}단계] {name} 검증 중...")
        result = fn()

        if result.passed:
            print(f"  ✅ PASS — {result.detail}")
        else:
            print("  ❌ FAIL")
            for e in result.errors:
                print(f"     ✗ {e}")
            all_passed = False
            print(f"\n  → {name} 단계 실패. 수정 후 재실행하세요.")
            break

        for w in result.warnings:
            print(f"  ⚠  {w}")

    print(f"\n{'=' * 55}")
    if all_passed:
        print("  ✅ 전체 파이프라인 PASS")
    else:
        print("  ❌ 파이프라인 중단 — 위 실패 단계 수정 필요")
    print(f"{'=' * 55}\n")
    return all_passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, default=1, help="시작 단계 번호 (1~6)")
    parser.add_argument("--quick", action="store_true", help="schema/style 만 검증 (Excel 불필요)")
    args = parser.parse_args()
    ok = run(start_stage=args.stage, quick=args.quick)
    sys.exit(0 if ok else 1)
