"""도구 분리 1단계(instagram) — 저장소 루트 직접 계산을 repo_root() 로 교체한 상수가 값 그대로인지 고정한다.

교체 전 값은 `Path(__file__).resolve().parents[N]`(= 저장소 루트)이었고, 교체 후는 `repo_root()`다. 이 시험은 각 상수가 저장소 루트에서
파생된 같은 위치를 가리키는지 확인한다(이후 파일을 폴더 안으로 옮겨도 같은 값이어야 한다).
"""

from __future__ import annotations

import importlib

import pytest

from scripts.app_paths import repo_root

ROOT = repo_root()

CASES = [
    ("scripts.instagram", "CACHE_PATH", ROOT / "data" / "instagram_post_cache.json"),
    ("scripts.instagram.reel", "REEL_DIR", ROOT / "data" / "instagram_reels"),
    ("scripts.instagram.kotara_ctc_reel", "ROOT", ROOT),
]


@pytest.mark.parametrize(("module", "attr", "expected"), CASES, ids=[f"{m}.{a}" for m, a, _ in CASES])
def test_constant_value_is_unchanged(module, attr, expected):
    value = getattr(importlib.import_module(module), attr)
    assert value == expected
    assert value.is_absolute()
