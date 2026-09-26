"""하나팩스 bulk_send: 05.g2b 팩스 디렉터리를 HAEHAN_G2B_FAX_DIR 로 바꿀 수 있고, 미설정 시 기존 기본값을 유지한다."""

import importlib
from pathlib import Path


def _reload(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("HAEHAN_G2B_FAX_DIR", raising=False)
    else:
        monkeypatch.setenv("HAEHAN_G2B_FAX_DIR", value)
    import scripts.hanafax.bulk_send as m

    return importlib.reload(m)


def test_default_path_unchanged(monkeypatch):
    m = _reload(monkeypatch, None)
    assert m.G2B_BASE == Path("C:/work/05. g2b/exports/개별팩스")
    assert m.FAX_FILE == m.G2B_BASE / "fax_common_v3.xlsx"
    assert m.BATCH_DIR == m.G2B_BASE / "batches"


def test_env_overrides_path(monkeypatch, tmp_path):
    m = _reload(monkeypatch, str(tmp_path))
    assert m.G2B_BASE == tmp_path
    assert m.FAX_FILE == tmp_path / "fax_common_v3.xlsx"
    assert m.BATCH_DIR == tmp_path / "batches"
    _reload(monkeypatch, None)
