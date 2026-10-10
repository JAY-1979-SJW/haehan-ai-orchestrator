"""한국 주요 사이트의 알려진 로그인 URL 직접 등재.

자동 탐색이 실패하는 사이트(메인 페이지 메뉴에 로그인 링크 노출 안 함,
큰 이미지 버튼/JS 클릭 방식)의 로그인 URL을 명시적으로 등록.

도메인 → 로그인 URL (개인뱅킹/일반 사용자 기준)
"""
from __future__ import annotations

KNOWN_LOGIN_URLS: dict[str, str] = {
    # ── 1금융권 은행 ──────────────────────────────────────────────────
    "hanabank.com": "https://www.hanabank.com/common/login.do",
    "kbstar.com": "https://obank.kbstar.com/quics?page=C025255",
    "shinhan.com": "https://bank.shinhan.com/index.jsp#020101000000",
    "wooribank.com": "https://spot.wooribank.com/pot/Dream?withyou=ENLGN0001",
    "nonghyup.com": "https://banking.nonghyup.com/servlet/IPNF0011I.view",
    "nhbank.com": "https://banking.nonghyup.com/servlet/IPNF0011I.view",
    "ibk.co.kr": "https://mybank.ibk.co.kr/uib/jsp/comm/main/CommMain001I.jsp",
    "kdb.co.kr": "https://www.kdb.co.kr/wbnt/UWBPLOGIN001_01.do",
    "epostbank.go.kr": "https://www.epostbank.go.kr/IPS_PHOEUM/login/login.jsp",
    "knbank.co.kr": "https://www.knbank.co.kr/ib20/mnu/PBKMAN000003",
    "busanbank.co.kr": "https://www.busanbank.co.kr/ib20/mnu/PBK01000",
    "dgb.co.kr": "https://m.dgb.co.kr/HanaBankWeb/HanaBankWeb.iface",
    "jbbank.co.kr": "https://www.jbbank.co.kr/EI/EIA0700.jbb",
    "kjbank.com": "https://pib.kjbank.com/jsp/login/login.jsp",
    "suhyup-bank.com": "https://suhyup-bank.com/ib20/mnu/PBKMAN0001",
    "citibank.co.kr": "https://www.citibank.co.kr/com/cmn/Login.cap",
    # 인터넷전문은행
    "kakaobank.com": "https://www.kakaobank.com/login",
    "kbanknow.com": "https://www.kbanknow.com/IPLATWEB/login/LOGIN_M01.jsp",
    "tossbank.com": "https://www.tossbank.com/login",

    # ── 카드 ─────────────────────────────────────────────────────────
    "samsungcard.com": "https://www.samsungcard.com/personal/login/UHPELGN0901M0.jsp",
    "shinhancard.com": "https://www.shinhancard.com/pconts/html/login.html",
    "hyundaicard.com": "https://www.hyundaicard.com/cpb/login/CPBLI0101_01.hc",
    "lottecard.co.kr": "https://www.lottecard.co.kr/app/IPBHB001M00.do",
    "kbcard.com": "https://card.kbcard.com/CXPRMA0030.cms",
    "hanacard.co.kr": "https://www.hanacard.co.kr/MWBCEMHC0010MA.web",
    "nhcard.co.kr": "https://card.nonghyup.com/nhcard/login/login.jsp",
    "wooricard.com": "https://pc.wooricard.com/cpc/cpa/cpadcg0011i.do",
    "citicard.co.kr": "https://www.citicard.co.kr/com/cmn/Login.cap",
    "bccard.com": "https://www.bccard.com/app/card/Login.do",

    # ── 보험 ─────────────────────────────────────────────────────────
    "samsungfire.com": "https://m.samsungfire.com/login.html",
    "kbinsure.co.kr": "https://www.kbinsure.co.kr/CG504000000.ec",
    "hyundaimarine.com": "https://www.hyundaimarine.com/customer/login/login.do",
    "samsunglife.com": "https://www.samsunglife.com/individual/customerCenter/myInfo/login.jsp",
    "hanwhalife.com": "https://www.hanwhalife.com/myhanwhalife/login.do",
    "kyobo.co.kr": "https://login.kyobo.co.kr/login.jsp",

    # ── 금융 감독 ─────────────────────────────────────────────────────
    "fss.or.kr": "https://www.fss.or.kr/fss/login/loginMain.do",
    "fsc.go.kr": "https://www.fsc.go.kr/login",
    "bok.or.kr": "https://www.bok.or.kr/portal/main/main.do",

    # ── 세무/관세 ─────────────────────────────────────────────────────
    "hometax.go.kr": "https://www.hometax.go.kr/websquare/websquare.html?w2xPath=/ui/pp/index_pp.xml",
    "nts.go.kr": "https://www.nts.go.kr/nts/login.do",
    "etax.seoul.go.kr": "https://etax.seoul.go.kr/index_pop.html",
    "wetax.go.kr": "https://www.wetax.go.kr/main/?cmd=LPTIHA01R0",
    "customs.go.kr": "https://unipass.customs.go.kr/clip/index.do",
    "unipass.customs.go.kr": "https://unipass.customs.go.kr/clip/index.do",

    # ── 4대보험 ───────────────────────────────────────────────────────
    "nhis.or.kr": "https://www.nhis.or.kr/nhis/etc/personalLoginPage.do",
    "hira.or.kr": "https://www.hira.or.kr/co/login/loginForm.do",
    "nps.or.kr": "https://www.nps.or.kr/jsppage/csa/login/csa_member_login.jsp",
    "kcomwel.or.kr": "https://total.kcomwel.or.kr/portal/Login.do",
    "ei.go.kr": "https://www.ei.go.kr/ei/eih/cm/hm/loginPage.do",
    "4insure.or.kr": "https://www.4insure.or.kr/ins4/ptl/login/Login.do",
    "comwel.or.kr": "https://total.kcomwel.or.kr/portal/Login.do",

    # ── 사법 ─────────────────────────────────────────────────────────
    "scourt.go.kr": "https://www.scourt.go.kr/portal/login/login.jsp",
    "iros.go.kr": "https://www.iros.go.kr/PMainJ.jsp",
    "ecfs.scourt.go.kr": "https://ecfs.scourt.go.kr/ecf/ecf300/Login.jsp",
    "efamily.scourt.go.kr": "https://efamily.scourt.go.kr/cif/loginMain.do",
    "klac.or.kr": "https://www.klac.or.kr/lawnews/login.do",

    # ── 정부/공공 ─────────────────────────────────────────────────────
    "gov.kr": "https://www.gov.kr/portal/loginMain",
    "minwon.go.kr": "https://www.gov.kr/portal/loginMain",
    "epeople.go.kr": "https://www.epeople.go.kr/jsp/cs/login/login.jsp",
    "data.go.kr": "https://www.data.go.kr/auth/login.do",
    "korea.go.kr": "https://www.korea.go.kr/user/loginPage.do",

    # ── 노동/취업 ─────────────────────────────────────────────────────
    "work.go.kr": "https://www.work.go.kr/seekWantedMain.do",
    "hrd.go.kr": "https://www.hrd.go.kr/hrdp/co/pcobo/PCOBO0100L.do",
    "q-net.or.kr": "https://www.q-net.or.kr/login.do",

    # ── 부동산/등기 ───────────────────────────────────────────────────
    "molit.go.kr": "https://www.molit.go.kr/USR/login/userLogin.jsp",
    "lh.or.kr": "https://www.lh.or.kr/contents/cont.do?sCode=user&mPid=44&mId=124",
    "kab.co.kr": "https://www.kab.co.kr/login/login.jsp",

    # ── 자동차/교통 ───────────────────────────────────────────────────
    "car365.go.kr": "https://www.car365.go.kr/Login.car",
    "ecar.go.kr": "https://www.ecar.go.kr/portal/login",
    "koroad.or.kr": "https://www.koroad.or.kr/main/login.do",

    # ── 인증서 ────────────────────────────────────────────────────────
    "yessign.or.kr": "https://www.yessign.or.kr/cms/login/login.jsp",
    "signkorea.com": "https://www.signkorea.com/login",
    "kica.or.kr": "https://www.kica.or.kr/web/login",

    # ── 통신사 ─────────────────────────────────────────────────────────
    "tworld.co.kr": "https://www.tworld.co.kr/web/login/index",
    "kt.com": "https://login.kt.com/wam/mem/login.do",
    "lguplus.com": "https://www.lguplus.com/uplogin",

    # ── EUM ──────────────────────────────────────────────────────────
    "eum.cw.or.kr": "https://eum.cw.or.kr/login",

    # ── 네이버 쇼핑몰 (스마트스토어 셀러센터) ──────────────────────────
    "sell.smartstore.naver.com": "https://www.naver.com/",
    "smartstore.naver.com": "https://www.naver.com/",
    "commerce.naver.com": "https://www.naver.com/",
    "center.shopping.naver.com": "https://www.naver.com/",
    "adcenter.naver.com": "https://www.naver.com/",  # 네이버 광고센터

    # ── 정부 부처 (정부24 통합인증센터 SSO 사용 다수) ───────────────────
    "moef.go.kr": "https://www.moef.go.kr/com/cmm/EgovLoginUsr.do",
    "mois.go.kr": "https://www.mois.go.kr/frt/sub/a09/cms/screen.do",
    "mofa.go.kr": "https://www.mofa.go.kr/www/etc/login.do",
    "mnd.go.kr": "https://www.mnd.go.kr/cop/ui/uiAffairInquryLogin.do",
    "moe.go.kr": "https://www.moe.go.kr/cmm/uss/login.do",
    "msit.go.kr": "https://www.msit.go.kr/cms/log/log/login_a.jsp",
    "mcst.go.kr": "https://www.mcst.go.kr/kor/s_member/member/login.jsp",
    "mafra.go.kr": "https://www.mafra.go.kr/login/index.do",
    "motie.go.kr": "https://www.motie.go.kr/kor/login/login.do",
    "mohw.go.kr": "https://www.mohw.go.kr/menu.es?mid=a10101000000",
    "me.go.kr": "https://www.me.go.kr/home/web/main.do",
    "mogef.go.kr": "https://www.mogef.go.kr/cs/lgn/cs_lgn_f001.do",
    "mof.go.kr": "https://www.mof.go.kr/login/login.do",
    "mss.go.kr": "https://www.mss.go.kr/site/smba/main.do",
    "mpm.go.kr": "https://www.mpm.go.kr/mpm/main/login/login.do",
    "mfds.go.kr": "https://www.mfds.go.kr/cm/login.do",
    "kostat.go.kr": "https://kostat.go.kr/userLoginInput.es",
    "mma.go.kr": "https://www.mma.go.kr/login/login.do",
    "pps.go.kr": "https://www.pps.go.kr/kor/login/login.do",
    "kepco.co.kr": "https://cyber.kepco.co.kr/ckepco/front/jsp/Member/A/JMA0050.jsp",

    # ── 부동산 ────────────────────────────────────────────────────────
    "rt.molit.go.kr": "https://rt.molit.go.kr/login.do",
    "realtyprice.kr": "https://www.realtyprice.kr/notice/login/login.htm",
    "k-apt.go.kr": "https://www.k-apt.go.kr/cmmn/login.do",

    # ── 특허 ─────────────────────────────────────────────────────────
    "kipo.go.kr": "https://www.kipo.go.kr/ko/MainApp",
    "kipris.or.kr": "https://www.kipris.or.kr/khome/main.do",

    # ── 자동차 ────────────────────────────────────────────────────────
    "kotsa.or.kr": "https://www.kotsa.or.kr/portal/login/loginMain.do",
    "encar.com": "https://www.encar.com/index.do",

    # ── 채용 ─────────────────────────────────────────────────────────
    "saramin.co.kr": "https://www.saramin.co.kr/zf_user/auth",
    "jobkorea.co.kr": "https://www.jobkorea.co.kr/Login",
    "wanted.co.kr": "https://www.wanted.co.kr/sign_in",
    "incruit.com": "https://www.incruit.com/login",

    # ── 협업/메일 ─────────────────────────────────────────────────────
    "slack.com": "https://slack.com/signin",
    "notion.so": "https://www.notion.so/login",
    "zoom.us": "https://zoom.us/signin",
    "outlook.live.com": "https://login.live.com/",
    "mail.naver.com": "https://www.naver.com/",
    "mail.daum.net": "https://logins.daum.net/accounts/loginform.do",
    "mail.google.com": "https://accounts.google.com/ServiceLogin",

    # ── 금융 추가 ─────────────────────────────────────────────────────
    "krx.co.kr": "https://www.krx.co.kr/main/main.jsp",
    "kdic.or.kr": "https://www.kdic.or.kr/customer/login.do",
    "ccrs.or.kr": "https://www.ccrs.or.kr/main/index.do",
    "kftc.or.kr": "https://www.kftc.or.kr/kftc/data/EgovkftcSubLogin.do",
}


def get_known_login_url(domain: str) -> str | None:
    """도메인의 알려진 로그인 URL 반환."""
    if not domain:
        return None
    d = domain.lower().lstrip("www.")
    # 정확 매칭
    if d in KNOWN_LOGIN_URLS:
        return KNOWN_LOGIN_URLS[d]
    # www 포함
    if f"www.{d}" in KNOWN_LOGIN_URLS:
        return KNOWN_LOGIN_URLS[f"www.{d}"]
    # 부분 매칭 (서브도메인)
    for key, url in KNOWN_LOGIN_URLS.items():
        if key in d or d in key:
            return url
    return None
