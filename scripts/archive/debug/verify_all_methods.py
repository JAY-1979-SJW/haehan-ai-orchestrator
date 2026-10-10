"""전체 메서드 구현 검증 스크립트 — 한 번에 실행 후 결과 출력."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.browser.agent.agent import BrowserAgent

PASS = "✓"
FAIL = "✗"
SKIP = "⚠"

results = []


def check(name, fn, *args, allow_zero=False, **kwargs):
    try:
        val = fn(*args, **kwargs)
        if allow_zero and isinstance(val, int):
            ok = True
        else:
            ok = bool(val)
        results.append((name, ok, val))
        tag = PASS if ok else FAIL
        summary = (
            repr(val)[:80]
            if not ok
            else (
                f"{len(val)}개"
                if isinstance(val, list)
                else f"{list(val.keys())}"
                if isinstance(val, dict)
                else repr(val)[:60]
            )
        )
        print(f"  {tag} {name}: {summary}")
        return val
    except Exception as e:  # noqa: BLE001 - 디버그 검증 스크립트 - 각 메서드 호출 실패를 결과 리스트에 기록하고 출력, 아카이브된 진단 도구일 뿐 운영 로직 아님
        results.append((name, False, str(e)))
        print(f"  {FAIL} {name}: {e}")
        return None


print("\n" + "=" * 65)
print("  전체 메서드 구현 검증")
print("=" * 65)

with BrowserAgent() as a:
    # ── 메일 ──────────────────────────────────────────────────────
    print("\n📧 [메일]")

    mails = check("mail_inbox()", a.mail_inbox, max_n=3)
    mail_id = mails[0]["id"] if mails else None

    if mail_id:
        detail = check("mail_read(id)", a.mail_read, mail_id)
    else:
        results.append(("mail_read(id)", False, "mail_id 없음"))
        print(f"  {SKIP} mail_read(id): 스킵 (mail_id 없음)")

    check("mail_search('네이버')", a.mail_search, "네이버", max_n=3)

    check("mail_folders()", a.mail_folders)

    check("mail_unread_count()", a.mail_unread_count, allow_zero=True)

    # ── 캘린더 ────────────────────────────────────────────────────
    print("\n📅 [캘린더]")

    check("calendar_today()", a.calendar_today)

    check("calendar_events('2026-05-01','2026-05-31')", a.calendar_events, "2026-05-01", "2026-05-31")

    # ── MyBox ─────────────────────────────────────────────────────
    print("\n📦 [MyBox]")

    check("mybox_list('/')", a.mybox_list, "/")

    check("mybox_quota()", a.mybox_quota)

# ── 요약 ──────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("  검증 요약")
print("=" * 65)

ok_count = sum(1 for _, ok, _ in results if ok)
total = len(results)

for name, ok, val in results:
    tag = PASS if ok else FAIL
    print(f"  {tag} {name}")

print(f"\n  결과: {ok_count}/{total} 통과")
print("=" * 65 + "\n")
sys.exit(0 if ok_count == total else 1)
