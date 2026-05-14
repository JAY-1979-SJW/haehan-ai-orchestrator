"""웹 자동화 공통 페이지 헬퍼.

모든 웹 접속 스크립트에서 import해서 사용.

기본 패턴:
    page_goto(page, url)                              # 이동
    page_goto_wait(page, url, selector)               # 이동 후 목표 요소 등장 즉시 진행
    page_wait_visible(page, selector)                 # 요소 렌더 확인
    page_wait_click(page, selector)                   # 요소 대기 → 클릭 → 에러 감지
    page_wait_type(page, selector, text)              # 요소 대기 → 입력 → 값 검증
    page_wait_nav(page, url_pattern)                  # URL 전환 확인
    page_click_then_wait(page, click_sel, wait_sel)   # 클릭 → 결과 요소 대기 + 에러 경쟁
    page_check_error(page)                            # 에러 메시지 출현 확인

통합 감시 패턴 (입력 → 서버 반영 → UI 반영 완전 검증):
    page_watch_network(page, url_pattern)             # 컨텍스트: 네트워크 요청 감시 시작
    page_watch_dom(page, selector)                    # 컨텍스트: DOM 변화 감시 시작
    page_poll_until(page, selector, check_fn)         # 조건 충족까지 주기적 폴링
    page_submit_and_verify(page, ...)                 # 통합: 제출 → 네트워크+DOM+폴링 3중 검증
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Generator

from playwright.sync_api import Page, Request, Response
from scripts.logger import get_logger

log = get_logger(__name__)

# 공통 에러 메시지 셀렉터
_ERROR_SELECTORS = (
    '[role="alert"], .error-message, .mat-error, '
    '.cfc-error, [class*="error"]:not([class*="no-error"]), '
    'snack-bar-container, .toast-error'
)

# 자동 팝업 처리 활성화 플래그 (환경변수/명시적 비활성화 가능)
_AUTO_POPUP_HANDLE = True


def disable_auto_popup_handling() -> None:
    """page_goto() 자동 팝업 처리 비활성화 (테스트 등 특수 경우)."""
    global _AUTO_POPUP_HANDLE
    _AUTO_POPUP_HANDLE = False


def enable_auto_popup_handling() -> None:
    global _AUTO_POPUP_HANDLE
    _AUTO_POPUP_HANDLE = True


def _safe_auto_popup(page: Page) -> None:
    """페이지 이동 후 팝업 자동 처리 — 실패해도 본 작업 영향 없음."""
    if not _AUTO_POPUP_HANDLE:
        return
    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except Exception as e:
        log.debug("자동 팝업 처리 실패 (무시): %s", e)


# 중요작업 자동 로깅용 URL 패턴 — specific-first 매칭 (긴 키워드 우선)
_CRITICAL_SITE_PATTERNS = {
    # ── 금융 ─────────────────────────────────────────────────────────
    "BANK_VISIT": [
        # 1금융권
        "hanabank.com", "kbstar.com", "shinhan.com", "wooribank.com",
        "nonghyup.com", "nhbank.com", "ibk.co.kr", "kdb.co.kr",
        "epostbank.go.kr", "knbank.co.kr", "busanbank.co.kr",
        "dgb.co.kr", "jbbank.co.kr", "kjbank.com", "suhyup-bank.com",
        "citibank.co.kr", "standardchartered.co.kr", "scbk.co.kr",
        # 인터넷전문은행
        "kakaobank.com", "kbanknow.com", "tossbank.com",
        # 증권
        "kiwoom.com", "miraeasset.com", "mysamsungpop.com",
    ],
    "CARD_VISIT": [
        "samsungcard.com", "shinhancard.com", "hyundaicard.com", "lottecard.co.kr",
        "kbcard.com", "hanacard.co.kr", "nhcard.co.kr", "wooricard.com",
        "citicard.co.kr", "card-bccard.com", "bccard.com",
        "ibki.co.kr",
    ],
    "INSURANCE_VISIT": [
        # 생명/손해보험
        "samsungfire.com", "kbinsure.co.kr", "hyundaimarine.com",
        "dblife.co.kr", "samsunglife.com", "hanwhalife.com",
        "kyobo.co.kr", "miraeassetlife.com", "shinhanlife.co.kr",
        "lina.co.kr", "metlife.co.kr", "axa.co.kr",
    ],
    "FIN_REGULATOR": [
        "fss.or.kr",              # 금융감독원
        "fsc.go.kr",              # 금융위원회
        "bok.or.kr",              # 한국은행
        "krx.co.kr",              # 한국거래소
        "kdic.or.kr",             # 예금보험공사
        "ccrs.or.kr",             # 신용회복위원회
    ],

    # ── 세무 ─────────────────────────────────────────────────────────
    "TAX_VISIT": [
        "hometax.go.kr",          # 국세청 홈택스
        "nts.go.kr",              # 국세청
        "etax.seoul.go.kr",       # 서울 지방세
        "wetax.go.kr",            # 위택스 (지방세)
        "customs.go.kr",          # 관세청
        "unipass.customs.go.kr",  # 관세 유니패스
        "ftis.or.kr",             # 한국세무사회 전산회계
    ],

    # ── 4대보험 (공공) ────────────────────────────────────────────────
    "SOCIAL_INSURANCE": [
        "nhis.or.kr",             # 국민건강보험
        "hira.or.kr",             # 건강보험심사평가원
        "nps.or.kr",              # 국민연금공단
        "kcomwel.or.kr",          # 근로복지공단 (산재)
        "ei.go.kr",               # 고용보험
        "4insure.or.kr",          # 4대사회보험정보연계센터
        "comwel.or.kr",           # 산재/고용 통합
        "sportal.or.kr",          # 사회보험통합징수포털
    ],

    # ── 사법/법무 ─────────────────────────────────────────────────────
    "COURT_VISIT": [
        "scourt.go.kr",           # 대법원
        "iros.go.kr",             # 인터넷등기소
        "ecfs.scourt.go.kr",      # 전자소송
        "efamily.scourt.go.kr",   # 가족관계등록
        "glaw.scourt.go.kr",      # 종합법률정보
        "portal.scourt.go.kr",    # 사법포털
        "klid.or.kr",             # 한국지방세연구원
        "moj.go.kr",              # 법무부
        "kics.go.kr",             # 형사사법포털
        "spo.go.kr",              # 검찰청
        "police.go.kr",           # 경찰청
        "klac.or.kr",             # 대한법률구조공단
        "law.go.kr",              # 국가법령정보
        "easylaw.go.kr",          # 찾기쉬운 생활법령
    ],

    # ── 노동/취업 ──────────────────────────────────────────────────────
    "LABOR_VISIT": [
        "moel.go.kr",             # 고용노동부
        "work.go.kr",             # 워크넷
        "hrd.go.kr",              # HRD-Net
        "q-net.or.kr",            # Q-Net
        "hrdkorea.or.kr",         # 한국산업인력공단
        "minimumwage.go.kr",      # 최저임금위원회
    ],

    # ── 부동산/등기 ────────────────────────────────────────────────────
    "REALESTATE_VISIT": [
        "rt.molit.go.kr",         # 실거래가
        "realtyprice.kr",         # 부동산공시가격
        "kab.co.kr",              # 한국부동산원
        "lh.or.kr",               # 한국토지주택공사
        "k-apt.go.kr",            # 공동주택관리정보시스템
        "molit.go.kr",            # 국토교통부
    ],

    # ── 특허/지적재산 ──────────────────────────────────────────────────
    "IP_VISIT": [
        "kipo.go.kr",             # 특허청
        "kipris.or.kr",           # 키프리스
        "copyright.or.kr",        # 한국저작권위원회
    ],

    # ── 자동차/교통 ────────────────────────────────────────────────────
    "MOTOR_VISIT": [
        "car365.go.kr",           # 자동차365
        "ecar.go.kr",             # 자동차민원
        "koroad.or.kr",           # 도로교통공단
        "kotsa.or.kr",            # 한국교통안전공단
        "ts2020.kr",              # TS교통안전공단
        "molit-pemis.go.kr",      # 자동차 검사
    ],

    # ── 기타 부처/공공 ─────────────────────────────────────────────────
    "GOV_MINISTRY": [
        "moef.go.kr",             # 기획재정부
        "mois.go.kr",             # 행정안전부
        "mofa.go.kr",             # 외교부
        "unikorea.go.kr",         # 통일부
        "mnd.go.kr",              # 국방부
        "moe.go.kr",              # 교육부
        "msit.go.kr",             # 과학기술정보통신부
        "mcst.go.kr",             # 문화체육관광부
        "mafra.go.kr",            # 농림축산식품부
        "motie.go.kr",            # 산업통상자원부
        "mohw.go.kr",             # 보건복지부
        "me.go.kr",               # 환경부
        "mogef.go.kr",            # 여성가족부
        "mof.go.kr",              # 해양수산부
        "mss.go.kr",              # 중소벤처기업부
        "mpm.go.kr",              # 인사혁신처
        "mfds.go.kr",             # 식약처
        "kostat.go.kr",           # 통계청
        "mma.go.kr",              # 병무청
        "pps.go.kr",              # 조달청
        "kepco.co.kr",            # 한국전력
    ],
    "GOV_VISIT": [
        "gov.kr",                 # 정부24
        "minwon.go.kr",           # 민원24
        "epeople.go.kr",          # 국민신문고
        "korea.go.kr",            # 대한민국정부
        "110.go.kr",              # 정부민원안내
        "data.go.kr",             # 공공데이터포털
        "kosaf.go.kr",            # 한국장학재단
        "nice.go.kr",             # 교육행정정보시스템
        "koreapost.go.kr",        # 우정사업본부
        "cw.or.kr",               # 건설근로자공제회
    ],

    # ── 인증 ──────────────────────────────────────────────────────────
    "CERT_USE": [
        "yessign.or.kr", "signkorea.com", "tradesign.net",
        "crosscert.com", "kica.or.kr", "ncfb.or.kr",
        "kftc.or.kr",             # 금융결제원
    ],

    # ── EUM (건설근로자공제회 단말기 관리) ──────────────────────────────
    "EUM_LOGIN": ["eum.cw.or.kr"],

    # ── 포털 ─────────────────────────────────────────────────────────
    "PORTAL_VISIT": [
        "naver.com",              # 네이버 (메인)
        "daum.net",               # 다음
        "nate.com",               # 네이트
        "zum.com",                # 줌
        "google.co.kr",           # 구글 한국
    ],

    # ── 카카오 서비스 ─────────────────────────────────────────────────
    "KAKAO_SERVICE": [
        "kakao.com",
        "kakaocorp.com",
        "kakaotalk.com",
        "kakaobrain.com",
    ],

    # ── 쇼핑몰 (오픈마켓/종합몰) ──────────────────────────────────────
    "SHOPPING_VISIT": [
        "coupang.com",            # 쿠팡
        "11st.co.kr",             # 11번가
        "gmarket.co.kr",          # 지마켓
        "auction.co.kr",          # 옥션
        "interpark.com",          # 인터파크
        "ssg.com",                # SSG닷컴
        "lotteon.com",            # 롯데온
        "wemakeprice.com",        # 위메프
        "tmon.co.kr",             # 티몬
        "kurly.com",              # 마켓컬리
        "oliveyoung.co.kr",       # 올리브영
        "musinsa.com",            # 무신사
        "ably.co.kr",             # 에이블리
        "29cm.co.kr",             # 29cm
        "smartstore.naver.com",   # 네이버 스마트스토어
        "brand.naver.com",        # 네이버 브랜드스토어
    ],

    # ── 대형마트/백화점 ────────────────────────────────────────────────
    "MART_VISIT": [
        "emart.ssg.com", "emart.com",       # 이마트
        "homeplus.co.kr",                    # 홈플러스
        "costco.co.kr",                      # 코스트코
        "shinsegae.com",                     # 신세계
        "ehyundai.com",                      # 현대백화점
        "lotteshopping.com",                 # 롯데백화점
        "galleria.co.kr",                    # 갤러리아백화점
    ],

    # ── 배달 ──────────────────────────────────────────────────────────
    "DELIVERY_VISIT": [
        "baemin.com",                        # 배달의민족
        "yogiyo.co.kr",                      # 요기요
        "coupangeats.com",                   # 쿠팡이츠
    ],

    # ── 중고거래 ──────────────────────────────────────────────────────
    "USED_MARKET": [
        "daangn.com",                        # 당근마켓
        "bunjang.co.kr",                     # 번개장터
        "joongna.com",                       # 중고나라
    ],

    # ── OTT/스트리밍 ───────────────────────────────────────────────────
    "OTT_VISIT": [
        "netflix.com",
        "tving.com",
        "wavve.com",
        "watcha.com",
        "disneyplus.com",
        "youtube.com",
        "twitch.tv",
        "afreecatv.com",
    ],

    # ── 음악 ───────────────────────────────────────────────────────────
    "MUSIC_VISIT": [
        "melon.com",
        "genie.co.kr",
        "bugs.co.kr",
        "vibe.naver.com",
        "spotify.com",
        "music.apple.com",
    ],

    # ── 여행/항공/숙박 ─────────────────────────────────────────────────
    "TRAVEL_VISIT": [
        "koreanair.com",                     # 대한항공
        "flyasiana.com",                     # 아시아나
        "jejuair.net",                       # 제주항공
        "twayair.com",                       # 티웨이
        "airbusan.com",                      # 에어부산
        "easternair.kr",                     # 이스타항공
        "jinair.com",                        # 진에어
        "yanolja.com",                       # 야놀자
        "goodchoice.kr",                     # 여기어때
        "agoda.com", "expedia.co.kr", "booking.com",
        "skyscanner.co.kr", "trip.com",
    ],

    # ── 통신사 ─────────────────────────────────────────────────────────
    "TELCO_VISIT": [
        "sktelecom.com",                     # SKT
        "tworld.co.kr",                      # SKT T월드
        "kt.com",                            # KT
        "olleh.com",                         # KT 올레
        "lguplus.com",                       # LGU+
        "uplus.co.kr",
        "skbroadband.com",                   # SK브로드밴드
    ],

    # ── 결제 ──────────────────────────────────────────────────────────
    "PAYMENT_VISIT": [
        "kakaopay.com",
        "naverpay.com", "pay.naver.com",
        "payco.com",
        "tosspayments.com",
        "samsungpay.com",
        "smilepay.co.kr",
    ],

    # ── 게임 ──────────────────────────────────────────────────────────
    "GAME_VISIT": [
        "nexon.com",
        "ncsoft.com",
        "smilegate.com",
        "krafton.com",
        "netmarble.com",
        "pearlabyss.com",
        "steampowered.com",
        "riotgames.com",
    ],

    # ── 커뮤니티 ──────────────────────────────────────────────────────
    "COMMUNITY_VISIT": [
        "dcinside.com",                      # 디시인사이드
        "ppomppu.co.kr",                     # 뽐뿌
        "ruliweb.com",                       # 루리웹
        "fmkorea.com",                       # 에펨코리아
        "theqoo.net",                        # 더쿠
        "82cook.com",                        # 82쿡
        "instiz.net",                        # 인스티즈
        "humoruniv.com",                     # 웃긴대학
        "todayhumor.co.kr",                  # 오늘의유머
        "clien.net",                         # 클리앙
        "bobaedream.co.kr",                  # 보배드림
    ],

    # ── 부동산 직거래/매물 ─────────────────────────────────────────────
    "REALESTATE_PRIVATE": [
        "zigbang.com",                       # 직방
        "dabangapp.com", "dabang.kr",        # 다방
        "peterpanz.com",                     # 피터팬
        "hogangnono.com",                    # 호갱노노
        "land.naver.com",                    # 네이버 부동산
        "kbland.kr",                         # KB부동산
    ],

    # ── 지도/내비 ──────────────────────────────────────────────────────
    "MAP_NAVIGATION": [
        "map.naver.com",
        "map.kakao.com",
        "tmap.co.kr",
        "maps.google.com",
    ],

    # ── 중고차/자동차 거래 ─────────────────────────────────────────────
    "AUTO_MARKET": [
        "encar.com",                         # 엔카
        "kbchachacha.com",                   # KB차차차
        "cardotcom.co.kr",                   # 카닷컴
        "heydealer.com",                     # 헤이딜러
    ],

    # ── 채용/HR ──────────────────────────────────────────────────────
    "JOB_VISIT": [
        "saramin.co.kr",
        "jobkorea.co.kr",
        "wanted.co.kr",
        "incruit.com",
        "jumpit.co.kr",
    ],

    # ── 메일/협업 ──────────────────────────────────────────────────────
    "MAIL_PORTAL": [
        "mail.naver.com",
        "mail.daum.net",
        "mail.google.com", "gmail.com",
        "outlook.live.com", "outlook.office.com",
        "hiworks.com",                       # Hiworks
    ],
    "COLLAB_VISIT": [
        "slack.com",
        "notion.so",
        "trello.com",
        "asana.com",
        "monday.com",
        "zoom.us",
        "meet.google.com",
    ],

    # ── 교육/학습 ──────────────────────────────────────────────────────
    "EDU_VISIT": [
        "inflearn.com",                      # 인프런
        "fastcampus.co.kr",                  # 패스트캠퍼스
        "coursera.org",
        "udemy.com",
        "edx.org",
        "ebs.co.kr",
        "megastudy.net",
    ],

    # ── SNS ──────────────────────────────────────────────────────────
    "SNS_VISIT": [
        "instagram.com",
        "twitter.com", "x.com",
        "facebook.com",
        "threads.net",
        "tiktok.com",
        "pinterest.com",
        "linkedin.com",
    ],

    # ── 뉴스/언론 ──────────────────────────────────────────────────────
    "NEWS_VISIT": [
        "chosun.com",
        "donga.com",
        "joongang.co.kr",
        "hani.co.kr",
        "khan.co.kr",
        "ytn.co.kr",
        "yna.co.kr",                         # 연합뉴스
        "news.naver.com",
        "news.daum.net",
        "newsis.com",
    ],

    # ── 명품 패션 (글로벌 메종) ─────────────────────────────────────────
    "LUXURY_FASHION": [
        "louisvuitton.com",                  # 루이비통
        "chanel.com",                        # 샤넬
        "hermes.com",                        # 에르메스
        "gucci.com",                         # 구찌
        "prada.com",                         # 프라다
        "dior.com",                          # 디올
        "fendi.com",                         # 펜디
        "celine.com",                        # 셀린느
        "ysl.com",                           # 입생로랑
        "balenciaga.com",                    # 발렌시아가
        "bottegaveneta.com",                 # 보테가
        "valentino.com",                     # 발렌티노
        "loewe.com",                         # 로에베
        "burberry.com",                      # 버버리
        "miumiu.com",                        # 미우미우
        "versace.com",                       # 베르사체
        "dolcegabbana.com",                  # 돌체앤가바나
        "givenchy.com",                      # 지방시
        "armani.com",                        # 아르마니
        "tomford.com",                       # 톰포드
        "moncler.com",                       # 몽클레르
        "stoneisland.com",                   # 스톤아일랜드
        "thombrowne.com",                    # 톰브라운
        "maisonmargiela.com",                # 메종마르지엘라
        "saintlaurent.com",                  # 생로랑
        "chloe.com",                         # 끌로에
    ],

    # ── 명품 플랫폼 (해외/한국) ─────────────────────────────────────────
    "LUXURY_PLATFORM": [
        # 해외
        "net-a-porter.com",                  # 네타포르테
        "mrporter.com",                      # 미스터포터
        "farfetch.com",                      # 파페치
        "mytheresa.com",                     # 마이떼레사
        "matchesfashion.com",                # 매치스
        "ssense.com",                        # 센스
        "24s.com",                           # 24S
        "luisaviaroma.com",                  # 루이자비아로마
        # 한국
        "balaan.co.kr",                      # 발란
        "trenbe.com",                        # 트렌비
        "kream.co.kr",                       # 크림
        "must-it.com",                       # 머스트잇
        "thehandsome.com",                   # 한섬
        "sivillage.com",                     # SI빌리지
    ],

    # ── 명품 시계 ──────────────────────────────────────────────────────
    "WATCH_LUXURY": [
        "rolex.com",                         # 롤렉스
        "omegawatches.com",                  # 오메가
        "patek.com",                         # 파텍필립
        "audemarspiguet.com",                # 오데마피게
        "vacheron-constantin.com",           # 바쉐론콘스탄틴
        "tudorwatch.com",                    # 튜더
        "hublot.com",                        # 위블로
        "panerai.com",                       # 파네라이
        "iwc.com",                           # IWC
        "jaeger-lecoultre.com",              # 예거르쿨트르
        "blancpain.com",                     # 블랑팡
        "breitling.com",                     # 브라이틀링
        "tagheuer.com",                      # 태그호이어
        "longines.com",                      # 론진
        "rado.com",                          # 라도
    ],

    # ── 명품 주얼리 ────────────────────────────────────────────────────
    "JEWELRY_LUXURY": [
        "tiffany.com",                       # 티파니
        "vancleefarpels.com",                # 반클리프앤아펠
        "bulgari.com",                       # 불가리
        "cartier.com",                       # 까르띠에
        "chopard.com",                       # 쇼파드
        "graff.com",                         # 그라프
        "harrywinston.com",                  # 해리윈스턴
        "boucheron.com",                     # 부쉐론
        "piaget.com",                        # 피아제
    ],

    # ── 명품 자동차 ────────────────────────────────────────────────────
    "AUTO_LUXURY": [
        "mercedes-benz.com",                 # 메르세데스벤츠
        "bmw.com",                           # BMW
        "audi.com",                          # 아우디
        "porsche.com",                       # 포르쉐
        "ferrari.com",                       # 페라리
        "lamborghini.com",                   # 람보르기니
        "bentleymotors.com",                 # 벤틀리
        "rolls-roycemotorcars.com",          # 롤스로이스
        "bugatti.com",                       # 부가티
        "astonmartin.com",                   # 애스턴마틴
        "maserati.com",                      # 마세라티
        "mclaren.com",                       # 맥라렌
        "landrover.com",                     # 랜드로버
        "jaguar.com",                        # 재규어
        "lexus.com",                         # 렉서스
        "genesis.com",                       # 제네시스
    ],

    # ── 인테리어/가구 ──────────────────────────────────────────────────
    "INTERIOR_FURNITURE": [
        # 유럽 하이엔드
        "hermanmiller.com",                  # 허먼밀러
        "knoll.com",                         # 놀
        "vitra.com",                         # 비트라
        "cassina.com",                       # 까시나
        "bebitalia.com",                     # B&B 이탈리아
        "molteni.it",                        # 몰테니
        "poliform.it",                       # 폴리폼
        "minotti.com",                       # 미노티
        "kartell.com",                       # 카르텔
        "usm.com",                           # USM 모듈러
        "fritzhansen.com",                   # 프리츠한센
        "muuto.com",                         # 무토
        "hay.dk",                            # HAY
        "flexform.com",                      # 플렉스폼
        "cappellini.com",                    # 카펠리니
        "magisdesign.com",                   # 마지스
        "boconcept.com",                     # 보컨셉
        # 미국
        "westelm.com",                       # 웨스트엘름
        "cb2.com",                           # CB2
        "crateandbarrel.com",                # 크레이트앤배럴
        "rh.com",                            # Restoration Hardware
        "dwr.com",                           # Design Within Reach
        # 라이프스타일
        "westwingnow.com",                   # 웨스트윙
        "houzz.com",                         # 하우즈
        "dwell.com",                         # 드웰
        "ikea.com",                          # 이케아
    ],

    # ── 조명 디자인 ────────────────────────────────────────────────────
    "LIGHTING_DESIGN": [
        "flos.com",                          # 플로스
        "louispoulsen.com",                  # 루이스폴센
        "artemide.com",                      # 아르떼미데
        "foscarini.com",                     # 포스카리니
        "tomdixon.net",                      # 톰딕슨
        "bocci.com",                         # 보치
        "moooi.com",                         # 모오이
        "secto-design.com",                  # 섹토디자인
        "vibia.com",                         # 비비아
        "oluce.com",                         # 올루체
        "santacole.com",                     # 산타콜레
        "davidtrubridge.com",                # 데이비드트루브리지
        "ingo-maurer.com",                   # 잉고마우러
        "nemolighting.com",                  # 네모
        "marset.com",                        # 마르셋
        "leklint.com",                       # 르 클린트
        "fontanaarte.com",                   # 폰타나아르테
        "axolight.it",                       # 악소라이트
        "occhio.com",                        # 오키오
    ],

    # ── 건축/디자인 매체 ────────────────────────────────────────────────
    "DESIGN_MEDIA": [
        "dezeen.com",                        # 디진
        "archdaily.com",                     # 아치데일리
        "designboom.com",                    # 디자인붐
        "frameweb.com",                      # 프레임
        "wallpaper.com",                     # 월페이퍼
        "architecturalrecord.com",
        "domusweb.it",                       # 도무스
        "elledecor.com",                     # 엘르데코
        "ad.com",                            # AD
        "casabellaweb.eu",                   # 카사벨라
    ],

    # ── 미술관/박물관 ──────────────────────────────────────────────────
    "ART_MUSEUM": [
        "moma.org",                          # MoMA 뉴욕현대미술관
        "metmuseum.org",                     # 메트로폴리탄
        "guggenheim.org",                    # 구겐하임
        "tate.org.uk",                       # 테이트
        "louvre.fr",                         # 루브르
        "nationalgallery.org.uk",            # 영국 내셔널갤러리
        "centrepompidou.fr",                 # 퐁피두센터
        "rijksmuseum.nl",                    # 레이크스
        "uffizi.it",                         # 우피치
        "vam.ac.uk",                         # V&A
        "leeum.org",                         # 리움미술관
        "sema.seoul.go.kr",                  # 서울시립미술관
        "mmca.go.kr",                        # 국립현대미술관
    ],

    # ── 예술 경매 ──────────────────────────────────────────────────────
    "ART_AUCTION": [
        "sothebys.com",                      # 소더비
        "christies.com",                     # 크리스티
        "bonhams.com",                       # 본햄스
        "phillips.com",                      # 필립스
        "hindman.com",                       # 힌드먼
        "artsy.net",                         # 아치
        "artnet.com",                        # 아트넷
        "1stdibs.com",                       # 퍼스트딥스
        "k-auction.com",                     # 케이옥션
        "seoulauction.com",                  # 서울옥션
    ],

    # ── 라이프스타일 명품 (식기/홈리빙) ─────────────────────────────────
    "LIFESTYLE_LUXURY": [
        "lecreuset.com",                     # 르크루제
        "staub.com",                         # 스타우브
        "alessi.com",                        # 알레시
        "iittala.com",                       # 이딸라
        "marimekko.com",                     # 마리메꼬
        "wedgwood.com",                      # 웨지우드
        "royaldoulton.com",                  # 로얄돌튼
        "villeroy-boch.com",                 # 빌레로이앤보흐
        "rosenthal.com",                     # 로젠탈
        "lalique.com",                       # 라리끄
        "baccarat.com",                      # 바카라
        "riedel.com",                        # 리델
        "globalknife.com",                   # 글로벌 칼
    ],

    # ── 글로벌 IT/가전 ─────────────────────────────────────────────────
    "TECH_GLOBAL": [
        "apple.com",                         # 애플
        "microsoft.com",                     # 마이크로소프트
        "google.com",                        # 구글
        "amazon.com",                        # 아마존
        "samsung.com",                       # 삼성
        "lg.com",                            # LG
        "dyson.com",                         # 다이슨
        "bose.com",                          # 보스
        "sonos.com",                         # 소노스
        "bang-olufsen.com",                  # 뱅앤올룹슨
        "miele.com",                         # 밀레
        "smeg.com",                          # 스메그
        "kitchenaid.com",                    # 키친에이드
        "nespresso.com",                     # 네스프레소
        "delonghi.com",                      # 드롱기
        "leica-camera.com",                  # 라이카
        "hasselblad.com",                    # 핫셀블라드
    ],

    # ── 향수/뷰티 명품 ─────────────────────────────────────────────────
    "FRAGRANCE_LUXURY": [
        "jomalone.com",                      # 조말론
        "byredo.com",                        # 바이레도
        "lelabofragrances.com",              # 르라보
        "diptyqueparis.com",                 # 딥디크
        "creedboutique.com",                 # 크리드
        "maisonfranciskurkdjian.com",        # 메종프랑시스커정
        "penhaligons.com",                   # 펜할리곤스
        "amorepacific.com",                  # 아모레퍼시픽
        "sulwhasoo.com",                     # 설화수
        "lamer.com",                         # 라메르
        "esteelauder.com",                   # 에스티로더
        "lancome.com",                       # 랑콤
        "shiseido.com",                      # 시세이도
    ],
}

# Fallback 자동 분류 — 명시되지 않은 .go.kr / .or.kr 도메인은 GOV_OTHER로
_GOV_FALLBACK_TLD = (".go.kr", ".or.kr")


# 업무 카테고리 화이트리스트 — 이 카테고리만 critical_logger에 자동 기록
# 그 외(쇼핑/OTT/명품/인테리어/SNS 등)는 사이트맵 수집만, 감사 로그 안 함
WORK_CATEGORIES = {
    # 금융 업무
    "BANK_VISIT", "BANK_LOGIN", "BANK_LOGOUT", "BANK_INQUIRY", "BANK_TRANSFER",
    "CARD_VISIT", "CARD_LOGIN", "CARD_INQUIRY", "CARD_PAYMENT", "CARD_STATEMENT",
    "INSURANCE_VISIT", "INSURANCE_LOGIN", "INSURANCE_CLAIM",
    "FIN_REGULATOR",
    # 세무
    "TAX_VISIT", "TAX_LOGIN", "TAX_FILING", "TAX_PAYMENT", "TAX_REFUND",
    # 4대보험
    "SOCIAL_INSURANCE", "SOCIAL_INSURANCE_FILING",
    # 사법
    "COURT_VISIT", "COURT_FILING", "COURT_CERT_ISSUE",
    # 노동/취업 (업무)
    "LABOR_VISIT", "LABOR_FILING",
    # 부동산/등기 (업무)
    "REALESTATE_VISIT", "REALESTATE_FILING",
    # 특허/지적재산 (업무)
    "IP_VISIT", "IP_FILING",
    # 자동차/교통 (사업용)
    "MOTOR_VISIT", "MOTOR_FILING",
    # 정부/공공
    "GOV_MINISTRY", "GOV_VISIT", "GOV_OTHER",
    "GOV_LOGIN", "GOV_FILING", "GOV_CERT_ISSUE",
    # 인증서
    "CERT_USE", "CERT_INSTALL", "CERT_DELETE", "CERT_COPY", "CERT_RENEW",
    # 업무 메일/협업
    "MAIL_PORTAL", "MAIL_PORTAL_SEND",
    "COLLAB_VISIT",
    # 채용 (사업 운영)
    "JOB_VISIT", "JOB_APPLY",
    # EUM (단말기 임대 본업)
    "EUM_LOGIN", "EUM_INQUIRY", "EUM_REGISTER", "EUM_REMOVE",
}


def is_work_category(category: str | None) -> bool:
    """카테고리가 업무 영역인지 판단."""
    return bool(category) and category in WORK_CATEGORIES


def _detect_critical_category(url: str) -> str | None:
    """URL에서 중요사이트 카테고리 추출.

    1) Specific-first: 더 긴(구체적인) 키워드가 우선 매칭
    2) Fallback: 명시 안 된 .go.kr / .or.kr 은 GOV_OTHER
    예: 'eum.cw.or.kr' > 'cw.or.kr' → EUM_LOGIN 우선
    """
    if not url:
        return None
    url_lower = url.lower()

    matches = []
    for category, keywords in _CRITICAL_SITE_PATTERNS.items():
        for k in keywords:
            if k in url_lower:
                matches.append((len(k), category))

    if matches:
        matches.sort(key=lambda x: -x[0])
        return matches[0][1]

    # Fallback: 미등재 정부/공공 도메인
    for tld in _GOV_FALLBACK_TLD:
        if tld in url_lower:
            return "GOV_OTHER"

    return None


def _safe_critical_log(url: str) -> None:
    """페이지 이동 시 업무 사이트(은행/EUM/세무/사법/공공 등)만 자동 critical 로그.

    업무 외(쇼핑/OTT/명품/인테리어/SNS/뉴스 등)는 사이트맵만 수집하고
    감사 로그는 남기지 않음.
    """
    try:
        category = _detect_critical_category(url)
        if is_work_category(category):
            from scripts.critical_logger import log_critical
            log_critical(category, f"페이지 접속: {url[:120]}", url=url)
    except Exception:
        pass


# 자동 로그인 상태 감지 활성화 플래그
_AUTO_LOGIN_DETECT = True


def disable_auto_login_detection() -> None:
    global _AUTO_LOGIN_DETECT
    _AUTO_LOGIN_DETECT = False


def enable_auto_login_detection() -> None:
    global _AUTO_LOGIN_DETECT
    _AUTO_LOGIN_DETECT = True


def _safe_auto_login_detect(page: Page, url: str) -> None:
    """페이지 이동 후 로그인 상태 자동 감지 + 세션 추적.

    - 모든 사이트(업무/비업무 무관)에서 로그인 상태 자동 감지
    - DB의 site_sessions 테이블에 도메인별 상태 저장
    - 상태 변화(미로그인 → 로그인 또는 반대) 시 critical_logger 기록
      (단, 업무 사이트만 critical 로그, 그 외는 DB만)
    """
    if not _AUTO_LOGIN_DETECT:
        return
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).hostname or ""
        if not domain:
            return

        from scripts.login_detector import detect_login_state
        from scripts.session_tracker import mark_state

        state = detect_login_state(page)
        change = mark_state(domain, state)

        # 상태 변화 시 critical_logger 기록 (업무 사이트만)
        if change.get("changed"):
            try:
                category = _detect_critical_category(url)
                if is_work_category(category):
                    from scripts.critical_logger import log_critical
                    if change["new_logged_in"]:
                        log_critical(
                            "AUTH_SUCCESS",
                            f"로그인 감지: {domain}",
                            domain=domain,
                            user=state.get("user"),
                            score=state.get("score"),
                            url=url[:120],
                        )
                    else:
                        log_critical(
                            "AUTH_FAIL",
                            f"세션 종료/로그아웃: {domain}",
                            domain=domain,
                            url=url[:120],
                        )
            except Exception:
                pass
    except Exception as e:
        log.debug("자동 로그인 감지 실패 (무시): %s", e)


# ── 기본 헬퍼 ─────────────────────────────────────────────────────────

def page_goto(page: Page, url: str, timeout: int = 30000) -> None:
    """이동 → domcontentloaded → 팝업 처리 → 중요사이트 로깅 → 로그인 상태 감지."""
    log.debug("goto: %s", url)
    page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    _safe_auto_popup(page)
    _safe_critical_log(url)
    _safe_auto_login_detect(page, url)


def page_goto_wait(page: Page, url: str, selector: str, timeout: int = 20000) -> bool:
    """이동 후 목표 요소 등장 → 팝업 처리 → 중요사이트 로깅 → 로그인 상태 감지."""
    log.debug("goto_wait: %s | %s", url, selector)
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    _safe_auto_popup(page)
    _safe_critical_log(url)
    _safe_auto_login_detect(page, url)
    return page_wait_visible(page, selector, timeout=timeout)


def _find_frame(page: Page, selector: str):
    """메인 프레임 + 모든 하위 frame에서 selector에 맞는 (frame, element) 반환.

    Google Console처럼 콘텐츠가 iframe 안에 있을 때 자동으로 올바른 frame을 찾는다.
    """
    for frame in page.frames:
        try:
            el = frame.query_selector(selector)
            if el and el.is_visible():
                return frame, el
        except Exception:
            pass
    return None, None


def page_wait_visible(page: Page, selector: str, timeout: int = 20000) -> bool:
    """요소 등장 대기. 메인 프레임 실패 시 iframe 자동 탐색."""
    log.debug("wait_visible: %s", selector)
    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        log.debug("visible OK: %s", selector)
        return True
    except Exception:
        pass

    # iframe 탐색 fallback
    frame, el = _find_frame(page, selector)
    if el:
        log.debug("visible OK (iframe): %s", selector)
        return True
    log.warn("visible 타임아웃: %s", selector)
    return False


def page_check_error(page: Page, timeout: int = 1500) -> str | None:
    """에러 요소가 있으면 텍스트 반환, 없으면 None."""
    try:
        el = page.wait_for_selector(_ERROR_SELECTORS, timeout=timeout, state="visible")
        msg = el.inner_text().strip()
        log.warn("에러 감지: %s", msg)
        return msg or "(에러 텍스트 없음)"
    except Exception:
        return None


def page_wait_click(page: Page, selector: str, timeout: int = 20000) -> bool:
    """요소 대기 → 클릭 → 클릭 직후 에러 감지.

    메인 프레임 실패 시 iframe 탐색 → JS 텍스트 fallback 순으로 시도.
    """
    log.debug("wait_click: %s", selector)
    try:
        el = page.wait_for_selector(selector, timeout=timeout, state="visible")
        el.click()
        log.debug("click OK: %s", selector)
    except Exception:
        # iframe 탐색 fallback
        frame, el = _find_frame(page, selector)
        if el:
            el.click()
            log.debug("click OK (iframe): %s", selector)
        else:
            # JS 텍스트 기반 클릭 fallback
            import re
            texts = re.findall(r'has-text\("([^"]+)"\)', selector)
            if texts:
                # 모든 frame에서 텍스트로 클릭 시도
                clicked = None
                for frame in page.frames:
                    try:
                        clicked = frame.evaluate("""(texts) => {
                            for (const text of texts) {
                                const els = Array.from(document.querySelectorAll(
                                    'button, a, [role="button"], span, div'
                                ));
                                const el = els.find(e =>
                                    e.innerText && e.innerText.trim() === text &&
                                    e.getBoundingClientRect().width > 0
                                );
                                if (el) { el.click(); return text; }
                            }
                            return null;
                        }""", texts)
                        if clicked:
                            break
                    except Exception:
                        pass
                if clicked:
                    log.debug("click JS fallback OK: text='%s'", clicked)
                else:
                    log.warn("click 실패 — 모든 방법 소진: %s", selector)
                    return False
            else:
                log.warn("click 실패 — 요소 없음: %s", selector)
                return False

    err = page_check_error(page, timeout=1500)
    if err:
        log.warn("click 후 에러: %s", err)
        return False
    return True


def page_click_then_wait(
    page: Page,
    click_selector: str,
    wait_selector: str,
    click_timeout: int = 15000,
    wait_timeout: int = 15000,
) -> bool:
    """클릭 → 결과 요소 vs 에러 요소 경쟁 감지. 먼저 나타나는 쪽으로 판단."""
    log.debug("click_then_wait: %s → %s", click_selector, wait_selector)
    try:
        el = page.wait_for_selector(click_selector, timeout=click_timeout, state="visible")
        el.click()
    except Exception:
        log.warn("click_then_wait: 클릭 요소 없음 — %s", click_selector)
        return False

    try:
        appeared = page.wait_for_selector(
            f"{wait_selector}, {_ERROR_SELECTORS}",
            timeout=wait_timeout,
            state="visible",
        )
        tag_class = (appeared.get_attribute("class") or "") + (appeared.get_attribute("role") or "")
        if any(k in tag_class for k in ("error", "alert", "toast")):
            msg = appeared.inner_text().strip()
            log.warn("click_then_wait: 에러 응답 — %s", msg)
            print(f"    ✗ 에러: {msg}")
            return False
        log.debug("click_then_wait: 결과 요소 확인")
        return True
    except Exception:
        log.warn("click_then_wait: 결과 요소 미등장 — %s", wait_selector)
        return False


def page_wait_type(
    page: Page,
    selector: str,
    text: str,
    timeout: int = 15000,
    delay: int = 40,
) -> bool:
    """입력창 대기 → 입력 → input_value() 검증.

    wait_for_selector 실패 시 JS dispatchEvent fallback (Angular Material 등 대응).
    """
    log.debug("wait_type: %s ← '%s'", selector, text[:30])
    el = None
    frame_used = page  # 실제 사용된 frame 추적
    try:
        el = page.wait_for_selector(selector, timeout=timeout, state="visible")
        try:
            el.fill(text)
        except Exception:
            el.click(); el.click(); el.click()
            el.type(text, delay=delay)
    except Exception:
        # iframe 탐색 fallback
        found_frame, found_el = _find_frame(page, selector)
        if found_el:
            el = found_el
            frame_used = found_frame
            try:
                el.fill(text)
            except Exception:
                el.click(); el.click(); el.click()
                el.type(text, delay=delay)
            log.debug("type OK (iframe): %s", selector)
        else:
            # JS dispatchEvent fallback — 모든 frame 순회
            log.debug("type fallback JS: %s", selector)
            js_fill = """([sel, val]) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                el.focus();
                el.value = '';
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.value = val;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
                return el.value;
            }"""
            result = None
            for frame in page.frames:
                try:
                    result = frame.evaluate(js_fill, [selector, text])
                    if result is not None:
                        frame_used = frame
                        break
                except Exception:
                    pass
            if result is None:
                log.warn("type 실패 — JS fallback도 요소 없음: %s", selector)
                return False
        if result != text:
            log.warn("type JS fallback 불일치 — 기대='%s' 실제='%s'", text[:30], str(result)[:30])
            print(f"    ⚠  입력값 불일치: 기대='{text}' 실제='{result}'")
            return False
        log.debug("type JS fallback OK: '%s'", text[:30])
        return True

    # wait_for_selector 성공 경로: input_value()로 검증
    try:
        actual = el.input_value()
        if actual == text:
            log.debug("type 검증 OK: '%s'", text[:30])
            return True
        log.warn("type 검증 실패 — 기대='%s' 실제='%s'", text[:30], actual[:30])
        print(f"    ⚠  입력값 불일치: 기대='{text}' 실제='{actual}'")
        return False
    except Exception:
        log.debug("type 검증 생략 (input_value 미지원): %s", selector)
        return True


def page_wait_nav(page: Page, url_pattern: str, timeout: int = 20000) -> bool:
    """URL 패턴 전환 대기."""
    log.debug("wait_nav: %s", url_pattern)
    try:
        page.wait_for_url(url_pattern, timeout=timeout)
        log.debug("nav OK: %s", url_pattern)
        return True
    except Exception:
        log.warn("nav 타임아웃: %s", url_pattern)
        return False


# ── 통합 감시 레이어 ──────────────────────────────────────────────────

@dataclass
class NetworkLog:
    """네트워크 감시 결과."""
    matched: list[dict] = field(default_factory=list)   # 매칭된 요청 목록
    errors:  list[dict] = field(default_factory=list)   # 4xx/5xx 응답


@contextmanager
def page_watch_network(
    page: Page,
    url_pattern: str = "",
    methods: tuple[str, ...] = ("POST", "PUT", "PATCH", "DELETE"),
) -> Generator[NetworkLog, None, None]:
    """네트워크 요청 감시 컨텍스트.

    with page_watch_network(page, "/api/") as net:
        page_wait_click(page, "#save-btn")
    if net.matched:
        print("서버 요청 확인됨")

    url_pattern: 빈 문자열이면 모든 XHR/fetch 감시
    methods: 감시할 HTTP 메서드 (기본: 쓰기 요청만)
    """
    log_obj = NetworkLog()
    lock = threading.Lock()

    def on_response(response: Response) -> None:
        req = response.request
        if methods and req.method.upper() not in methods:
            return
        if url_pattern and url_pattern not in response.url:
            return
        entry = {
            "method": req.method,
            "url":    response.url,
            "status": response.status,
        }
        with lock:
            if response.status >= 400:
                log_obj.errors.append(entry)
                log.warn("network 에러 응답: %s %s → %d", req.method, response.url, response.status)
            else:
                log_obj.matched.append(entry)
                log.debug("network 요청 확인: %s %s → %d", req.method, response.url, response.status)

    page.on("response", on_response)
    try:
        yield log_obj
    finally:
        page.remove_listener("response", on_response)


@dataclass
class DomChangeLog:
    """DOM 변화 감시 결과."""
    changed: bool = False
    change_count: int = 0
    last_text: str = ""


@contextmanager
def page_watch_dom(
    page: Page,
    selector: str,
) -> Generator[DomChangeLog, None, None]:
    """DOM 변화 감시 컨텍스트 (MutationObserver).

    with page_watch_dom(page, "#result-area") as dom:
        page_wait_click(page, "#save-btn")
        time.sleep(0.5)  # 짧은 반응 대기
    if dom.changed:
        print(f"DOM 변화 확인: {dom.last_text}")
    """
    log_obj = DomChangeLog()

    # MutationObserver를 JS로 주입 — 변화 발생 시 window.__domChanged 플래그 설정
    js_inject = f"""
    (selector) => {{
        window.__domChanged = window.__domChanged || {{}};
        window.__domChanged[selector] = {{ count: 0, text: '' }};
        const target = document.querySelector(selector);
        if (!target) return false;
        const obs = new MutationObserver((mutations) => {{
            window.__domChanged[selector].count += mutations.length;
            window.__domChanged[selector].text = target.innerText || target.value || '';
        }});
        obs.observe(target, {{ childList: true, subtree: true, characterData: true, attributes: true }});
        window.__domObservers = window.__domObservers || {{}};
        window.__domObservers[selector] = obs;
        return true;
    }}
    """
    installed = page.evaluate(js_inject, selector)
    if not installed:
        log.warn("watch_dom: 셀렉터 없음 — %s", selector)

    try:
        yield log_obj
    finally:
        # 감시 결과 수집
        result = page.evaluate(
            "(sel) => window.__domChanged && window.__domChanged[sel]",
            selector
        )
        if result and result.get("count", 0) > 0:
            log_obj.changed = True
            log_obj.change_count = result["count"]
            log_obj.last_text = result.get("text", "")
            log.debug("dom 변화 확인: %s — %d회 변경, 최종='%s'",
                      selector, log_obj.change_count, log_obj.last_text[:50])

        # MutationObserver 해제
        page.evaluate(
            "(sel) => { if (window.__domObservers && window.__domObservers[sel]) "
            "window.__domObservers[sel].disconnect(); }",
            selector
        )


def page_poll_until(
    page: Page,
    selector: str,
    check_fn: Callable[[str], bool],
    interval: float = 0.5,
    timeout: float = 15.0,
) -> bool:
    """조건이 충족될 때까지 주기적으로 폴링.

    check_fn: 요소의 innerText/value를 받아 True/False 반환
    예) page_poll_until(page, "#status", lambda t: "저장됨" in t)
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            el = page.query_selector(selector)
            if el:
                text = ""
                try:
                    text = el.input_value()
                except Exception:
                    text = el.inner_text()
                if check_fn(text):
                    log.debug("poll_until 조건 충족: '%s'", text[:50])
                    return True
        except Exception:
            pass
        time.sleep(interval)

    log.warn("poll_until 타임아웃: %s", selector)
    return False


