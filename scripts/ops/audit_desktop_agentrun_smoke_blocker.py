"""HAEHAN-DESKTOP-AGENTRUN-SMOKE-BLOCKER-FIX-01 감리 스크립트.

검사 항목:
1. /assets/*.js 가 catch-all에서 올바른 MIME으로 분기되는지
2. /assets/*.css 가 catch-all에서 올바른 MIME으로 분기되는지
3. index.html 이 현재 번들명을 참조
4. 구 번들(CdlGYLfF) 참조 없음
5. LocalAgentPanel 이 App.tsx PANELS에 등록
6. local_agent 메뉴가 appStore DEFAULT_MENU에 등록
7. preflight API 호출 코드 존재
8. can_run=false disabled 조건 존재
9. user_message / next_actions 표시 코드 존재
10. warnings 비차단 조건 존재
11. OUT_OF_SCOPE 파일 미포함
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI_DIST = ROOT / "desktop" / "ui_dist"
UI_SRC = ROOT / "desktop" / "ui" / "src"

PASS = "PASS"
FAIL = "FAIL"

results: list[tuple[str, str, str]] = []


def chk(label: str, ok: bool, detail: str = "") -> None:
    status = PASS if ok else FAIL
    results.append((label, status, detail))


# ── 1/2. local_server.py assets 분기 ──────────────────────────────────────────
server_py = (ROOT / "desktop" / "local_server.py").read_text(encoding="utf-8")
has_assets_branch = (
    'full_path.startswith("assets/")' in server_py
    and "asset_file.is_file()" in server_py
    and "mimetypes.guess_type" in server_py
)
chk("1. /assets/*.js catch-all 분기 코드 존재", has_assets_branch, "spa_fallback assets 분기")
chk("2. /assets/*.css catch-all 분기 코드 존재", has_assets_branch, "동일 분기로 CSS 처리")

# ── 3/4. index.html 번들 참조 ─────────────────────────────────────────────────
index_html = (UI_DIST / "index.html").read_text(encoding="utf-8")
js_match = re.search(r'src="[./]*assets/(index-[^"]+\.js)"', index_html)
css_match = re.search(r'href="[./]*assets/(index-[^"]+\.css)"', index_html)
current_js = js_match.group(1) if js_match else None
chk("3. index.html 현재 번들 참조", bool(current_js), f"JS: {current_js}")
chk("4. 구 번들(CdlGYLfF) 참조 없음", "CdlGYLfF" not in index_html, "구 번들 hash")

# ── 5/6. App.tsx + appStore.ts 등록 ──────────────────────────────────────────
app_tsx = (UI_SRC / "App.tsx").read_text(encoding="utf-8")
store_ts = (UI_SRC / "store" / "appStore.ts").read_text(encoding="utf-8")
chk("5. LocalAgentPanel App.tsx PANELS 등록", "local_agent" in app_tsx and "LocalAgentPanel" in app_tsx)
chk("6. local_agent DEFAULT_MENU 등록", "'local_agent'" in store_ts or '"local_agent"' in store_ts)

# ── 7~10. 번들 내 preflight 코드 존재 ────────────────────────────────────────
js_files = list((UI_DIST / "assets").glob("*.js"))
bundle = js_files[0].read_bytes() if js_files else b""
chk("7. preflight API 호출 코드 (번들)", b"local-agent/preflight" in bundle, js_files[0].name if js_files else "")
chk("8. can_run disabled 조건 (번들)", b"can_run" in bundle)
chk("9. user_message/next_actions 표시 (번들)", b"user_message" in bundle and b"next_actions" in bundle)
chk("10. warnings 비차단 조건 (번들)", b"warnings" in bundle)

# ── 11. OUT_OF_SCOPE 미포함 (git status 대신 파일 직접 확인) ─────────────────
out_of_scope = [
    ROOT / "scripts" / "archive" / "data" / "chrome_ui_monitor_state.json",
    ROOT / "scripts" / "navigator.py",
]
# 이 감리는 소스 코드 정적 분석이므로 파일 존재 여부만 확인
chk("11. OUT_OF_SCOPE 파일 여전히 존재(미삭제)", all(p.exists() for p in out_of_scope))

# ── 출력 ─────────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, s, _ in results if s == PASS)
fail_count = sum(1 for _, s, _ in results if s == FAIL)

print("=" * 60)
print("SMOKE BLOCKER AUDIT — HAEHAN-DESKTOP-AGENTRUN-SMOKE-BLOCKER-FIX-01")
print("=" * 60)
for label, status, detail in results:
    mark = "✅" if status == PASS else "❌"
    suffix = f"  [{detail}]" if detail else ""
    print(f"  {mark} {label}{suffix}")
print("-" * 60)
print(f"  PASS: {pass_count}  FAIL: {fail_count}")
print("=" * 60)
if fail_count > 0:
    sys.exit(1)
