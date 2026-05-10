"""카카오 로컬 데몬 — 로컬 PC에서 상시 실행.

카카오워크/카카오톡 상태를 감시하여 서버 API로 전송.

사용법:
  python scripts/kakao_daemon.py                # 기본 실행
  python scripts/kakao_daemon.py --dry-run      # 서버 전송 없이 콘솔만 출력
  python scripts/kakao_daemon.py --once         # 1회 실행 후 종료

환경변수:
  KAKAO_SERVER_URL   서버 주소 (기본: http://localhost:8000)
  KAKAO_API_TOKEN    인증 토큰 (있으면 Authorization 헤더 포함)

설정 파일:
  scripts/kakao_daemon_config.json 에 저장 가능
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

from ai_orchestrator.local_agent.desktop.mixins.kakaowork_mixin import KakaoworkMixin
from ai_orchestrator.local_agent.desktop.download_watcher import DownloadWatcher
from ai_orchestrator.local_agent.desktop.classifier import classify_file

# ── 설정 ──
CONFIG_FILE = Path(__file__).parent / "kakao_daemon_config.json"
DAEMON_VERSION = "1.0.0"

_log_file = ROOT / "data" / "reports" / "local_agent" / "kakao_daemon.log"
_log_file.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(open(1, "w", encoding="utf-8", closefd=False)),
        logging.FileHandler(_log_file, encoding="utf-8"),
    ]
)
log = logging.getLogger("kakao_daemon")


def _load_config() -> dict:
    defaults = {
        "server_url": "http://localhost:8000",
        "api_token": "",
        "poll_interval": 30,       # 카카오워크 채팅방 폴링 주기 (초)
        "heartbeat_interval": 60,  # heartbeat 주기 (초)
        "download_poll": 15,       # 다운로드 폴더 감시 주기 (초)
    }
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            defaults.update(data)
        except Exception:
            pass
    # 환경변수 우선
    if os.environ.get("KAKAO_SERVER_URL"):
        defaults["server_url"] = os.environ["KAKAO_SERVER_URL"]
    if os.environ.get("KAKAO_API_TOKEN"):
        defaults["api_token"] = os.environ["KAKAO_API_TOKEN"]
    return defaults


def _save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 서버 전송 ──

class EventSender:
    def __init__(self, server_url: str, token: str, dry_run: bool = False):
        self.base = server_url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.dry_run = dry_run

    def send(self, event_type: str, app: str, payload: dict) -> bool:
        body = {
            "event_type": event_type,
            "app": app,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        if self.dry_run:
            log.info("[DRY-RUN] %s/%s %s", app, event_type, json.dumps(payload, ensure_ascii=False)[:120])
            return True
        try:
            r = requests.post(f"{self.base}/api/v1/kakao/event",
                              json=body, headers=self.headers, timeout=10)
            r.raise_for_status()
            return True
        except Exception as e:
            log.warning("전송 실패 [%s/%s]: %s", app, event_type, e)
            return False


# ── 카카오워크 폴링 워커 ──

class KakaoworkWorker(KakaoworkMixin):
    def __init__(self, sender: EventSender, interval: int):
        self._sender = sender
        self._interval = interval
        self._prev_rooms: dict[str, dict] = {}
        self._stop = threading.Event()

    def run(self):
        # uiautomation은 COM 기반 — 스레드마다 CoInitialize 필요
        try:
            import ctypes
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass
        log.info("카카오워크 폴링 시작 (주기: %ds)", self._interval)
        # 첫 실행은 즉시
        self._tick()
        while not self._stop.wait(timeout=self._interval):
            self._tick()

    def _tick(self):
        try:
            rooms = self.kakaowork_list_rooms()
        except Exception as e:
            log.warning("카카오워크 폴링 오류: %s", e)
            return

        if not rooms:
            return

        # 항상 방 목록 전송 (서버 상태 최신화)
        self._sender.send("rooms_updated", "kakaowork", {"rooms": rooms})

        # 미읽음 변화 감지
        changed = []
        for r in rooms:
            name = r["name"]
            cnt = r["unread_count"]
            prev = self._prev_rooms.get(name, {}).get("unread_count", 0)
            if cnt > 0 and cnt != prev:
                changed.append(r)

        if changed:
            log.info("미읽음 변화: %s", [(r["name"], r["unread_count"]) for r in changed])
            self._sender.send("unread", "kakaowork", {"rooms": changed})

        self._prev_rooms = {r["name"]: r for r in rooms}

    def stop(self):
        self._stop.set()


# ── 다운로드 폴더 감시 ──

class DownloadWorker:
    def __init__(self, sender: EventSender, interval: int):
        self._sender = sender
        self._watcher = DownloadWatcher(
            poll_interval=interval,
            callback=self._on_new_file,
        )

    def _on_new_file(self, file_info: dict):
        from ai_orchestrator.local_agent.desktop.download_watcher import map_to_active_room
        from ai_orchestrator.local_agent.desktop.classifier import organize_file

        path = Path(file_info["path"])
        source = file_info.get("source", "general")

        # 카카오워크 출처면 활성 채팅방 매핑 시도
        room_name = None
        if source == "kakaowork":
            try:
                room = map_to_active_room(file_info["mtime"])
                if room:
                    room_name = room.get("name")
            except Exception:
                pass

        # 자동 정리 (_processed 폴더로 복사)
        try:
            org = organize_file(path, room_hint=room_name, copy=True)
        except Exception as e:
            org = {"status": f"organize_error: {e}", "category": file_info.get("type"),
                   "subcategory": "", "suggested_folder": "", "tags": [source]}

        payload = {
            "name": file_info["name"],
            "path": file_info["path"],
            "source": source,
            "room": room_name or "",
            "type": file_info["type"],
            "size": file_info["size"],
            "mtime_iso": file_info.get("mtime_iso"),
            "category": org.get("category"),
            "subcategory": org.get("subcategory", ""),
            "organized_to": org.get("dest", ""),
            "organize_status": org.get("status", ""),
            "tags": org.get("tags", []),
        }
        log.info("새 파일: [%s] %s → %s (%s)", source, file_info["name"],
                 org.get("status",""), room_name or "-")
        self._sender.send("file_downloaded", source, payload)

    def start(self):
        log.info("다운로드 폴더 감시 시작")
        self._watcher.start()

    def stop(self):
        self._watcher.stop()


# ── Heartbeat ──

def heartbeat_loop(sender: EventSender, interval: int, stop: threading.Event):
    log.info("Heartbeat 시작 (주기: %ds)", interval)
    while not stop.wait(timeout=interval):
        sender.send("heartbeat", "daemon", {"version": DAEMON_VERSION})


# ── 메인 ──

def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    once = "--once" in args

    cfg = _load_config()

    if "--setup" in args:
        print("서버 URL 입력 (기본: http://localhost:8000):")
        url = input().strip() or "http://localhost:8000"
        print("API 토큰 입력 (없으면 Enter):")
        token = input().strip()
        cfg["server_url"] = url
        cfg["api_token"] = token
        _save_config(cfg)
        print(f"설정 저장: {CONFIG_FILE}")
        return

    log.info("=" * 50)
    log.info("  카카오 로컬 데몬 v%s", DAEMON_VERSION)
    log.info("  서버: %s", cfg["server_url"])
    log.info("  모드: %s", "DRY-RUN" if dry_run else "LIVE")
    log.info("=" * 50)

    sender = EventSender(cfg["server_url"], cfg["api_token"], dry_run=dry_run)

    # 서버 연결 확인
    if not dry_run:
        try:
            r = requests.get(f"{cfg['server_url']}/api/v1/kakao/status", timeout=5)
            log.info("서버 연결 OK: %s", r.status_code)
        except Exception as e:
            log.warning("서버 연결 실패: %s — 오프라인 모드로 계속", e)

    if once:
        kw = KakaoworkWorker(sender, cfg["poll_interval"])
        kw._tick()
        log.info("1회 실행 완료")
        return

    stop_ev = threading.Event()
    kw = KakaoworkWorker(sender, cfg["poll_interval"])
    dl = DownloadWorker(sender, cfg["download_poll"])

    # heartbeat·download는 별도 스레드 (COM 불필요)
    threads = [
        threading.Thread(target=heartbeat_loop,
                         args=(sender, cfg["heartbeat_interval"], stop_ev),
                         name="heartbeat", daemon=True),
    ]
    dl.start()
    for t in threads:
        t.start()

    # uiautomation 폴링은 메인 스레드에서 실행 (COM 자동 초기화)
    log.info("카카오워크 폴링 시작 (주기: %ds) — 메인 스레드", cfg["poll_interval"])
    log.info("데몬 실행 중 — Ctrl+C로 종료")
    try:
        kw._tick()  # 즉시 1회
        while not stop_ev.wait(timeout=cfg["poll_interval"]):
            kw._tick()
    except KeyboardInterrupt:
        log.info("종료 중...")
    finally:
        stop_ev.set()
        dl.stop()
        log.info("데몬 종료")


if __name__ == "__main__":
    main()
