"""사이트 접속/로그인 전 단계 감시 + 실패 시 아티팩트 번들.

사용:
    from scripts.site_engine.site_watch import StepWatcher
    w = StepWatcher(site="eum")
    with w.step("01_goto") as s:
        page.goto(...)
        s.attach(page)        # 페이지 첨부 (실패 시 자동 스크린샷)
    with w.step("02_login_form_detect") as s:
        s.attach(page)
        ...
        if not found:
            s.fail("로그인 폼 없음", kind="form_not_found")  # 즉시 중단

실패 시:
    - 스크린샷 + DOM + 콘솔/네트워크 에러 수집
    - summary.json 작성
    - StepFailure 예외 발생 (호출자는 잡거나 그대로 전파)
    - 후속 step 실행 안 됨
"""

from __future__ import annotations

import json
import time
import traceback
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.common.logger import get_logger
from scripts.common.op_log import log_op

if TYPE_CHECKING:
    from scripts.form.bot_radar import BotRadar

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "data" / "reports"


class StepFailure(RuntimeError):
    def __init__(self, site: str, step: str, kind: str, message: str, report_dir: Path):
        self.site = site
        self.step = step
        self.kind = kind
        self.message = message
        self.report_dir = report_dir
        super().__init__(f"[{site}:{step}] {kind}: {message}  (보고서: {report_dir})")


class _BotFlagged(RuntimeError):
    """내부 신호 — step 블록에서 catch 후 step.fail 로 변환."""

    def __init__(self, report: dict):
        self.report = report
        super().__init__(f"bot flagged: {report.get('level')} (vendors={report.get('vendors')})")


class _Step:
    """개별 step 핸들. with 블록 안에서 .attach(page), .fail(...) 호출 가능."""

    def __init__(self, watcher: StepWatcher, name: str):
        self.watcher = watcher
        self.name = name
        self.page = None
        self._failed = False
        self._fail_kind = ""
        self._fail_msg = ""
        self.started_at = time.time()

    def attach(self, page) -> None:
        """페이지 첨부 — 실패 시 자동 스크린샷/DOM + 봇 레이더 활성화."""
        self.page = page
        # 콘솔 + 네트워크 훅 + 봇 레이더 (중복 방지)
        if not getattr(page, "_site_watch_hooked", False):
            try:
                page.on("console", lambda msg: self.watcher._on_console(msg))
                page.on("requestfailed", lambda req: self.watcher._on_req_failed(req))
                page._site_watch_hooked = True
            except Exception:  # noqa: BLE001 - 사이트 자동화 단계별 실행 래퍼(스크린샷/HTML덤프/봇감지 기록) - 예외 발생시 실패로 기록하고 finalize(failed=True)로 이어지는 흐름 유지, 정책 판정 로직 아님
                pass
        # 봇 레이더 장착 (page 단위 1회)
        with suppress(Exception):
            self.watcher.ensure_bot_radar(page)

    def fail(self, message: str, kind: str = "unknown") -> None:
        """이 단계 실패 처리 — StepFailure 발생 후 watcher가 종료."""
        self._failed = True
        self._fail_kind = kind
        self._fail_msg = message
        raise StepFailure(self.watcher.site, self.name, kind, message, self.watcher.report_dir)


