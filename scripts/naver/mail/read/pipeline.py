"""Naver Mail 읽기 End-to-End 파이프라인.

흐름:
  1. about:blank 타겟 확보
  2. www.naver.com → 세션 판정
  3. LOGGED_IN 이면 mail.naver.com 진입
  4. mail이 nidlogin 으로 redirect 되면 NEED_MAIL_LOGIN — wait_until_logged_in
  5. 받은편지함 전체 페이지 순회 → 목록 수집
  6. 규칙 기반 분류
  7. 상위 N건(또는 ACTION_REQUIRED) 본문 읽기 → 보고

CLI:
  python -m scripts.naver.mail.read.pipeline [--max-bodies N] [--login-timeout S]
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from core.agent_runtime.policy import site_entry_policy as sep
from scripts.naver.mail.read import body_reader, cdp, classify, entry, list_collector

OUT_DIR = Path("data/inspection/naver_mail_pipeline")


def _print_status(state: str, href: str) -> None:
    print(f"  [login_status] state={state} href={href[:80]}")


def _classify_unread(unread: list) -> dict[str, list]:
    """안 읽은 메일을 라벨별로 분류(우선순위 정렬)."""
    classified: dict[str, list] = {}
    for it in unread:
        c = classify.classify(it.sender_full + " " + it.sender_name, it.subject)
        classified.setdefault(c.label, []).append((c.priority, it))
    for k in classified:
        classified[k].sort(key=lambda x: x[0])
    return classified


def _select_targets(classified: dict[str, list], max_bodies: int) -> list:
    """우선순위 순으로 본문 읽을 대상 최대 max_bodies 건 선택."""
    priority_order = ["ACTION_REQUIRED", "REVIEW", "INFO", "CARD_NOTICE", "PROMO", "OTHER"]
    targets: list = []
    for lab in priority_order:
        for _, it in classified.get(lab, []):
            targets.append((lab, it))
            if len(targets) >= max_bodies:
                break
        if len(targets) >= max_bodies:
            break
    return targets


def run(*, max_bodies: int = 4, login_timeout_s: float = 300.0, out_dir: Path = OUT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    sep.assert_main_page_first("https://www.naver.com/", "naver")
    sep.assert_main_page_first("https://mail.naver.com/", "naver")

    target_id = cdp.ensure_about_blank_target()
    print(f"[1] target_id={target_id[:12]}")

    # 2) 세션 판정
    state, data = entry.probe_session(target_id)
    print(f"[2] probe_session → {state}  href={data.get('href', '')[:80]}")

    if state == sep.STATE_LOGIN_REQUIRED or state == sep.STATE_SESSION_EXPIRED:
        print("[2.1] 사용자 수동 로그인 대기 (자동 입력 금지)")
        # mail.naver.com 로 직접 navigate — 그러면 자동으로 nidlogin 으로 redirect 되어 사용자가 로그인하기 좋음
        cdp.navigate(target_id, "https://mail.naver.com/")
        time.sleep(3.0)
        res = entry.wait_until_logged_in(
            target_id,
            timeout_s=login_timeout_s,
            on_status=_print_status,
        )
        print(f"  → {res.state}  href={res.final_url[:80]}")
        if res.state in (entry.TIMED_OUT, entry.ERROR):
            return {"ok": False, "stage": "login_wait", "result": asdict(res)}

    # 3) mail.naver.com 진입
    mstate, mdata = entry.enter_mail(target_id)
    print(f"[3] enter_mail → {mstate}  href={mdata.get('href', '')[:80]}")
    if mstate == entry.NEED_MAIL_LOGIN:
        print("[3.1] mail-specific 로그인 필요 — 대기")
        res = entry.wait_until_logged_in(
            target_id,
            timeout_s=login_timeout_s,
            on_status=_print_status,
        )
        if res.state == entry.TIMED_OUT:
            return {"ok": False, "stage": "mail_login_wait", "result": asdict(res)}
        mstate, mdata = entry.enter_mail(target_id)
    if mstate != entry.READY:
        return {"ok": False, "stage": "enter_mail", "state": mstate, "data": mdata}

    # 4) 목록 수집
    items, meta = list_collector.collect_all_pages(target_id, max_items=200)
    unread = [i for i in items if i.is_unread]
    print(f"[4] collected total={len(items)}  unread={len(unread)}  folder={meta.get('title', '')}")

    # 5) 분류
    classified = _classify_unread(unread)
    print(f"[5] classify labels={ {k: len(v) for k, v in classified.items()} }")

    # 6) 우선순위 N건 본문 읽기 (ACTION_REQUIRED 우선)
    targets = _select_targets(classified, max_bodies)
    print(f"[6] read bodies → {len(targets)}건")
    bodies = []
    for lab, it in targets:
        if not it.sn:
            continue
        body = body_reader.read_body(target_id, it.sn)
        bodies.append({"label": lab, "list_subject": it.subject, "body": asdict(body)})
        print(f"   - [{lab}] sn={it.sn} subj={it.subject[:60]}")

    out = {
        "meta": meta,
        "totals": {"all": len(items), "unread": len(unread)},
        "classified_counts": {k: len(v) for k, v in classified.items()},
        "items": [asdict(i) for i in items],
        "bodies": bodies,
    }
    out_path = out_dir / "pipeline_result.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[done] saved → {out_path}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-bodies", type=int, default=4)
    ap.add_argument("--login-timeout", type=float, default=300.0)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    run(max_bodies=args.max_bodies, login_timeout_s=args.login_timeout, out_dir=args.out)


if __name__ == "__main__":
    main()
