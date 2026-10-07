"""CDP 칸(lane) 등록표 — 포트·프로필·담당 사이트의 단일 출처.

기준서: docs/specs/2026-10-02_app_agent_dispatch.md §9 (P0)
브라우저 작업을 병렬로 돌리려면 서로 다른 Chrome(포트+프로필 한 쌍)이 필요하다. 이 모듈은 "어느 사이트는 어느 칸"만 안다.

- `general` 칸 = 기존 CDP(9222, `ai_chrome` 프로필) 그대로 — **기존 로그인 세션 보존**, 기존 코드의 동작은 바뀌지 않는다.
- 새 칸은 필요할 때만 켠다. 동시에 켜는 칸은 `MAX_ACTIVE_LANES`(메모리 부족 이력) 이하.
- **한 계정은 한 칸에만** 배정한다(같은 계정을 두 칸에서 동시에 로그인하면 세션이 끊길 수 있다).
- 새 하드코딩 금지: 포트가 필요하면 `lane_for_site()`/`get_lane()` 으로 조회한다. 부작용 없음(네트워크는 `is_alive()` 에서만).
"""

from __future__ import annotations

import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scripts.common.app_paths import repo_root
from scripts.common.config import CDP_HOST
from scripts.common.config import CDP_PORT as GENERAL_PORT

ROOT = repo_root()
MAX_ACTIVE_LANES = 3
GENERAL = "general"


@dataclass(frozen=True)
class Lane:
    name: str
    port: int
    profile_dir: Path
    sites: tuple[str, ...]

    @property
    def endpoint(self) -> str:
        return f"http://{CDP_HOST}:{self.port}"

    @property
    def pid_file(self) -> Path:
        # general 은 기존 PID 파일을 그대로 쓴다(cdp_force_start 와 호환)
        suffix = "" if self.name == GENERAL else f"_{self.name}"
        return ROOT / "data" / f"cdp_force_pid{suffix}.json"


def _general_profile() -> Path:
    env = os.environ.get("HAEHAN_CDP_PROFILE", "").strip()
    return Path(env) if env else ROOT / "data" / "cdp_profile" / "ai_chrome"


def _build_lanes() -> dict[str, Lane]:
    return {
        GENERAL: Lane(GENERAL, GENERAL_PORT, _general_profile(), ()),
        "naver": Lane(
            "naver",
            GENERAL_PORT + 1,
            ROOT / "data" / "cdp_profile" / "lane_naver",
            ("naver", "smartstore", "blog", "cafe", "naver_mail", "commerce"),
        ),
        "groupware": Lane(
            "groupware",
            GENERAL_PORT + 2,
            ROOT / "data" / "cdp_profile" / "lane_groupware",
            ("hiworks", "eum", "gabia"),
        ),
    }


LANES: dict[str, Lane] = _build_lanes()


class UnknownLane(KeyError):
    """등록되지 않은 칸 이름."""


def get_lane(name: str) -> Lane:
    try:
        return LANES[name]
    except KeyError as e:
        raise UnknownLane(f"등록되지 않은 CDP 칸: {name} (가능: {', '.join(LANES)})") from e


def lane_for_site(site: str) -> Lane:
    """사이트 이름 → 담당 칸. 어느 칸에도 없으면 `general`."""
    key = (site or "").strip().lower()
    for lane in LANES.values():
        if key in lane.sites:
            return lane
    return LANES[GENERAL]


def validate_registry(lanes: dict[str, Lane] | None = None) -> list[str]:
    """등록표 일관성 검사: 포트·프로필 중복, 사이트가 두 칸에 중복 배정(= 같은 계정이 두 칸에 로그인될 위험)."""
    lanes = lanes or LANES
    errors: list[str] = []
    ports: dict[int, str] = {}
    profiles: dict[str, str] = {}
    sites: dict[str, str] = {}
    for lane in lanes.values():
        if lane.port in ports:
            errors.append(f"포트 {lane.port} 중복: {ports[lane.port]}, {lane.name}")
        ports[lane.port] = lane.name
        pkey = str(lane.profile_dir).lower()
        if pkey in profiles:
            errors.append(f"프로필 중복: {profiles[pkey]}, {lane.name}")
        profiles[pkey] = lane.name
        for site in lane.sites:
            if site in sites:
                errors.append(f"사이트 '{site}' 가 두 칸에 배정됨: {sites[site]}, {lane.name}")
            sites[site] = lane.name
    return errors


def is_alive(lane: Lane, timeout: float = 1.5, opener: Callable[..., object] = urllib.request.urlopen) -> bool:
    """이 칸의 Chrome 이 CDP 에 응답하는지(읽기 전용 HTTP 한 번)."""
    try:
        with opener(f"{lane.endpoint}/json/version", timeout=timeout) as r:  # type: ignore[attr-defined]
            return getattr(r, "status", 200) == 200
    except Exception:  # noqa: BLE001 - 응답 없음·연결 거부 모두 "꺼져 있음" 으로 본다
        return False


def active_lanes(is_alive_fn: Callable[[Lane], bool] = is_alive) -> list[str]:
    return [name for name, lane in LANES.items() if is_alive_fn(lane)]


def can_start(lane_name: str, is_alive_fn: Callable[[Lane], bool] = is_alive) -> tuple[bool, str]:
    """새 칸을 켜도 되는지(이미 켜져 있으면 True, 동시 칸 상한 초과면 False)."""
    lane = get_lane(lane_name)
    if is_alive_fn(lane):
        return True, "이미 켜져 있음"
    running = active_lanes(is_alive_fn)
    if len(running) >= MAX_ACTIVE_LANES:
        return (
            False,
            f"동시에 켠 칸이 이미 {len(running)}개({', '.join(running)}) — 상한 {MAX_ACTIVE_LANES}개(메모리 보호)",
        )
    return True, "켤 수 있음"