class StepWatcher:
    """전 단계 감시 + 보고서 번들."""

    def __init__(self, site: str):
        self.site = site
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.report_dir = REPORTS_DIR / f"{site}_{ts}"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict] = []
        self.console_msgs: list[dict] = []
        self.net_failures: list[dict] = []
        self.bot_reports: list[dict] = []  # step별 봇 감지 누적
        self._bot_radar: BotRadar | None = None
        self.started_at = time.time()
        self._step_idx = 0
        log.info("[site-watch] 시작 site=%s 보고서=%s", site, self.report_dir)

    def ensure_bot_radar(self, page) -> None:
        if self._bot_radar is None:
            try:
                from scripts.form.bot_radar import BotRadar

                self._bot_radar = BotRadar(page)
                self._bot_radar.arm()
                log.info("[site-watch] BotRadar 장착 site=%s", self.site)
            except Exception as e:  # noqa: BLE001 - 사이트 자동화 단계별 실행 래퍼(스크린샷/HTML덤프/봇감지 기록) - 예외 발생시 실패로 기록하고 finalize(failed=True)로 이어지는 흐름 유지, 정책 판정 로직 아님
                log.debug("[site-watch] BotRadar 장착 실패: %s", e)

    def _scan_bot(self, page, step_name: str) -> dict:
        """각 step 종료 후 호출. blocked/challenged 면 즉시 raise."""
        if page is None:
            return {}
        try:
            from scripts.form.bot_radar import scan as bot_scan

            r = bot_scan(page)
        except Exception as e:  # noqa: BLE001 - 사이트 자동화 단계별 실행 래퍼(스크린샷/HTML덤프/봇감지 기록) - 예외 발생시 실패로 기록하고 finalize(failed=True)로 이어지는 흐름 유지, 정책 판정 로직 아님
            log.debug("[site-watch] bot scan 실패: %s", e)
            return {}
        r["step"] = step_name
        self.bot_reports.append(r)
        if r.get("flagged"):
            # 즉시 보고서에 기록 후 raise (호출자가 step.fail 로 변환)
            raise _BotFlagged(r)
        return r

    # ── 이벤트 훅 ───────────────────────────────────────────────────
    def _on_console(self, msg) -> None:
        try:
            t = msg.type
            if t in ("error", "warning"):
                self.console_msgs.append({"type": t, "text": (msg.text or "")[:500]})
        except Exception:  # noqa: BLE001 - 사이트 자동화 단계별 실행 래퍼(스크린샷/HTML덤프/봇감지 기록) - 예외 발생시 실패로 기록하고 finalize(failed=True)로 이어지는 흐름 유지, 정책 판정 로직 아님
            pass

    def _on_req_failed(self, req) -> None:
        with suppress(Exception):
            self.net_failures.append(
                {
                    "url": req.url[:300],
                    "method": getattr(req, "method", ""),
                    "failure": (req.failure or "") if hasattr(req, "failure") else "",
                }
            )

    # ── 단계 컨텍스트 ───────────────────────────────────────────────
    @contextmanager
    def step(self, name: str):
        self._step_idx += 1
        idx = self._step_idx
        full_name = f"{idx:02d}_{name}"
        s = _Step(self, full_name)
        log.info("[site-watch] ▶ %s/%s", self.site, full_name)
        print(f"  ▶ [{self.site}] {full_name}", flush=True)
        # started 단계는 op_log에 기록하지 않음 (성공/실패만 finally 분기에서 기록)
        try:
            yield s
            # 정상 종료 직전 — 봇 레이더 사후 스캔
            if s.page is not None:
                try:
                    self._scan_bot(s.page, full_name)
                except _BotFlagged as bf:
                    elapsed = round(time.time() - s.started_at, 2)
                    self._capture(
                        s,
                        ok=False,
                        kind="bot_flagged",
                        message=f"level={bf.report['level']} vendors={bf.report.get('vendors', [])}",
                        elapsed=elapsed,
                    )
                    self._finalize(
                        failed=True, last_step=full_name, kind="bot_flagged", message=f"level={bf.report['level']}"
                    )
                    print(f"  ✘ [{self.site}] {full_name} → 봇 감지 (level={bf.report['level']})")
                    print(f"     vendors={bf.report.get('vendors', [])}")
                    print(f"     보고서: {self.report_dir}")
                    log_op(f"{self.site}:{full_name}", ok=False, message=f"bot_flagged:{bf.report['level']}")
                    raise StepFailure(
                        self.site, full_name, "bot_flagged", bf.report.get("level", ""), self.report_dir
                    ) from bf
        except StepFailure as e:
            elapsed = round(time.time() - s.started_at, 2)
            self._capture(s, ok=False, kind=e.kind, message=e.message, elapsed=elapsed)
            self._finalize(failed=True, last_step=full_name, kind=e.kind, message=e.message)
            print(f"  ✘ [{self.site}] {full_name} → {e.kind}: {e.message}")
            print(f"     보고서: {self.report_dir}")
            log_op(f"{self.site}:{full_name}", ok=False, message=f"{e.kind}: {e.message}")
            raise
        except Exception as e:
            elapsed = round(time.time() - s.started_at, 2)
            tb = traceback.format_exc()[-800:]
            (self.report_dir / f"{full_name}_traceback.txt").write_text(tb, encoding="utf-8")
            self._capture(s, ok=False, kind="exception", message=str(e)[:200], elapsed=elapsed)
            self._finalize(failed=True, last_step=full_name, kind="exception", message=str(e)[:200])
            print(f"  ✘ [{self.site}] {full_name} → 예외: {str(e)[:120]}")
            print(f"     보고서: {self.report_dir}")
            log_op(f"{self.site}:{full_name}", ok=False, message=f"exception: {str(e)[:120]}")
            raise StepFailure(self.site, full_name, "exception", str(e)[:200], self.report_dir) from e
        else:
            elapsed = round(time.time() - s.started_at, 2)
            self._capture(s, ok=True, kind="", message="", elapsed=elapsed)
            print(f"  ✓ [{self.site}] {full_name} ({elapsed}s)", flush=True)
            log_op(f"{self.site}:{full_name}", ok=True, message=f"{elapsed}s")

    # ── 캡처 ────────────────────────────────────────────────────────
    def _capture(self, s: _Step, *, ok: bool, kind: str, message: str, elapsed: float) -> None:
        rec = {
            "step": s.name,
            "ok": ok,
            "elapsed_s": elapsed,
            "kind": kind,
            "message": message,
        }
        # 실패 또는 항상 캡처 옵션 — 여기선 실패 시만 시각/DOM 저장
        if not ok and s.page is not None:
            with suppress(Exception):
                rec["url"] = s.page.url
            try:
                s.page.screenshot(path=str(self.report_dir / f"{s.name}.png"), full_page=True)
                rec["screenshot"] = f"{s.name}.png"
            except Exception as e:  # noqa: BLE001 - 사이트 자동화 단계별 실행 래퍼(스크린샷/HTML덤프/봇감지 기록) - 예외 발생시 실패로 기록하고 finalize(failed=True)로 이어지는 흐름 유지, 정책 판정 로직 아님
                rec["screenshot_err"] = str(e)[:120]
            try:
                html = s.page.content()
                (self.report_dir / f"{s.name}.html").write_text(html, encoding="utf-8")
                rec["html"] = f"{s.name}.html"
            except Exception as e:  # noqa: BLE001 - 사이트 자동화 단계별 실행 래퍼(스크린샷/HTML덤프/봇감지 기록) - 예외 발생시 실패로 기록하고 finalize(failed=True)로 이어지는 흐름 유지, 정책 판정 로직 아님
                rec["html_err"] = str(e)[:120]
        self.steps.append(rec)

    def _finalize(self, *, failed: bool, last_step: str = "", kind: str = "", message: str = "") -> None:
        # 마지막 종합 봇 리포트
        final_bot: dict[Any, Any] = {}
        if self._bot_radar is not None:
            with suppress(Exception):
                final_bot = self._bot_radar.report()
        summary = {
            "site": self.site,
            "started_at": self.started_at,
            "finished_at": time.time(),
            "elapsed_s": round(time.time() - self.started_at, 2),
            "ok": not failed,
            "failed_at": last_step if failed else "",
            "failure_kind": kind if failed else "",
            "failure_message": message if failed else "",
            "steps": self.steps,
            "console_msgs": self.console_msgs[-50:],
            "net_failures": self.net_failures[-50:],
            "bot_radar": {
                "final_level": final_bot.get("level", "unknown"),
                "final_confidence": final_bot.get("confidence", 0),
                "final_vendors": final_bot.get("vendors", []),
                "step_reports": [{k: v for k, v in r.items() if k != "signals"} for r in self.bot_reports[-20:]],
            },
        }
        (self.report_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def finish_ok(self) -> None:
        """모든 단계 성공 시 호출 — 보고서 마무리."""
        self._finalize(failed=False)
        log.info("[site-watch] ✔ 완료 site=%s steps=%d", self.site, len(self.steps))
        print(f"  ✔ [{self.site}] 모든 단계 통과 ({len(self.steps)} step, 보고서: {self.report_dir})")
