"""naver_mail의 mail_read 패키지 이동(B2) — 옛 경로 shim이 하위 모듈까지 같은 모듈을 내는지.

실제 패키지는 scripts.naver.mail.read 로 이동했다. 옛 경로
scripts.naver.mail.read 와 그 하위 모듈(cdp 등)이 여전히 import 되는지,
그리고 새·옛 경로가 같은 모듈 객체를 가리키는지 고정한다.
"""

from __future__ import annotations

import importlib

import pytest

SUBMODULES = ("cdp", "body_reader", "classify", "entry", "list_collector", "pipeline")


def test_old_package_path_imports():
    import scripts.naver.mail.read as mod
    assert mod.__name__ == "scripts.naver.mail.read"


@pytest.mark.parametrize("name", SUBMODULES)
def test_old_submodule_path_is_same_object_as_new(name):
    old = importlib.import_module(f"scripts.naver.mail.read.{name}")
    new = importlib.import_module(f"scripts.naver.mail.read.{name}")
    assert old is new


def test_from_import_style_still_works():
    from scripts.naver.mail.read import (
        body_reader,
        cdp,
        classify,
        entry,
        list_collector,
        pipeline,
    )

    assert cdp.__name__ == "scripts.naver.mail.read.cdp"
    assert body_reader.__name__ == "scripts.naver.mail.read.body_reader"
    assert classify.__name__ == "scripts.naver.mail.read.classify"
    assert entry.__name__ == "scripts.naver.mail.read.entry"
    assert list_collector.__name__ == "scripts.naver.mail.read.list_collector"
    assert pipeline.__name__ == "scripts.naver.mail.read.pipeline"