@dataclass
class VerifyResult:
    """page_submit_and_verify 결과."""
    success: bool = False
    network_ok: bool = False   # 서버 요청 2xx 확인
    dom_changed: bool = False  # UI DOM 변화 확인
    poll_ok: bool = False      # 최종 상태 폴링 확인
    error_msg: str = ""

    def summary(self) -> str:
        parts = []
        parts.append("네트워크 ✓" if self.network_ok  else "네트워크 ✗")
        parts.append("DOM변화 ✓"  if self.dom_changed  else "DOM변화 ✗")
        parts.append("폴링확인 ✓" if self.poll_ok      else "폴링확인 ✗")
        status = "성공" if self.success else "실패"
        return f"[{status}] {' | '.join(parts)}" + (f" | 에러={self.error_msg}" if self.error_msg else "")


def page_submit_and_verify(
    page: Page,
    submit_selector: str,
    *,
    network_pattern: str = "",
    dom_watch_selector: str = "",
    poll_selector: str = "",
    poll_check: Callable[[str], bool] | None = None,
    result_selector: str = "",
    submit_timeout: int = 10000,
    verify_timeout: float = 15.0,
) -> VerifyResult:
    """제출 버튼 클릭 후 3중 검증: 네트워크 요청 + DOM 변화 + 최종 폴링.

    사용 예:
        result = page_submit_and_verify(
            page,
            submit_selector='button:has-text("저장")',
            network_pattern="/api/",          # 서버 요청 URL 패턴
            dom_watch_selector="#result",     # 변화 감시할 DOM 요소
            poll_selector="#status-msg",      # 폴링할 요소
            poll_check=lambda t: "저장됨" in t,
            result_selector=".success-banner",
        )
        print(result.summary())
    """
    result = VerifyResult()

    # DOM 감시 대상 결정
    watch_sel = dom_watch_selector or result_selector or "body"

    with page_watch_network(page, url_pattern=network_pattern) as net:
        with page_watch_dom(page, watch_sel) as dom:
            # 제출 버튼 클릭
            try:
                btn = page.wait_for_selector(submit_selector, timeout=submit_timeout, state="visible")
                btn.click()
                log.debug("submit_and_verify: 클릭 완료 — %s", submit_selector)
            except Exception as e:
                result.error_msg = f"제출 버튼 없음: {e}"
                log.warn("submit_and_verify: %s", result.error_msg)
                return result

            # 결과 요소 vs 에러 경쟁 대기
            if result_selector:
                try:
                    appeared = page.wait_for_selector(
                        f"{result_selector}, {_ERROR_SELECTORS}",
                        timeout=int(verify_timeout * 1000),
                        state="visible",
                    )
                    tag_class = (appeared.get_attribute("class") or "") + (appeared.get_attribute("role") or "")
                    if any(k in tag_class for k in ("error", "alert", "toast")):
                        result.error_msg = appeared.inner_text().strip()
                        log.warn("submit_and_verify: 에러 응답 — %s", result.error_msg)
                        return result
                except Exception:
                    pass

            # DOM 변화 감지를 위해 짧게 대기
            time.sleep(0.8)

    # ── 검증 1: 네트워크 ──────────────────────────────────────────────
    if net.errors:
        result.error_msg = f"서버 에러: {net.errors[0]['status']} {net.errors[0]['url']}"
        log.warn("submit_and_verify: %s", result.error_msg)
        return result
    result.network_ok = bool(net.matched) or not network_pattern
    # network_pattern 미지정 시 감시 생략(항상 통과)

    # ── 검증 2: DOM 변화 ─────────────────────────────────────────────
    result.dom_changed = dom.changed
    if dom.changed:
        log.debug("submit_and_verify: DOM 변화 확인 (%d회)", dom.change_count)

    # ── 검증 3: 폴링 ─────────────────────────────────────────────────
    if poll_selector and poll_check:
        result.poll_ok = page_poll_until(
            page, poll_selector, poll_check,
            interval=0.5, timeout=verify_timeout
        )
    else:
        result.poll_ok = True  # 폴링 기준 미지정 시 생략

    # 에러 메시지 최종 확인
    err = page_check_error(page, timeout=1000)
    if err:
        result.error_msg = err
        return result

    result.success = result.network_ok and (result.dom_changed or not dom_watch_selector) and result.poll_ok
    return result


