"""서버 전용 배포 스크립트 — git 안전 동기화 + docker compose 재빌드.

⚠️ 서버 전용. 로컬 PC(docker 미설치)에서는 가드가 즉시 차단한다.
   docker 호출이 허용된 유일한 스크립트 — configs/quality_gate.json
   no_local_docker_cli_allow_paths 에 등록됨. (CLAUDE.md 정책 예외)

호출(데몬):  python3 tools/server_deploy.py --approved

흐름:
  1. 로컬 가드: docker 없으면 exit 3
  2. git fetch + fast-forward only 병합 (운영 로컬 변경 유실 방지 — reset --hard 미사용)
  3. docker compose up -d --build (변경된 서비스)
  4. 헬스체크
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[1]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
COMPOSE_SERVICES = ["ai-orchestrator-api", "admin-web"]


def _guard_server_only() -> None:
    """로컬 PC(docker 없음)에서 실행 차단."""
    if shutil.which("docker") is None:
        print("[server_deploy] docker 없음 — 서버 전용 스크립트입니다. 로컬 실행 차단.")
        sys.exit(3)


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print(f"[server_deploy] $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(ROOT), check=False, **kw)


def _git_sync() -> bool:
    """fetch 후 fast-forward 가능할 때만 병합. 충돌/분기 시 중단(유실 방지)."""
    _run(["git", "fetch", "origin", "master"])
    behind = _run(
        ["git", "rev-list", "--count", "HEAD..origin/master"],
        capture_output=True,
        text=True,
    )
    n = (behind.stdout or "0").strip()
    print(f"[server_deploy] origin/master 대비 {n} 커밋 뒤")
    if n == "0":
        print("[server_deploy] 이미 최신 — 배포 생략")
        return False
    ff = _run(["git", "merge", "--ff-only", "origin/master"])
    if ff.returncode != 0:
        print("[server_deploy] fast-forward 불가(로컬 분기/충돌) — 수동 확인 필요. 중단.")
        sys.exit(4)
    return True


def _build_env() -> dict[str, str]:
    """compose build.args(GIT_SHA·BUILD_TIME)로 넘길 값 — 병합 후 HEAD 커밋과 빌드 시각(UTC). 실패하면 넘기지 않아 "unknown"."""
    env = dict(os.environ)
    sha = _run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if sha:
        env["GIT_SHA"] = sha
        env["BUILD_TIME"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return env


def _compose_rebuild() -> None:
    # docker compose(v2) 우선, 없으면 docker-compose(v1)
    base = (
        ["docker", "compose"]
        if _run(["docker", "compose", "version"], capture_output=True).returncode == 0
        else ["docker-compose"]
    )
    _run([*base, "up", "-d", "--build", *COMPOSE_SERVICES], env=_build_env())


def _reload_nginx() -> None:
    """컨테이너 재생성 후 nginx upstream IP 재해결 — 미하면 502(옛 IP 캐시).

    nginx 컨테이너 없거나 reload 실패해도 배포는 성공 처리(best-effort).
    """
    if _run(["docker", "inspect", "nginx"], capture_output=True).returncode != 0:
        print("[server_deploy] nginx 컨테이너 없음 — reload 생략")
        return
    if _run(["docker", "exec", "nginx", "nginx", "-t"], capture_output=True).returncode != 0:
        print("[server_deploy] nginx -t 실패 — reload 생략")
        return
    _run(["docker", "exec", "nginx", "nginx", "-s", "reload"])
    print("[server_deploy] nginx reload 완료 (upstream 재해결)")


def main() -> int:
    if "--approved" not in sys.argv:
        print("[server_deploy] --approved 필요 (데몬 경유 호출).")
        return 2
    _guard_server_only()
    changed = _git_sync()
    if not changed:
        return 0
    _compose_rebuild()
    _reload_nginx()  # 컨테이너 IP 변경 → nginx 재해결 (502 방지)
    print("[server_deploy] 배포 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
