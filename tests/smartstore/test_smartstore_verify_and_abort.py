"""스마트스토어 상품등록 — 액션 후 검증 / 조용한 실패 금지 회귀 테스트 (2026-08-15).

수정한 실제 문제:
  1. _fill_field 가 입력값을 확인하지 않고 ok:True 반환 → "넣었다는데 안 들어감"
  2. set_category 가 자동완성 첫 항목을 무조건 선택하고 검증 없음 → 엉뚱한 카테고리
  3. upload_main_image 가 폼에 없는 input[type=file] 을 기대 → 항상 실패
  4. register_product 가 앞 단계 실패에도 계속 진행하고 save 까지 함 → 불완전 상품 등록
"""

from __future__ import annotations

from scripts.naver.smartstore.product.general_product import (
    GeneralProductRegister,
    _normalize_field_value,
)


# ── 1. 값 정규화 ────────────────────────────────────────────────
def test_normalize_ignores_comma_and_currency():
    """판매가는 '55,000' 으로 되돌아오므로 그대로 비교하면 항상 불일치."""
    assert _normalize_field_value("55,000") == _normalize_field_value("55000")
    assert _normalize_field_value("55000원") == _normalize_field_value("55000")
    assert _normalize_field_value(" 100 ") == "100"
    assert _normalize_field_value(None) == ""


def test_normalize_keeps_real_difference():
    assert _normalize_field_value("55000") != _normalize_field_value("5500")


# ── 2. register_product 중단 로직 ───────────────────────────────
class _StubRegister(GeneralProductRegister):
    """페이지 없이 단계 성공/실패만 시뮬레이션."""

    def __init__(self, fail_on: str | None = None):
        self.fail_on = fail_on
        self.calls: list[str] = []
        self.saved = False

    def open(self, timeout_s: int = 30) -> bool:
        return True

    def _step(self, name: str) -> dict:
        self.calls.append(name)
        if self.fail_on == name:
            return {"ok": False, "error": f"{name} 실패"}
        return {"ok": True}

    def set_category(self, category_name):
        return self._step("category")

    def set_product_name(self, name):
        return self._step("name")

    def set_price(self, price):
        return self._step("price")

    def set_stock(self, stock):
        return self._step("stock")

    def upload_main_image(self, image_path):
        return self._step("main_image")

    def save(self, require_confirm: bool = True):  # type: ignore[override]
        self.saved = True
        self.calls.append("save")
        return {"ok": True}


DATA = {"category": "인테리어조명", "name": "테스트상품", "price": 1000, "stock": 10, "main_image": "x.png"}

# 이 파일은 **단계 진행 기계**(순서/중단/저장금지)를 검증한다.
# 사전 검증(preflight)은 그보다 앞단의 별도 관문이며 tests/quality_gates/test_preflight.py 가 맡는다.
# 여기서는 skip_preflight=True 로 우회해 검증 대상을 섞지 않는다.
# (실존하지 않는 'x.png' 는 preflight 가 정당하게 막는다 — 그 동작 자체는 정상이다)


def test_all_steps_run_when_no_failure():
    reg = _StubRegister()
    r = reg.register_product(DATA, save_after=False, skip_preflight=True)
    assert r["ok"] is True
    assert r["aborted"] is False
    assert reg.calls == ["category", "name", "price", "stock", "main_image"]


def test_aborts_on_first_failure():
    """실패 이후 단계는 실행되지 않아야 한다."""
    reg = _StubRegister(fail_on="name")
    r = reg.register_product(DATA, save_after=False, skip_preflight=True)
    assert r["ok"] is False
    assert r["aborted"] is True
    assert r["failed_at"] == "name"
    assert reg.calls == ["category", "name"]  # price/stock/image 미실행
    assert "price" not in reg.calls


def test_never_saves_when_a_step_failed():
    """핵심: 앞 단계가 실패하면 저장을 절대 하지 않는다."""
    reg = _StubRegister(fail_on="category")
    r = reg.register_product(DATA, save_after=True, require_confirm=False, skip_preflight=True)
    assert r["saved"] is False
    assert reg.saved is False, "실패했는데 저장이 실행됨 — 불완전 상품 등록 위험"
    assert "save" not in reg.calls


def test_saves_only_when_all_steps_ok():
    reg = _StubRegister()
    r = reg.register_product(DATA, save_after=True, require_confirm=False, skip_preflight=True)
    assert r["saved"] is True
    assert reg.saved is True
    assert reg.calls[-1] == "save"


def test_failed_at_is_none_on_success():
    reg = _StubRegister()
    r = reg.register_product(DATA, save_after=False, skip_preflight=True)
    assert r["failed_at"] is None


# ── 3. 이미지 업로드가 모달 경유 구조인지 ────────────────────────
def test_upload_uses_modal_helper():
    """폼에 input[type=file] 이 없으므로 모달 경유 헬퍼가 반드시 있어야 한다."""
    assert hasattr(GeneralProductRegister, "_open_image_modal")
    assert hasattr(GeneralProductRegister, "_uploaded_image_count")


def test_upload_aborts_when_modal_cannot_open(monkeypatch):
    reg = GeneralProductRegister.__new__(GeneralProductRegister)
    monkeypatch.setattr(reg, "_ensure_opened", lambda: True, raising=False)
    monkeypatch.setattr(reg, "_uploaded_image_count", lambda: 0, raising=False)
    monkeypatch.setattr(reg, "_open_image_modal", lambda: False, raising=False)

    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        p = Path(f.name)
    try:
        r = reg.upload_main_image(str(p))
        assert r["ok"] is False
        assert r["error"] == "image_modal_not_opened"
    finally:
        p.unlink(missing_ok=True)


def test_category_verifier_exists():
    """자동완성 첫 항목을 맹목적으로 고르지 않도록 검증 메서드가 있어야 한다."""
    assert hasattr(GeneralProductRegister, "get_selected_category")
