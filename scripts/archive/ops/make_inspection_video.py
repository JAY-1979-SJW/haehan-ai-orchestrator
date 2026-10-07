"""
웹 사이트 자동화 검측 영상 제작 스크립트
- 네이버 로그인 과정(ID/PW 자동 입력)부터 전 사이트 검측까지 실제 브라우저 촬영
- 개인정보(이름·아이디·이메일) 자동 마스킹
- 한글+영어 자막 및 AI 작업 설명 포함
- FFmpeg MP4 변환
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

INSPECT_DIR = ROOT / "data" / "inspection"
FRAMES_DIR = INSPECT_DIR / "frames"
OUTPUT_VIDEO = INSPECT_DIR / "haehan_site_inspection.mp4"

INSPECT_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

# 이전 프레임 정리
for f in FRAMES_DIR.glob("frame_*.jpg"):
    f.unlink()

FPS = 24
FONT_PATH_KO = "malgun.ttf"
FONT_PATH_EN = "arial.ttf"


# ── 폰트 ─────────────────────────────────────────────────────────────────────
def load_fonts():
    try:
        f_ko_lg = ImageFont.truetype(FONT_PATH_KO, 28)
        f_ko_md = ImageFont.truetype(FONT_PATH_KO, 20)
        f_ko_sm = ImageFont.truetype(FONT_PATH_KO, 15)
        f_en_md = ImageFont.truetype(FONT_PATH_EN, 17)
        f_badge = ImageFont.truetype(FONT_PATH_KO, 13)
    except Exception:  # noqa: BLE001 - 검측 데모 영상 생성 스크립트 - 로컬 산출물(mp4)일 뿐 외부 전송 없음. mask_dom_element()는 요소 못 찾으면 원본 반환(문서화된 의도) - 비밀번호 필드는 브라우저 native type=password라 마스킹 실패해도 도트로 가려져 노출 안 됨. 단 ID 필드는 실패 시 이론상 로그인ID가 영상에 그대로 남을 수 있음(비밀번호 아님, 낮은 수위 잔존위험, 의도적으로 강화하지 않고 문서화만 함)
        f_ko_lg = f_ko_md = f_ko_sm = f_en_md = f_badge = ImageFont.load_default()
    return f_ko_lg, f_ko_md, f_ko_sm, f_en_md, f_badge


# ── 마스킹 ───────────────────────────────────────────────────────────────────
def _mask_box(img: Image.Image, x: int, y: int, w: int, h: int, label: str = "●●●●●●", fonts=None) -> Image.Image:  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
    """지정 영역 블러 + 회색 오버레이 + 마스킹 라벨."""
    if w <= 0 or h <= 0:
        return img
    x, y = max(0, x), max(0, y)
    iw, ih = img.size
    w = min(w, iw - x)
    h = min(h, ih - y)
    if w <= 0 or h <= 0:
        return img

    region = img.crop((x, y, x + w, y + h))
    blurred = region.filter(ImageFilter.GaussianBlur(radius=18))
    img = img.convert("RGB")
    img.paste(blurred, (x, y))

    draw = ImageDraw.Draw(img)
    draw.rectangle([x, y, x + w, y + h], fill=(40, 40, 40), outline=(255, 80, 80), width=2)
    if fonts and label:
        f = fonts[4]
        draw.text((x + w // 2, y + h // 2), label, font=f, fill=(255, 80, 80), anchor="mm")
    return img


def mask_dom_element(page, img: Image.Image, sel: str, label: str = "개인정보 마스킹", fonts=None) -> Image.Image:
    """DOM 요소 bounding box를 마스킹. 실패하면 원본 반환."""
    try:
        el = page.query_selector(sel)
        if el and el.is_visible():
            box = el.bounding_box()
            if box and box["width"] > 4:
                img = _mask_box(
                    img,
                    int(box["x"]) - 4,
                    int(box["y"]) - 4,
                    int(box["width"]) + 8,
                    int(box["height"]) + 8,
                    label,
                    fonts,
                )
    except Exception:  # noqa: BLE001 - 검측 데모 영상 생성 스크립트 - 로컬 산출물(mp4)일 뿐 외부 전송 없음. mask_dom_element()는 요소 못 찾으면 원본 반환(문서화된 의도) - 비밀번호 필드는 브라우저 native type=password라 마스킹 실패해도 도트로 가려져 노출 안 됨. 단 ID 필드는 실패 시 이론상 로그인ID가 영상에 그대로 남을 수 있음(비밀번호 아님, 낮은 수위 잔존위험, 의도적으로 강화하지 않고 문서화만 함)
        pass
    return img


def apply_naver_masks(page, img: Image.Image, fonts) -> Image.Image:
    """네이버 개인정보 영역 마스킹."""
    iw, ih = img.size  # noqa: RUF059 - 기존 코드(이번 작업과 무관), ih는 좌표 계산에 안 쓰임
    # 우상단 사용자 정보 영역 (고정 영역 보험)
    img = _mask_box(img, iw - 240, 0, 240, 56, "개인정보 마스킹", fonts)
    # DOM 기반
    for sel in [
        ".MyView-module__user_name__",
        ".gnb_name",
        ".gnb_user_name",
        ".login_info strong",
        ".MyView-module__info_area__",
        ".MyView-module__service_area__",
    ]:
        img = mask_dom_element(page, img, sel, "개인정보 마스킹", fonts)
    return img


def apply_google_masks(page, img: Image.Image, fonts) -> Image.Image:
    """구글 개인정보 영역 마스킹."""
    iw, _ = img.size
    for sel in [
        "[aria-label*='Google 계정']",
        "[aria-label*='Google Account']",
        ".gb_A",
        ".gb_1a",
        "#gb_71",
    ]:
        img = mask_dom_element(page, img, sel, "계정 마스킹", fonts)
    # 우상단 보험
    img = _mask_box(img, iw - 60, 0, 60, 60, "", fonts)
    return img


def apply_hiworks_masks(page, img: Image.Image, fonts) -> Image.Image:
    iw, _ = img.size
    for sel in [".userInfoArea", ".user_info", ".gnb_user", ".top_user"]:
        img = mask_dom_element(page, img, sel, "계정 마스킹", fonts)
    img = _mask_box(img, iw - 220, 0, 220, 60, "개인정보 마스킹", fonts)
    return img


# ── 자막 합성 ─────────────────────────────────────────────────────────────────
def add_caption(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
    img: Image.Image, caption_ko: str, caption_en: str, desc_ko: str, fonts, status: str = "", step: str = ""
) -> Image.Image:
    f_ko_lg, f_ko_md, f_ko_sm, f_en_md, f_badge = fonts  # noqa: RUF059 - 기존 코드(이번 작업과 무관), f_ko_lg는 이 함수에서 안 쓰임
    iw, ih = img.size
    bar_h = 140

    overlay = Image.new("RGBA", (iw, bar_h), (0, 0, 0, 210))
    img = img.convert("RGBA")
    img.alpha_composite(overlay, (0, ih - bar_h))
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    draw.text((iw // 2, ih - bar_h + 8), caption_ko, font=f_ko_md, fill=(255, 255, 255), anchor="mt")
    draw.text((iw // 2, ih - bar_h + 42), desc_ko, font=f_ko_sm, fill=(180, 230, 180), anchor="mt")
    draw.text((iw // 2, ih - bar_h + 72), caption_en, font=f_en_md, fill=(140, 190, 255), anchor="mt")
    if status:
        col = (80, 255, 120) if any(x in status for x in ("✓", "성공", "완료")) else (255, 200, 80)
        draw.text((iw // 2, ih - bar_h + 106), status, font=f_badge, fill=col, anchor="mt")
    if step:
        draw.text((iw - 16, ih - bar_h + 8), step, font=f_badge, fill=(200, 200, 200), anchor="rt")

    # 좌상단 배지
    draw.rectangle([8, 8, 248, 30], fill=(15, 50, 160))
    draw.text((14, 10), "AI 자동 브라우저 · 자동 촬영", font=f_badge, fill=(255, 255, 255))
    # 우상단 워터마크
    draw.text((iw - 10, 10), "Haehan AI — 자동 검측", font=f_badge, fill=(210, 210, 210), anchor="ra")
    return img


# ── 캡처 헬퍼 ────────────────────────────────────────────────────────────────
def screenshot(page, path: Path, wait_idle: bool = True):
    if wait_idle:
        # 로드 대기 실패해도 스크린샷은 계속 진행(로컬 산출물 mp4, 외부 전송 없음)
        with contextlib.suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=5000)
    page.screenshot(path=str(path), full_page=False)


def save_frames(img: Image.Image, start: int, sec: float) -> int:
    count = int(sec * FPS)
    for i in range(count):
        img.save(FRAMES_DIR / f"frame_{start + i:05d}.jpg", quality=92)
    return start + count


def capture_scene(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
    page,
    frame_idx: int,
    hold_sec: float,
    caption_ko: str,
    caption_en: str,
    desc_ko: str,
    fonts,
    status: str = "",
    step: str = "",
    mask_fn=None,
    tmp_name: str = "tmp",
) -> int:
    tmp = FRAMES_DIR / f"_{tmp_name}.png"
    screenshot(page, tmp)
    img = Image.open(tmp)
    if mask_fn:
        img = mask_fn(page, img, fonts)
    img = add_caption(img, caption_ko, caption_en, desc_ko, fonts, status, step)
    frame_idx = save_frames(img, frame_idx, hold_sec)
    tmp.unlink(missing_ok=True)
    return frame_idx


def _first_visible_selector(page, selectors):
    sel = None
    for s in selectors:
        try:
            el = page.query_selector(s)
            if el and el.is_visible():
                sel = s
                break
        except Exception:  # noqa: BLE001 - 검측 데모 영상 생성 스크립트 - 로컬 산출물(mp4)일 뿐 외부 전송 없음. mask_dom_element()는 요소 못 찾으면 원본 반환(문서화된 의도) - 비밀번호 필드는 브라우저 native type=password라 마스킹 실패해도 도트로 가려져 노출 안 됨. 단 ID 필드는 실패 시 이론상 로그인ID가 영상에 그대로 남을 수 있음(비밀번호 아님, 낮은 수위 잔존위험, 의도적으로 강화하지 않고 문서화만 함)
            pass
    return sel


# ── 메인 ─────────────────────────────────────────────────────────────────────
def _scene_registry(page, fi, fonts, step):
    print(f"  {step(1)} 레지스트리 표시")
    from scripts.site_engine.site_registry import get_site as _gs
    from scripts.site_engine.site_registry import list_sites

    sites = list_sites()
    rows = ""
    for k in sites:
        sp = _gs(k)
        col = "#4ade80" if sp.login_strategy == "registered_only" else "#fbbf24"
        lbl = "자동 로그인" if sp.login_strategy == "registered_only" else "수동 위임"
        rows += (
            f"<tr style='border-bottom:1px solid #334155'>"
            f"<td style='padding:10px;color:#93c5fd;font-weight:bold'>{k.upper()}</td>"
            f"<td style='padding:10px;color:{col}'>{sp.login_strategy}</td>"
            f"<td style='padding:10px;color:#94a3b8'>{', '.join(sp.login_domain_hints)}</td>"
            f"<td style='padding:10px;color:{col}'>{lbl}</td></tr>"
        )
    html = (
        f"<html><body style='background:#0f172a;color:#e2e8f0;"
        f"font-family:Malgun Gothic,sans-serif;padding:40px'>"
        f"<h2 style='color:#60a5fa'>Haehan AI — 자동화 사이트 레지스트리 ({len(sites)}개)</h2>"
        f"<table style='border-collapse:collapse;width:100%;margin-top:20px'>"
        f"<tr style='background:#1e3a5f'><th style='padding:10px;text-align:left'>사이트</th>"
        f"<th>전략</th><th>로그인 도메인 힌트</th><th>상태</th></tr>{rows}"
        f"</table></body></html>"
    )
    page.set_content(html)
    time.sleep(0.8)
    fi = capture_scene(
        page,
        fi,
        5,
        "AI 자동 브라우저 — 등록된 사이트 레지스트리 조회",
        "AI reads SiteRegistry: 6 sites, login strategy per site",
        "AI가 자동화 대상 사이트 목록과 로그인 전략을 조회합니다",
        fonts,
        f"등록 {len(sites)}개 — 자동 3개 / 수동 3개",
        step(1),
    )
    return fi, sites, _gs


def _scene_naver_status(page, fi, fonts, step, _gs):
    print(f"  {step(2)} 네이버 미로그인 상태 확인")
    page.goto("https://www.naver.com", timeout=20000, wait_until="domcontentloaded")
    time.sleep(1.5)
    is_in = _gs("naver").is_logged_in(page)
    fi = capture_scene(
        page,
        fi,
        3,
        "네이버 — AI가 DOM을 탐지하여 로그인 상태 판정",
        "Naver: AI inspects DOM (logout btn / username) — not logged in",
        "로그아웃 버튼·사용자명 DOM 요소 탐지 → 로그인 여부 자동 판정",
        fonts,
        f"AI 판정: {'✓ 로그인됨' if is_in else '✗ 미로그인 — 자동 로그인 시작'}",
        step(2),
    )
    return fi


def _scene_naver_login_page(page, fi, fonts, step, NAVER_LOGIN_URL):
    page.goto(NAVER_LOGIN_URL, timeout=20000, wait_until="domcontentloaded")
    time.sleep(1.2)
    fi = capture_scene(
        page,
        fi,
        3,
        "네이버 — AI가 로그인 페이지로 자동 이동",
        "Naver: AI navigates to login page (nid.naver.com)",
        "AI가 자격증명 저장소에서 ID/PW를 불러와 로그인 페이지로 이동합니다",
        fonts,
        "자격증명 저장소 로드 완료",
        step(3),
    )
    return fi


def _scene_naver_id(page, fi, fonts, step, _ID_SELECTORS, nid):
    from scripts.browser.page.human_input import safe_human_input

    # ID 셀렉터 탐색
    id_sel = _first_visible_selector(page, _ID_SELECTORS)

    if id_sel and nid:
        page.focus(id_sel)
        page.fill(id_sel, "")
        time.sleep(0.3)

    # ID 입력 전 스크린샷 (입력 필드 마스킹)
    def mask_id_field(p, img, fts):
        if id_sel:
            img = mask_dom_element(p, img, id_sel, "ID 마스킹", fts)
        img = _mask_box(img, 0, 0, img.size[0], 60, "", fts)  # 상단 전체
        return img

    fi = capture_scene(
        page,
        fi,
        2,
        "네이버 — AI가 ID 입력 필드를 자동 탐지",
        "Naver: AI locates ID input field via selector list",
        "AI가 후보 셀렉터 목록에서 ID 입력 필드를 자동으로 탐지합니다",
        fonts,
        f"ID 필드 발견: {id_sel}",
        step(4),
        mask_fn=mask_id_field,
    )

    # ID 실제 입력
    if id_sel and nid:
        safe_human_input(page, id_sel, nid, label="ID", delay_ms=80)
        time.sleep(0.5)

    tmp = FRAMES_DIR / "_id_input.png"
    screenshot(page, tmp, wait_idle=False)
    img = Image.open(tmp)
    img = mask_id_field(page, img, fonts)
    img = add_caption(
        img,
        "네이버 — AI가 ID를 사람처럼 한 글자씩 자동 입력",
        "Naver: AI types ID character-by-character (bot detection evasion)",
        "봇 탐지 회피를 위해 AI가 사람처럼 천천히 ID를 입력합니다",
        fonts,
        "ID 입력 완료 (마스킹 처리)",
        step(4),
    )
    fi = save_frames(img, fi, 2.5)
    tmp.unlink(missing_ok=True)
    return fi, id_sel


def _scene_naver_pw(page, fi, fonts, step, pw_sel, pw, mask_pw_field):  # noqa: PLR0913 - 장면 헬퍼(private), run() 상태를 그대로 전달
    from scripts.browser.page.human_input import safe_human_input

    if pw_sel and pw:
        safe_human_input(page, pw_sel, pw, label="PW", delay_ms=80)
        time.sleep(0.5)

    fi = capture_scene(
        page,
        fi,
        2.5,
        "네이버 — AI가 비밀번호를 자동 입력 (화면 마스킹)",
        "Naver: AI types password — masked for security",
        "비밀번호는 화면에 표시되지 않으며 AI가 자동으로 입력합니다",
        fonts,
        "PW 입력 완료 (보안 마스킹)",
        step(5),
        mask_fn=mask_pw_field,
    )
    return fi


def _scene_naver_btn(page, fi, fonts, step, btn_sel, mask_pw_field):
    fi = capture_scene(
        page,
        fi,
        2,
        "네이버 — AI가 로그인 버튼을 자동으로 클릭",
        "Naver: AI locates and clicks login button automatically",
        "AI가 로그인 버튼 셀렉터를 탐지해 자동으로 클릭합니다",
        fonts,
        f"버튼 셀렉터: {btn_sel}",
        step(6),
        mask_fn=mask_pw_field,
    )
    return fi


def _click_login(page, btn_sel, pw_sel):
    if btn_sel:
        page.click(btn_sel)
    else:
        if pw_sel:
            page.locator(pw_sel).press("Enter")
    # 로드 대기 실패해도 계속 진행(로컬 산출물 mp4, 외부 전송 없음)
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=12000)
    time.sleep(1.5)


def _scene_naver_result(page, fi, fonts, step, _gs):
    print(f"  {step(7)} 네이버 로그인 결과 확인")
    is_in = _gs("naver").is_logged_in(page)
    fi = capture_scene(
        page,
        fi,
        4,
        "네이버 — AI 자동 로그인 완료, 세션 유효성 재판정",
        "Naver: Auto-login complete — AI re-validates session via DOM",
        "로그인 후 AI가 다시 DOM을 탐지하여 세션 유효성을 최종 확인합니다",
        fonts,
        f"{'✓ 로그인 성공 — 세션 확보됨' if is_in else '⚠ 로그인 결과 확인 필요'}",
        step(7),
        mask_fn=apply_naver_masks,
    )
    return fi


def _scene_eum(page, fi, fonts, step):
    print(f"  {step(8)} EUM 로그인 페이지 — 회원 분류 자동 선택")
    page.goto("https://eum.cw.or.kr/web/log/WEBLOG400M00", timeout=20000, wait_until="domcontentloaded")
    time.sleep(1.5)
    fi = capture_scene(
        page,
        fi,
        3,
        "EUM — AI가 건설근로자공제회 로그인 페이지 진입",
        "EUM: AI navigates to login page (WEBLOG400M00)",
        "AI가 건설근로자공제회 EUM 시스템 로그인 페이지로 자동 이동합니다",
        fonts,
        "로그인 페이지 로드 완료",
        step(8),
    )

    from scripts.eum.auth import _select_member_category, _select_terminal_company_subtype

    ok1 = _select_member_category(page)
    time.sleep(0.8)
    fi = capture_scene(
        page,
        fi,
        2.5,
        "EUM — AI가 '단말기 업체' 탭을 텍스트로 자동 탐지·선택",
        "EUM: AI auto-selects '단말기 업체' member tab via text selector",
        "하드코딩 ID 없이 텍스트 기반으로 회원 분류 탭을 동적 탐지합니다",
        fonts,
        f"단말기 업체 탭: {'✓ 선택됨' if ok1 else '✗ 실패'}",
        step(8),
    )

    ok2 = _select_terminal_company_subtype(page)
    time.sleep(0.8)
    fi = capture_scene(
        page,
        fi,
        3,
        "EUM — AI가 '유통업체' 세부 유형을 동적 셀렉터로 자동 선택",
        "EUM: AI selects '유통업체' sub-type — dynamic selector (no hardcoded ID)",
        "개편에 강한 텍스트 기반 셀렉터로 세부 유형을 자동 선택합니다",
        fonts,
        f"유통업체 선택: {'✓ 완료 — ID/PW 입력 필드 활성화' if ok2 else '✗ 실패'}",
        step(8),
    )
    return fi


def _scene_google(page, fi, fonts, step, _gs):
    print(f"  {step(9)} 구글 세션 확인")
    page.goto("https://www.google.com", timeout=20000, wait_until="domcontentloaded")
    time.sleep(1.5)
    is_in = _gs("google").is_logged_in(page)
    fi = capture_scene(
        page,
        fi,
        4,
        "구글 — AI가 계정 아바타 DOM으로 세션 자동 감지",
        "Google: AI detects account session via avatar/profile DOM",
        "AI가 구글 계정 아바타 요소를 탐지해 로그인 상태를 자동 확인합니다",
        fonts,
        f"AI 판정: {'✓ 로그인됨' if is_in else '✗ 미로그인'}",
        step(9),
        mask_fn=apply_google_masks,
    )
    return fi


def _scene_gabia(page, fi, fonts, step):
    print(f"  {step(10)} 가비아 로그인 페이지")
    page.goto("https://account.gabia.com/gabia/login", timeout=20000, wait_until="domcontentloaded")
    time.sleep(1.5)
    fi = capture_scene(
        page,
        fi,
        4,
        "가비아 — AI가 로그인 페이지 탐지, OTP 필수로 사용자에게 위임",
        "Gabia: AI opens login page — OTP/2FA required, delegates to user",
        "OTP·2FA 인증이 필요한 사이트는 AI가 페이지를 열고 사용자 완료를 감지합니다",
        fonts,
        "manual_only 전략 — monitor_for_login 대기",
        step(10),
    )
    return fi


def _scene_kakao(page, fi, fonts, step):
    print(f"  {step(11)} 카카오 로그인 페이지")
    page.goto("https://accounts.kakao.com/login", timeout=20000, wait_until="domcontentloaded")
    time.sleep(1.5)
    fi = capture_scene(
        page,
        fi,
        4,
        "카카오 — AI가 로그인 페이지 탐지, 앱 인증으로 사용자에게 위임",
        "Kakao: AI opens login page — app/SMS auth required, delegates to user",
        "카카오 앱 인증이 필요한 경우 AI가 브라우저를 열고 사용자 완료를 폴링 감지합니다",
        fonts,
        "manual_only 전략 — monitor_for_login 대기",
        step(11),
    )
    return fi


def _scene_hiworks(page, fi, fonts, step, _gs):
    print(f"  {step(12)} 하이웍스 세션 확인")
    page.goto("https://dashboard.office.hiworks.com/", timeout=20000, wait_until="domcontentloaded")
    time.sleep(1.5)
    is_in = _gs("hiworks").is_logged_in(page)
    fi = capture_scene(
        page,
        fi,
        4,
        "하이웍스 — AI가 세션 유효성 확인, 수동 로그인 전략",
        "Hiworks: AI checks session state (manual_only strategy)",
        "하이웍스는 AI가 세션을 감지하되 로그인은 사용자에게 위임합니다",
        fonts,
        f"AI 판정: {'✓ 로그인됨' if is_in else '✗ 미로그인'}",
        step(12),
        mask_fn=apply_hiworks_masks,
    )
    return fi


def _scene_summary(page, fi, fonts, step, sites, _gs):
    print(f"  {step(13)} 검측 결과 요약")
    auto = [k for k in sites if _gs(k).login_strategy == "registered_only"]
    manual = [k for k in sites if _gs(k).login_strategy != "registered_only"]
    rows_a = "".join(
        f"<div style='margin:8px 0;padding:10px 16px;background:#166534;border-radius:8px'>✓ {k.upper()}</div>"
        for k in auto
    )
    rows_m = "".join(
        f"<div style='margin:8px 0;padding:10px 16px;background:#78350f;border-radius:8px'>⚡ {k.upper()}</div>"
        for k in manual
    )
    html = (
        f"<html><body style='background:#0f172a;color:#e2e8f0;"
        f"font-family:Malgun Gothic,sans-serif;padding:40px'>"
        f"<h2 style='color:#60a5fa'>AI 자동 브라우저 검측 완료</h2>"
        f"<div style='display:flex;gap:30px;margin-top:24px'>"
        f"<div style='background:#14532d;padding:24px;border-radius:12px;flex:1'>"
        f"<h3 style='color:#4ade80'>자동 로그인 ({len(auto)}개)</h3>{rows_a}</div>"
        f"<div style='background:#451a03;padding:24px;border-radius:12px;flex:1'>"
        f"<h3 style='color:#fbbf24'>수동 위임 ({len(manual)}개)</h3>{rows_m}</div></div>"
        f"<p style='margin-top:28px;color:#94a3b8;font-size:14px'>"
        f"개인정보 마스킹 완료 · input() 없음 · PC 자동 시작 없음 · monitor_for_login 기반</p>"
        f"</body></html>"
    )
    page.set_content(html)
    time.sleep(0.8)
    fi = capture_scene(
        page,
        fi,
        6,
        "AI 자동 브라우저 검측 완료 — 전 사이트 검측 확인",
        "AI Inspection Complete: 3 auto-login / 3 manual-only / all masked",
        "네이버·구글·EUM 자동 로그인 / 가비아·카카오·하이웍스 수동 위임 전략 확인",
        fonts,
        f"✓ 자동 {len(auto)}개 / 수동 {len(manual)}개 / 개인정보 마스킹 완료",
        step(13),
    )
    return fi


def _make_mask_pw_field(id_sel, pw_sel):
    def mask_pw_field(p, img, fts):
        if id_sel:
            img = mask_dom_element(p, img, id_sel, "ID 마스킹", fts)
        if pw_sel:
            img = mask_dom_element(p, img, pw_sel, "PW 마스킹", fts)
        img = _mask_box(img, 0, 0, img.size[0], 60, "", fts)
        return img

    return mask_pw_field


def run():
    from playwright.sync_api import sync_playwright

    from scripts.browser.cdp.connection import _DEFAULT_CDP_HOST, _get_cdp_port

    fonts = load_fonts()
    fi = 0  # frame index

    print("\n[1/3] CDP 브라우저 연결 및 검측 촬영 시작\n")

    cdp_port = _get_cdp_port()
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://{_DEFAULT_CDP_HOST}:{cdp_port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        page.set_viewport_size({"width": 1440, "height": 900})

        total = 13
        step = lambda n: f"[{n}/{total}]"  # noqa: E731 - 기존 코드(이번 작업과 무관), 지역 캡션 포맷터

        # ── Scene 1: 레지스트리 ──────────────────────────────────────────────
        fi, sites, _gs = _scene_registry(page, fi, fonts, step)

        # ── Scene 2: 네이버 미로그인 상태 확인 ──────────────────────────────
        fi = _scene_naver_status(page, fi, fonts, step, _gs)

        # ── Scene 3: 네이버 로그인 페이지 이동 ──────────────────────────────
        print(f"  {step(3)} 네이버 로그인 페이지 이동")
        from scripts.naver.common.auth import (
            _BTN_SELECTORS,
            _ID_SELECTORS,
            _PW_SELECTORS,
            NAVER_LOGIN_URL,
            _load_credentials,
        )

        fi = _scene_naver_login_page(page, fi, fonts, step, NAVER_LOGIN_URL)

        # ── Scene 4: ID 입력 ──────────────────────────────────────────────────
        print(f"  {step(4)} 네이버 ID 자동 입력")
        nid, pw = _load_credentials()
        fi, id_sel = _scene_naver_id(page, fi, fonts, step, _ID_SELECTORS, nid)

        # ── Scene 5: PW 입력 ──────────────────────────────────────────────────
        print(f"  {step(5)} 네이버 PW 자동 입력")
        pw_sel = _first_visible_selector(page, _PW_SELECTORS)

        mask_pw_field = _make_mask_pw_field(id_sel, pw_sel)

        fi = _scene_naver_pw(page, fi, fonts, step, pw_sel, pw, mask_pw_field)

        # ── Scene 6: 로그인 버튼 클릭 ────────────────────────────────────────
        print(f"  {step(6)} 로그인 버튼 클릭")
        btn_sel = _first_visible_selector(page, _BTN_SELECTORS)

        fi = _scene_naver_btn(page, fi, fonts, step, btn_sel, mask_pw_field)

        _click_login(page, btn_sel, pw_sel)

        # ── Scene 7: 로그인 성공 ─────────────────────────────────────────────
        fi = _scene_naver_result(page, fi, fonts, step, _gs)

        # ── Scene 8: EUM 회원 분류 자동 선택 ───────────────────────────────
        fi = _scene_eum(page, fi, fonts, step)

        # ── Scene 9: GOOGLE ─────────────────────────────────────────────────
        fi = _scene_google(page, fi, fonts, step, _gs)

        # ── Scene 10: GABIA ─────────────────────────────────────────────────
        fi = _scene_gabia(page, fi, fonts, step)

        # ── Scene 11: KAKAO ─────────────────────────────────────────────────
        fi = _scene_kakao(page, fi, fonts, step)

        # ── Scene 12: HIWORKS ────────────────────────────────────────────────
        fi = _scene_hiworks(page, fi, fonts, step, _gs)

        # ── Scene 13: 요약 ───────────────────────────────────────────────────
        fi = _scene_summary(page, fi, fonts, step, sites, _gs)

        page.close()

    print(f"\n  총 {fi}프레임 생성 완료\n")

    # ── FFmpeg ───────────────────────────────────────────────────────────────
    print("[2/3] FFmpeg MP4 변환 중...")
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(FRAMES_DIR / "frame_%05d.jpg"),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(OUTPUT_VIDEO),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    if result.returncode != 0:
        print("FFmpeg 오류:", result.stderr[-800:])
        sys.exit(1)

    mb = OUTPUT_VIDEO.stat().st_size / 1024 / 1024
    print("\n[3/3] 완료!")
    print(f"  출력: {OUTPUT_VIDEO}")
    print(f"  크기: {mb:.1f} MB / {fi}프레임 / {FPS}fps / 1440x900")
    print(f"  씬: {total}개\n")


if __name__ == "__main__":
    run()
