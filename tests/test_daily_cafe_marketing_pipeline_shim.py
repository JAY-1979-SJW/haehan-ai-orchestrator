"""daily_cafe_marketing_pipeline 이동(B2) — 실행 전달 shim.

실제 구현은 scripts/naver/cafe/ops/daily_cafe_marketing_pipeline.py 로 이동했다.
Windows 작업 스케줄러(HaehanAI_DailyCafeMarketing)가 옛 경로
scripts/ops/daily_cafe_marketing_pipeline.py 를 그대로 실행하므로, 그 파일이
여전히 같은 main()을 내고, 직접 실행(`python scripts/ops/daily_cafe_marketing_pipeline.py`)
해도 새 위치의 main()이 불리는지 고정한다.
"""

from __future__ import annotations

import runpy
from unittest.mock import patch

from scripts.app_paths import repo_root

REPO_ROOT = repo_root()
SHIM_PATH = REPO_ROOT / "scripts" / "ops" / "daily_cafe_marketing_pipeline.py"
REAL_PATH = REPO_ROOT / "scripts" / "naver" / "cafe" / "ops" / "daily_cafe_marketing_pipeline.py"


def test_shim_file_exists_and_real_file_moved():
    assert SHIM_PATH.exists()
    assert REAL_PATH.exists()


def test_shim_import_exposes_same_main_as_real_module():
    import scripts.naver.cafe.ops.daily_cafe_marketing_pipeline as real_mod
    import scripts.ops.daily_cafe_marketing_pipeline as shim_mod

    assert shim_mod.main is real_mod.main


def test_direct_execution_via_runpy_calls_real_main():
    """python scripts/ops/daily_cafe_marketing_pipeline.py 와 같은 직접 실행 경로를
    runpy로 재현 — __main__ 블록이 새 위치의 main()을 부르는지 확인(실제 CDP/수집은
    mock으로 막아 부작용 없음)."""
    with patch("scripts.naver.cafe.ops.daily_cafe_marketing_pipeline.main", return_value=0) as mock_main:
        try:
            runpy.run_path(str(SHIM_PATH), run_name="__main__")
        except SystemExit as exc:
            assert exc.code == 0
        else:
            raise AssertionError("SystemExit 이 발생해야 한다(main() 호출 후 종료)")
        mock_main.assert_called_once()
