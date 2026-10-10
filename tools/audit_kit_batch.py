"""audit-kit 의 파일 단위 hook 검사를 **한 프로세스에서 여러 파일**에 돌린다 — 프로젝트 그래프를 한 번만 만든다.

`audit-kit hook` 은 호출마다 `build_project_graph`(프로젝트 전체 .py 를 읽어 import 그래프 구성)와 순환 계산을 새로 한다. 이 저장소(.py 수천 개)에서
파일 하나당 약 8초라서, 합본 PR 처럼 변경 파일이 1000개 넘으면 기준·변경 후 두 트리에 hook 2000번 × 8초 ÷ 4 스레드 ≈ 70분이다.
(2026-10-08 PR #160 verify 가 이 단계에서 90분 상한까지 끝나지 않았다.) 이 스크립트는 같은 `audit_kit.hook.check_file` 을 그대로 부르되
그래프와 순환 계산을 트리마다 한 번만 하도록 캐시해서 파일당 비용을 그래프 구성에서 떼어 낸다 — 결과(메시지)는 파일마다 따로 부른 것과 같다.

사용: audit-kit 가상환경의 python 으로 `python audit_kit_batch.py <트리 루트>` , 표준입력에 상대 경로 JSON 배열.
출력(stdout, JSON): {상대경로: [메시지, ...] 또는 null(그 파일 검사 중 예외)}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve()
    rels = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "[]")
    from audit_kit import hook  # audit-kit 가상환경에만 있다

    original = hook.build_project_graph
    cache: dict = {}

    def cached(cfg):  # 트리(cfg.root)마다 한 번만 그래프를 만들고, 순환 계산 결과도 한 번만 구한다
        key = str(cfg.root)
        if key not in cache:
            graph = original(cfg)
            try:
                cycles = graph.cycles()
                graph.cycles = lambda: cycles
            except Exception:  # noqa: BLE001 - 순환 캐시는 최적화일 뿐 — 실패하면 원래 동작(호출마다 계산)으로 둔다
                pass
            cache[key] = graph
        return cache[key]

    hook.build_project_graph = cached
    out: dict = {}
    for rel in rels:
        try:
            out[rel] = list(hook.check_file(root / rel))
        except Exception as exc:  # noqa: BLE001 - 한 파일의 검사 실패가 나머지를 막지 않게 하고, 호출 쪽이 단독 실행으로 다시 시도한다
            print(f"[audit_kit_batch] {rel}: {exc!r}", file=sys.stderr)
            out[rel] = None
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
