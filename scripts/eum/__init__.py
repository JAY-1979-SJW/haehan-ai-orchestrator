"""EUM (건설근로자공제회) 자동화 패키지.

기존 scripts/eum_*.py 스탠드얼론 스크립트들을 패키지로 통합.
원본 파일은 보존 — 이 패키지는 라우터 진입점만 추가.

사용:
    python scripts/entry/cdp_cli.py eum extract
    python scripts/entry/cdp_cli.py eum dashboard
    python scripts/entry/cdp_cli.py eum mail
    python scripts/entry/cdp_cli.py eum new-sites
"""
from __future__ import annotations