# ── 실시간 브라우저 상태 감시 ──────────────────────────────────────────

def page_inspect(page: Page, label: str = "") -> dict:
    """현재 페이지의 실제 요소 상태를 실시간으로 수집·출력.

    각 단계 진입 시 호출하면 실제 셀렉터를 파악할 수 있다.
    반환값: { url, title, inputs, buttons, errors }
    """
    tag = f"[inspect{':' + label if label else ''}]"

    result = page.evaluate("""() => {
        const inputs = Array.from(document.querySelectorAll('input:not([type=hidden])'))
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            })
            .map(el => ({
                id:          el.id || '',
                name:        el.name || '',
                type:        el.type || '',
                placeholder: el.placeholder || '',
                value:       el.value || '',
                class:       el.className || '',
            }));

        const buttons = Array.from(document.querySelectorAll(
            'button, [role="button"], input[type=submit], a[role="button"]'
        ))
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && !el.disabled;
            })
            .map(el => ({
                text:  (el.innerText || el.value || '').trim().slice(0, 60),
                id:    el.id || '',
                class: el.className || '',
                role:  el.getAttribute('role') || '',
            }))
            .filter(b => b.text);

        const errors = Array.from(document.querySelectorAll(
            '[role="alert"], .mat-error, .error-message, .cfc-error'
        ))
            .map(el => el.innerText.trim())
            .filter(t => t);

        return { inputs, buttons, errors };
    }""")

    url   = page.url
    title = page.title()

    log.debug("%s URL=%s TITLE=%s", tag, url, title)
    print(f"  {tag} URL: {url}")
    print(f"  {tag} TITLE: {title}")

    inputs  = result.get("inputs", [])
    buttons = result.get("buttons", [])
    errors  = result.get("errors", [])

    if inputs:
        print(f"  {tag} INPUT ({len(inputs)}개):")
        for inp in inputs:
            print(f"    id={inp['id']!r:20} type={inp['type']!r:10} "
                  f"placeholder={inp['placeholder']!r:30} value={inp['value']!r}")
    else:
        print(f"  {tag} INPUT: 없음")

    if buttons:
        print(f"  {tag} BUTTON ({len(buttons)}개):")
        for btn in buttons[:10]:  # 최대 10개만 출력
            print(f"    text={btn['text']!r:40} id={btn['id']!r}")
    else:
        print(f"  {tag} BUTTON: 없음")

    if errors:
        print(f"  {tag} ERROR: {errors}")

    log.debug("%s inputs=%d buttons=%d errors=%d", tag, len(inputs), len(buttons), len(errors))
    return {"url": url, "title": title, "inputs": inputs, "buttons": buttons, "errors": errors}
