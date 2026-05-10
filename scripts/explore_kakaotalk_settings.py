"""카카오톡 환경설정 — '받은 파일/사진 자동 저장' 옵션 탐지.

카카오톡 메인 창에서 환경설정(Ctrl+S 또는 더보기→환경설정) 진입 후
'자동 다운로드', '자동 저장', '파일 저장 경로' 같은 옵션 탐색.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import uiautomation as auto
import psutil
import pyautogui

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "reports" / "local_agent"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def safe(o, a, d=""):
    try:
        v = getattr(o, a, d); return v() if callable(v) else v
    except Exception: return d


def info(c, depth=0):
    try:
        r = c.BoundingRectangle
        rect = {"l": r.left, "t": r.top, "r": r.right, "b": r.bottom}
    except Exception: rect = {}
    return {
        "depth": depth, "type": safe(c, "ControlTypeName"),
        "name":  safe(c, "Name", "")[:120], "aid": safe(c, "AutomationId", "")[:80],
        "cls":   safe(c, "ClassName", "")[:60], "off": safe(c, "IsOffscreen", False),
        "rect":  rect,
    }


def deep_walk(c, depth=0, max_depth=15):
    if depth >= max_depth: return []
    n = [info(c, depth)]
    if n[0]["off"]: return n
    try: chs = c.GetChildren()
    except Exception: return n
    for ch in chs[:80]: n.extend(deep_walk(ch, depth+1, max_depth))
    return n


def find_kakaotalk():
    pids = {p.info["pid"] for p in psutil.process_iter(["pid","name"])
            if "kakaotalk" in (p.info.get("name") or "").lower()}
    for w in auto.GetRootControl().GetChildren():
        try:
            if w.ProcessId in pids and (w.Name or "").strip(): return w
        except Exception: pass
    return None


def find_settings_window():
    """카카오톡 설정 창 — 별도 윈도우로 뜸 (보통 '환경설정' 이름)."""
    for w in auto.GetRootControl().GetChildren():
        try:
            name = (w.Name or "")
            if any(k in name for k in ("환경설정", "설정", "Settings", "Preferences")):
                return w
        except Exception: pass
    return None


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"kakaotalk_settings_{ts}.json"

    print("=" * 70)
    print("  카카오톡 환경설정 탐지")
    print("=" * 70)

    main_win = find_kakaotalk()
    if not main_win:
        print("⚠ 카카오톡 미실행"); return

    print(f"\n메인 창: {main_win.Name!r} pid={main_win.ProcessId}")
    main_win.SetActive(); time.sleep(0.5)

    # 환경설정 단축키 (Ctrl+S) — 카카오톡 PC의 표준 단축키
    print("\n[1/3] Ctrl+S 로 환경설정 진입 시도")
    pyautogui.hotkey("ctrl", "s")
    time.sleep(2)

    settings = find_settings_window()
    if not settings:
        # 다른 단축키 / 메뉴 진입 시도
        print("  Ctrl+S 실패 — 더보기 메뉴 시도")
        # 카카오톡 메인 좌하단 더보기 버튼 (햄버거)
        # → 환경설정 메뉴 클릭
        # 패스 (사용자가 수동으로 열어주길 기다림)
        print("\n  ⚠ 자동 진입 실패 — 카카오톡에서 직접 환경설정을 여세요 (Ctrl+S)")
        print("  10초 대기...")
        time.sleep(10)
        settings = find_settings_window()

    if not settings:
        print("\n⚠ 설정 창 미발견 — 종료"); return

    print(f"\n[2/3] 설정 창 발견: {settings.Name!r}")
    r = settings.BoundingRectangle
    print(f"  rect=({r.left},{r.top},{r.right},{r.bottom})")

    # 트리 덤프
    print("\n[3/3] 트리 분석 (max_depth=15)")
    tree = deep_walk(settings, max_depth=15)
    print(f"  노드 {len(tree)}개")

    # 자동저장/다운로드 키워드 노드 추출
    KEYWORDS = ("자동", "저장", "다운로드", "auto", "save", "download",
                "경로", "폴더", "path", "folder", "사진", "파일", "받은")
    matches = []
    for n in tree:
        text = (n["name"] + " " + n["aid"]).lower()
        for kw in KEYWORDS:
            if kw.lower() in text:
                matches.append({**n, "matched": kw}); break

    print(f"\n키워드 일치 노드: {len(matches)}개")
    for m in matches[:30]:
        rect = m["rect"]; r_str = f"({rect.get('l',0)},{rect.get('t',0)})"
        print(f"  [{m['matched']:6s}] {m['type']:18s} {m['name'][:50]!r} aid={m['aid']!r} {r_str}")

    # 모든 체크박스/리스트
    checks = [n for n in tree if n["type"] in ("CheckBoxControl", "RadioButtonControl") and not n["off"]]
    edits = [n for n in tree if n["type"] == "EditControl" and not n["off"]]
    btns = [n for n in tree if n["type"] == "ButtonControl" and n["name"] and not n["off"]]
    lists = [n for n in tree if n["type"] in ("ListControl", "TreeControl") and not n["off"]]

    print(f"\n체크박스: {len(checks)}개, 입력창: {len(edits)}개, 버튼: {len(btns)}개, 리스트: {len(lists)}개")
    print("\n--- 체크박스 ---")
    for c in checks[:20]:
        print(f"  {c['name'][:60]!r} aid={c['aid']!r}")
    print("\n--- 리스트 항목 (좌측 카테고리) ---")
    for l in lists[:5]:
        for ch in deep_walk(_resolve(l, settings), max_depth=3)[:30]:
            if ch["type"] == "ListItemControl" or ch["type"] == "TreeItemControl":
                print(f"  - {ch['name'][:60]!r}")

    out.write_text(json.dumps({
        "settings_window": settings.Name, "tree_count": len(tree),
        "keyword_matches": matches, "checkboxes": checks, "edits": edits,
        "buttons_named": btns[:50], "tree": tree,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")


def _resolve(node_dict, parent_ctrl):
    """info dict → 실제 컨트롤 핸들 (이름 매칭)."""
    # 단순화: parent에서 이름 일치 찾기
    return parent_ctrl  # 일단 부모 반환 (실패 시 None 처리됨)


if __name__ == "__main__":
    main()
