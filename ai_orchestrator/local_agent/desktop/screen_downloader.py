"""화면 인식 기반 카카오 파일 자동 다운로드.

동작 원리:
1. 앱 창 캡처
2. 다운로드 가능한 파일/사진 영역 탐지 (이미지 템플릿 매칭 또는 색상 패턴)
3. 해당 위치에 마우스 올리기 → 다운로드 버튼 출현 대기 → 클릭
4. 저장 다이얼로그 처리 (Enter 또는 기본 경로 확정)
"""
from __future__ import annotations

import time
from pathlib import Path

import pyautogui
import psutil

try:
    import uiautomation as auto
    _UIA_OK = True
except ImportError:
    _UIA_OK = False

from PIL import Image, ImageGrab
import numpy as np

pyautogui.FAILSAFE = True  # 마우스를 좌상단으로 이동하면 중단
pyautogui.PAUSE = 0.3      # 각 액션 사이 기본 딜레이

TEMPLATE_DIR = Path(__file__).parent / "_templates"
TEMPLATE_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────
# 창 탐색
# ──────────────────────────────────────────────

def _get_window(process_name: str):
    if not _UIA_OK:
        return None
    pids = {p.info["pid"] for p in psutil.process_iter(["pid", "name"])
            if process_name.lower() in (p.info.get("name") or "").lower()}
    if not pids:
        return None
    desktop = auto.GetRootControl()
    for w in desktop.GetChildren():
        try:
            if w.ProcessId in pids and (w.Name or "").strip():
                return w
        except Exception:
            pass
    return None


def _window_rect(process_name: str) -> tuple[int, int, int, int] | None:
    """(left, top, width, height) 또는 None."""
    w = _get_window(process_name)
    if not w:
        return None
    try:
        r = w.BoundingRectangle
        return r.left, r.top, r.right - r.left, r.bottom - r.top
    except Exception:
        return None


def _activate_window(process_name: str) -> bool:
    w = _get_window(process_name)
    if not w:
        return False
    try:
        w.SetActive()
        time.sleep(0.5)
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────
# 화면 캡처
# ──────────────────────────────────────────────

def capture_window(process_name: str) -> Image.Image | None:
    rect = _window_rect(process_name)
    if not rect:
        return None
    _activate_window(process_name)
    return pyautogui.screenshot(region=rect)


# ──────────────────────────────────────────────
# 템플릿 매칭 (PIL 기반)
# ──────────────────────────────────────────────

