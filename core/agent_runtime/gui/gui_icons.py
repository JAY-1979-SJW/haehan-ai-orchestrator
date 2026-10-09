"""GUI 아이콘 / spinner / sparkline — PIL 동적 생성.

unicode glyph 가 우선 (의존성 ↓). PIL 은 sparkline + 라운드 dot 만.
"""

from __future__ import annotations

from collections.abc import Sequence

# ── 사이드바 아이콘 (unicode glyph) ──────────────────────────────

SIDEBAR_ICONS = {
    "dashboard": "⌂",
    "registration": "◆",
    "logs": "▦",
    "settings": "⚙",
    "help": "ⓘ",
}

PAGE_TITLES = {
    "dashboard": "Dashboard",
    "registration": "Registration",
    "logs": "Logs",
    "settings": "Settings",
}


# ── status dot (소형 PIL 원) ────────────────────────────────────


def make_dot(color: str = "#10B981", size: int = 12, *, alpha: float = 1.0):
    """작은 색 원 PIL Image — 상태 dot 용."""
    try:
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001 - PIL 미설치/렌더링 실패 시 아이콘 생성 함수(make_dot/make_tray_icon/make_sparkline/make_spinner_frame)가 None을 반환 — 화면표시 실패일 뿐 데이터나 보안에 영향 없음.
        return None
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r, g, b = _hex_to_rgb(color)
    a = max(0, min(255, int(255 * alpha)))
    d.ellipse((0, 0, size - 1, size - 1), fill=(r, g, b, a))
    return img


def make_tray_icon(color: str = "#10B981", size: int = 64):
    """트레이 아이콘 — 색 원."""
    try:
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001 - PIL 미설치/렌더링 실패 시 아이콘 생성 함수(make_dot/make_tray_icon/make_sparkline/make_spinner_frame)가 None을 반환 — 화면표시 실패일 뿐 데이터나 보안에 영향 없음.
        return None
    img = Image.new("RGB", (size, size), (15, 17, 21))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, size - 6, size - 6), fill=color, outline="#22272F")
    return img


def _hex_to_rgb(hexc: str) -> tuple[int, int, int]:
    h = hexc.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ── sparkline ───────────────────────────────────────────────────


def make_sparkline(  # noqa: PLR0913 - 공개 GUI 헬퍼 keyword-only 시그니처 유지
    values: Sequence[float],
    *,
    width: int = 240,
    height: int = 36,
    line_color: str = "#6366F1",
    fill_color: str = "#6366F1",
    fill_alpha: int = 50,
    bg: str = "#1C2129",
):
    """heartbeat sparkline. PIL ImageTk 호환 PNG 반환."""
    try:
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001 - PIL 미설치/렌더링 실패 시 아이콘 생성 함수(make_dot/make_tray_icon/make_sparkline/make_spinner_frame)가 None을 반환 — 화면표시 실패일 뿐 데이터나 보안에 영향 없음.
        return None
    img = Image.new("RGBA", (width, height), (*_hex_to_rgb(bg), 255))
    d = ImageDraw.Draw(img)
    if not values:
        return img
    vals = list(values)
    lo = min(vals)
    hi = max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pad_x = 4
    pad_y = 4
    usable_w = width - pad_x * 2
    usable_h = height - pad_y * 2
    pts = []
    for i, v in enumerate(vals):
        x = pad_x + (i / max(n - 1, 1)) * usable_w
        y = pad_y + (1 - (v - lo) / rng) * usable_h
        pts.append((x, y))
    # 채우기 다각형
    fill_poly = pts + [(pts[-1][0], height - pad_y), (pts[0][0], height - pad_y)]  # noqa: RUF005 - sparkline 채우기 다각형 좌표 리스트 결합 — 성능/보안과 무관한 스타일 제안, 로컬 리스트 결합일 뿐
    r, g, b = _hex_to_rgb(fill_color)
    d.polygon(fill_poly, fill=(r, g, b, fill_alpha))
    # 선
    if len(pts) >= 2:
        d.line(pts, fill=line_color, width=2)
    return img


# ── spinner (frame) ────────────────────────────────────────────


def make_spinner_frame(angle_deg: int = 0, *, size: int = 16, color: str = "#818CF8", bg: str = "#1C2129"):
    """회전 spinner 한 프레임. after(80ms) 마다 angle+30."""
    try:
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001 - PIL 미설치/렌더링 실패 시 아이콘 생성 함수(make_dot/make_tray_icon/make_sparkline/make_spinner_frame)가 None을 반환 — 화면표시 실패일 뿐 데이터나 보안에 영향 없음.
        return None
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 12 segments, 회전 각에 따라 alpha gradient
    cx = cy = size / 2
    r_out = size / 2 - 1
    r_in = r_out - 3
    import math

    base = math.radians(angle_deg)
    for i in range(12):
        a = base + math.radians(i * 30)
        a2 = a + math.radians(20)
        alpha = int(255 * (1.0 - (i / 12)))
        cr, cg, cb = _hex_to_rgb(color)
        x1 = cx + r_in * math.cos(a)
        y1 = cy + r_in * math.sin(a)
        x2 = cx + r_out * math.cos(a2)
        y2 = cy + r_out * math.sin(a2)
        d.line([(x1, y1), (x2, y2)], fill=(cr, cg, cb, alpha), width=2)
    return img
