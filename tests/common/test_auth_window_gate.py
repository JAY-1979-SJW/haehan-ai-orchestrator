"""순차 인증창 게이트 — 범용 엔진 + 사이트 프로필 단위 테스트.

브라우저 없이 `classify`(순수 함수)로 여러 사이트의 단계 판정을 검증하고,
네이버 래퍼 API(detect_auth_stage/advance_once)도 가짜 page 로 검증한다.
"""

from scripts.common.auth_window_gate import (
    EUM_PROFILE,
    G2B_PROFILE,
    GABIA_PROFILE,
    NAVER_PROFILE,
    STAGE_CALLBACK,
    STAGE_CAPTCHA,
    STAGE_CERT,
    STAGE_LANDING,
    STAGE_LOGGED_IN,
    STAGE_LOGIN,
    STAGE_TWO_FACTOR,
    classify,
)
from scripts.naver.common import auth_window_gate as naver_gate


def probe(url, text="", buttons=(), hasPw=False):
    return {"url": url, "text": text, "buttons": list(buttons), "hasPw": hasPw}


class FakePage:
    """범용 probe 형태를 반환하는 가짜 page (+ SSO 클릭 라벨)."""

    def __init__(self, p, sso_label=None):
        self._p = p
        self._sso_label = sso_label
        self.brought_front = False

    def evaluate(self, js, *args):
        if "rx.test" in js:  # click_sso JS
            return self._sso_label
        return self._p

    def bring_to_front(self):
        self.brought_front = True


# ── 범용 classify: 네이버 ─────────────────────────────────────────────────────
def test_naver_two_factor():
    st = classify(
        probe("https://accounts.commerce.naver.com/certify?url=x", text="2단계 인증 인증번호 6자리를 입력"),
        NAVER_PROFILE,
    )
    assert st["stage"] == STAGE_TWO_FACTOR and st["needs_user"] is True


def test_naver_captcha():
    st = classify(probe("https://nid.naver.com/login", text="보안문자를 입력하세요"), NAVER_PROFILE)
    assert st["stage"] == STAGE_CAPTCHA


def test_naver_login_page():
    st = classify(probe("https://accounts.commerce.naver.com/login?url=x"), NAVER_PROFILE)
    assert st["stage"] == STAGE_LOGIN
    # 하위호환 별칭
    assert st["stage"] == naver_gate.STAGE_COMMERCE_LOGIN


def test_naver_callback():
    assert (
        classify(probe("https://sell.smartstore.naver.com/#/login-callback"), NAVER_PROFILE)["stage"] == STAGE_CALLBACK
    )


def test_naver_landing():
    st = classify(
        probe("https://sell.smartstore.naver.com/#/home/about", buttons=["로그인하기", "가입하기"]), NAVER_PROFILE
    )
    assert st["stage"] == STAGE_LANDING


def test_naver_logged_in():
    st = classify(
        probe("https://sell.smartstore.naver.com/#/seller/products", buttons=["상품관리", "주문관리"]), NAVER_PROFILE
    )
    assert st["stage"] == STAGE_LOGGED_IN and st["needs_user"] is False


def test_naver_sso_detected():
    st = classify(
        probe("https://accounts.commerce.naver.com/login", buttons=["네이버 아이디로 간편 로그인 skyj****"]),
        NAVER_PROFILE,
    )
    assert st["sso"]


# ── 범용 classify: 다른 사이트 (범용성 검증) ─────────────────────────────────────
def test_g2b_cert_stage():
    st = classify(probe("https://www.g2b.go.kr/login", text="공동인증서 선택 후 로그인"), G2B_PROFILE)
    assert st["stage"] == STAGE_CERT and st["needs_user"] is True


def test_gabia_login_stage():
    st = classify(probe("https://login.gabia.com/", buttons=["로그인"]), GABIA_PROFILE)
    assert st["stage"] in (STAGE_LOGIN, STAGE_LANDING)  # login url + 로그인 버튼


def test_eum_logged_in():
    st = classify(probe("https://eum.cw.or.kr/main", buttons=["마이페이지", "로그아웃"]), EUM_PROFILE)
    assert st["stage"] == STAGE_LOGGED_IN


def test_profiles_are_independent():
    # 같은 본문이라도 프로필별 도메인/규칙으로 다르게 판정
    p = probe("https://other.example.com/x", text="hello")
    assert classify(p, NAVER_PROFILE)["stage"] != STAGE_LOGGED_IN  # 네이버 도메인 아님 → unknown


# ── 네이버 래퍼 advance_once (가짜 page) ─────────────────────────────────────────
def test_advance_sso_clicked():
    page = FakePage(
        probe("https://accounts.commerce.naver.com/login", buttons=["간편 로그인"]), sso_label="간편 로그인"
    )
    step = naver_gate.advance_once(page)
    assert step["action"] == "sso_clicked"


def test_advance_two_factor_brings_front():
    page = FakePage(probe("https://accounts.commerce.naver.com/certify", text="2단계 인증"))
    step = naver_gate.advance_once(page)
    assert step["action"] == "needs_user" and page.brought_front is True


def test_advance_logged_in():
    page = FakePage(probe("https://sell.smartstore.naver.com/#/seller/home", buttons=["상품관리"]))
    assert naver_gate.advance_once(page)["action"] == "logged_in"