def _find_template(haystack: Image.Image, template: Image.Image,
                   threshold: float = 0.85) -> list[tuple[int, int]]:
    """템플릿 이미지가 haystack 내 어디에 있는지 좌표 목록 반환."""
    hay = np.array(haystack.convert("RGB"), dtype=np.float32)
    tmpl = np.array(template.convert("RGB"), dtype=np.float32)
    th, tw = tmpl.shape[:2]
    hh, hw = hay.shape[:2]

    results = []
    # 슬라이딩 윈도 (작은 이미지에만 적합, 큰 화면엔 느림)
    # 실용적 크기 제한
    if tw > hw or th > hh:
        return results

    for y in range(0, hh - th, 2):
        for x in range(0, hw - tw, 2):
            patch = hay[y:y + th, x:x + tw]
            diff = np.abs(patch - tmpl).mean()
            score = 1.0 - diff / 255.0
            if score >= threshold:
                results.append((x + tw // 2, y + th // 2))

    # 중복 제거 (가까운 좌표 병합)
    merged: list[tuple[int, int]] = []
    for pt in results:
        if not any(abs(pt[0] - m[0]) < tw and abs(pt[1] - m[1]) < th for m in merged):
            merged.append(pt)
    return merged


def find_template_on_screen(template_path: Path,
                             process_name: str,
                             threshold: float = 0.85) -> list[tuple[int, int]]:
    """화면(앱 창) 내 템플릿 위치를 절대 좌표로 반환."""
    if not template_path.exists():
        return []
    rect = _window_rect(process_name)
    if not rect:
        return []
    screen = capture_window(process_name)
    if not screen:
        return []
    template = Image.open(template_path)
    rel_pts = _find_template(screen, template, threshold)
    # 창 좌표 → 절대 화면 좌표
    ox, oy = rect[0], rect[1]
    return [(ox + x, oy + y) for x, y in rel_pts]


# ──────────────────────────────────────────────
# 다운로드 실행 로직
# ──────────────────────────────────────────────

def _hover_and_wait_download_btn(abs_x: int, abs_y: int,
                                  hover_duration: float = 1.0) -> tuple[int, int] | None:
    """파일 위에 마우스를 올려 다운로드 버튼이 나타나면 그 좌표 반환."""
    pyautogui.moveTo(abs_x, abs_y, duration=0.4)
    time.sleep(hover_duration)
    # 다운로드 버튼 템플릿 재탐지 (hover 후 UI 변경)
    # 없으면 None
    return None  # 템플릿 없을 때 fallback: 우클릭 메뉴 사용


def _right_click_download(abs_x: int, abs_y: int,
                           process_name: str) -> bool:
    """파일에 우클릭 → '다운로드' 또는 '저장' 메뉴 클릭."""
    pyautogui.rightClick(abs_x, abs_y)
    time.sleep(0.8)

    # 우클릭 메뉴에서 '저장' 또는 '다운로드' 텍스트 탐색 (UIA)
    if not _UIA_OK:
        return False
    try:
        desktop = auto.GetRootControl()
        # 메뉴 항목 탐색
        for w in desktop.GetChildren():
            cls = (w.ClassName or "").lower()
            if "menu" in cls or "popup" in cls:
                for item in w.GetChildren():
                    name = (item.Name or "").strip()
                    if any(k in name for k in ("저장", "다운로드", "Save", "Download")):
                        item.Click()
                        time.sleep(1.0)
                        return True
    except Exception:
        pass
    # 메뉴 닫기
    pyautogui.press("escape")
    return False


def _handle_save_dialog(default_path: Path | None = None) -> bool:
    """저장 다이얼로그 처리 — Enter로 기본 경로 확정."""
    time.sleep(0.5)
    if not _UIA_OK:
        pyautogui.press("enter")
        return True
    try:
        desktop = auto.GetRootControl()
        for w in desktop.GetChildren():
            name = (w.Name or "").lower()
            cls = (w.ClassName or "").lower()
            if any(k in name for k in ("저장", "save", "다른 이름")) or \
               any(k in cls for k in ("dialog", "filedialog")):
                if default_path:
                    # 경로 입력창 찾아서 입력
                    edit = w.EditControl(searchDepth=10)
                    if edit.Exists(maxSearchSeconds=1):
                        edit.SetFocus()
                        pyautogui.hotkey("ctrl", "a")
                        pyautogui.write(str(default_path), interval=0.02)
                pyautogui.press("enter")
                return True
    except Exception:
        pass
    pyautogui.press("enter")
    return True


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

class KakaoScreenDownloader:
    """화면 인식 기반 카카오 파일 다운로더."""

    KAKAOWORK = "Kakaowork.exe"
    KAKAOTALK = "KakaoTalk.exe"

    def __init__(self, save_dir: Path | None = None):
        self.save_dir = save_dir or (Path.home() / "Downloads" / "kakao_auto")
        self.save_dir.mkdir(parents=True, exist_ok=True)

    # ── 템플릿 저장 (최초 1회, 사용자가 직접 화면 확인 후 실행) ──

    def save_template_from_region(self, name: str,
                                   x: int, y: int, w: int, h: int) -> Path:
        """화면의 특정 영역을 템플릿으로 저장."""
        img = pyautogui.screenshot(region=(x, y, w, h))
        path = TEMPLATE_DIR / f"{name}.png"
        img.save(path)
        print(f"템플릿 저장: {path}")
        return path

    def capture_and_show(self, app: str = "kakaowork") -> Path | None:
        """현재 앱 화면 캡처 후 저장 (디버그용)."""
        process = self.KAKAOWORK if "work" in app.lower() else self.KAKAOTALK
        img = capture_window(process)
        if not img:
            return None
        from datetime import datetime
        out = Path(__file__).parent.parent.parent.parent / \
              "data" / "reports" / "local_agent" / \
              f"screen_{app}_{datetime.now().strftime('%H%M%S')}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
        return out

    # ── 다운로드 메서드 ──

    def download_by_template(self, template_name: str,
                              app: str = "kakaowork",
                              max_items: int = 5) -> int:
        """템플릿 이미지와 일치하는 파일/사진 클릭 다운로드.

        반환: 다운로드 시도 횟수
        """
        process = self.KAKAOWORK if "work" in app.lower() else self.KAKAOTALK
        template_path = TEMPLATE_DIR / f"{template_name}.png"

        _activate_window(process)
        pts = find_template_on_screen(template_path, process)
        if not pts:
            print(f"  템플릿 '{template_name}' 미발견")
            return 0

        count = 0
        for abs_x, abs_y in pts[:max_items]:
            print(f"  클릭: ({abs_x}, {abs_y})")
            ok = _right_click_download(abs_x, abs_y, process)
            if ok:
                _handle_save_dialog()
                count += 1
                time.sleep(1.0)
        return count

    def download_last_file(self, app: str = "kakaowork") -> bool:
        """채팅방의 마지막(가장 최근) 파일/사진 다운로드.

        전략:
        1. 앱 창 하단 영역에서 파일 영역 탐지
        2. 마우스 올리기 → 다운로드 버튼 클릭
        3. 없으면 우클릭 → 저장
        """
        process = self.KAKAOWORK if "work" in app.lower() else self.KAKAOTALK
        rect = _window_rect(process)
        if not rect:
            print(f"  {process} 창 없음")
            return False

        _activate_window(process)
        ox, oy, ow, oh = rect

        # 채팅 영역 하단 1/3에서 파일 탐지 시도
        # 카카오워크: 우측 70% 영역이 채팅
        chat_x = ox + int(ow * 0.3)
        chat_y = oy + int(oh * 0.5)
        chat_w = int(ow * 0.7)
        chat_h = int(oh * 0.4)

        # 채팅 영역 캡처
        chat_img = pyautogui.screenshot(region=(chat_x, chat_y, chat_w, chat_h))

        # 파일 아이콘 패턴 탐지 (템플릿 있으면 사용)
        dl_tmpl = TEMPLATE_DIR / "download_btn.png"
        file_tmpl = TEMPLATE_DIR / "file_icon.png"
        photo_tmpl = TEMPLATE_DIR / "photo_area.png"

        found = False
        for tmpl_path in (dl_tmpl, file_tmpl, photo_tmpl):
            if not tmpl_path.exists():
                continue
            tmpl = Image.open(tmpl_path)
            pts = _find_template(chat_img, tmpl)
            if pts:
                # 절대 좌표로 변환
                ax, ay = pts[0]
                abs_x = chat_x + ax
                abs_y = chat_y + ay
                ok = _right_click_download(abs_x, abs_y, process)
                if ok:
                    _handle_save_dialog()
                    found = True
                break

        if not found:
            print("  템플릿 미발견 — 화면 캡처 후 템플릿 등록이 필요합니다")
            print("  scripts/capture_kakao_screen.py 실행 후 템플릿을 등록하세요")
        return found

    def download_all_visible(self, app: str = "kakaowork",
                              file_types: list[str] | None = None) -> int:
        """화면에 보이는 모든 파일/사진 다운로드.

        file_types: ["photo", "file", "video"] 중 선택 (None=전체)
        """
        templates = []
        if file_types is None or "photo" in file_types:
            templates.append("photo_area")
        if file_types is None or "file" in file_types:
            templates.append("file_icon")

        process = self.KAKAOWORK if "work" in app.lower() else self.KAKAOTALK
        total = 0
        for tmpl in templates:
            total += self.download_by_template(tmpl, app)
        return total

    def register_template_interactive(self, name: str) -> None:
        """사용자가 화면에서 영역을 직접 선택해 템플릿으로 저장.

        3초 후 마우스 드래그 영역을 캡처합니다.
        """
        print(f"3초 후 '{name}' 템플릿 영역을 캡처합니다...")
        print("캡처할 UI 요소(다운로드 버튼, 파일 아이콘 등)에 마우스를 올려두세요.")
        time.sleep(3)
        x, y = pyautogui.position()
        # 마우스 위치 주변 60x60 영역 캡처
        img = pyautogui.screenshot(region=(x - 30, y - 30, 60, 60))
        path = TEMPLATE_DIR / f"{name}.png"
        img.save(path)
        print(f"템플릿 저장 완료: {path} (중심: {x},{y})")
