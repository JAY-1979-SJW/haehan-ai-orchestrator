# 층간 위반 41 → 0 정리 — 방법·결과·교훈

- 날짜: 2026-10-01 / 지시: "2개 다 해야지"(레지스트리 오분류 보정 + 진짜 역방향 import 해소), 이어서 "#113·#114 진행"
- 기준: CI `verify` 가 세는 층간 위반(`data/code_map/modules.json` → `layer_inversions`, 파일별 레이어는 `configs/module_registry.json` 과 `allowed_deps`)
- 결과: **41 → 0**, 모듈 순환 80 유지, 금지 import 1 유지. 영향 테스트 통과, CI `verify` 통과.

## 1. 위반이 생기는 규칙 (알아 둘 것)
- 위반 = 파일 레이어의 `allowed_deps` 밖으로 import. 예) L1→L1만, L2→L1·L2·L3·L7, L4→L1~L4·L7, L5→L1~L5·L7, L7→L1·L7, L10→L1~L4·L7·L10.
- **지연(함수 안) import 와 리터럴 `importlib.import_module("x")` 도 간선으로 센다.** import 를 함수 안으로 옮겨도 해소되지 않는다. 변수에 담은 문자열 import 는 정적 그래프에 안 잡힌다(이 사실을 악용하지 말 것 — 아래 5절).
- 잘못된 레이어의 대부분은 **파일 이름 규칙**이 만든다: `guard`→L2 정책, `runner`·`flow`→L6 워크플로, `settings`→L1, `schedule`·`db`·`저장 신호`→L7, `blog`·`g2b` 이름→L5 등. 파일이 실제로 하는 일과 다르면 오분류다.

## 2. 방법 (순서)
1. **오분류 보정 29건 → 41→11**: 파일 내용(docstring·import·동작)을 근거로 `configs/module_registry.overrides.json` 에 `{layer, role, reason}` 으로 확정하고 `registry_sync --fix` 로 정본에 반영. 파일 라벨을 바꾸기 전에 **what-if 시뮬레이션**으로 새 위반이 생기는지 먼저 확인(import 간선은 그대로 두고 레이어만 바꿔 재계산 — 지도를 다시 만들 필요 없음).
2. **진짜 역방향 import 3건 코드 수정 → 11→5** (동작 불변, 테스트 먼저):
   - `DuplicateApprovalError` 를 작은 L1 모듈로 분리하고 원래 모듈에서 재노출(L7 저장소가 L2 검증기를 import 하던 것).
   - `LocalAgent.to_safe(stats=None)`: 모델(L1)이 레지스트리를 import 하던 방향을 뒤집어 레지스트리가 통계를 계산해 넘긴다.
   - blog CLI(L6)가 라우터(L8)에서 가져오던 Unsplash 이미지 헬퍼를 `scripts/naver/blog/unsplash_images.py` 로 이동(라우터는 옛 이름으로 재노출).
3. **#114: 코드맵 해석기 수정 → 5→3**: `reach.Resolver` 가 `from local_agent import X` 를 루트 `local_agent/` 패키지가 아니라 `core/agent_runtime/runtime/local_agent.py` 로 잘못 해석하던 가짜 간선을 제거. `from X import Y` 에서 Y 가 서브모듈로 존재하는 가장 가까운 위치를 우선. 측정 도구를 바꾸는 일이라 **변경 전후 import_edges 를 비교**해 의도한 변경만 일어났는지 확인했다(제거 13건 = 의도 11 + 서브모듈이 루트 패키지에만 있는 테스트 2).
4. **#113: 사이트 등록표 분리 → 3→0**: `scripts/site_registry.py` 를 코어(L4: `SiteSpec`·조회·등록·지연 로더)로 줄이고, 사이트별 로그인 래퍼·7개 항목은 `scripts/site_registry_sites.py`(L5)로 글자 그대로 이동. 호출처 코드 변경 없음.

## 3. 시행착오 (재발 방지)
- 헬퍼를 `ai_orchestrator/services/` 에 두자 `services ↔ scripts` **새 순환(80→81)** 이 생겼다. 블로그 전용이라 `scripts/naver/blog/` 로 옮겨 해결. 파일을 옮기면 `Path(__file__).resolve().parents[N]` 의 N 이 달라지므로 경로 깊이를 테스트로 고정했다.
- 라벨을 연쇄적으로 올리면(예: `cdp_client` 까지 L5 로) 다른 파일에서 위반이 또 생긴다. 숫자를 줄이려는 라벨 변경은 하지 않는다 — 파일이 실제로 L5 일 때만.
- 자동 린트 수정(`ruff --fix --select RUF100`)이 다른 사람이 단 필요한 `# noqa: PLR0913` 을 지웠다. 규칙 일부만 선택해 `--fix` 하면 그 규칙 밖의 noqa 가 "불필요"로 보인다 → `--fix` 는 `I001` 처럼 좁은 규칙에만.
- 변이 시험으로 테스트의 구멍을 찾았다(롤백 제거를 처음엔 못 잡음 → 보강).
- 같은 브랜치를 여러 세션이 공유하면 한쪽의 `pull --rebase`+`push` 가 다른 쪽의 미푸시 커밋을 함께 올린다 → 푸시 전 `git log origin..HEAD` 로 내 커밋만인지 확인.

## 4. 코어 ↔ 사이트 모듈 결합 (#113 의 솔직한 한계)
`site_registry`(L4) 는 첫 `get_site`/`list_sites` 호출 때 변수에 담은 문자열(`_LOADER = "scripts.site_registry_sites"`)로 L5 사이트 모듈을 불러 등록한다. 런타임에는 코어가 사이트 모듈에 의존하므로 **결합이 0 은 아니다.** 정적 그래프에 안 잡힐 뿐이다. 그럼에도 이 설계를 택한 이유는 L4 파일이 사이트 지식을 갖지 않는다는 **소유 구조**가 실제로 달라지고(호출처 3곳은 메타데이터만 쓴다), 대안이 더 나쁘기 때문이다.
- 대안 B(래퍼를 문자열 import 로만 바꾸기): 사이트 지식이 코어에 남아 분석기만 속인다 → 거부.
- 대안 C(진입점마다 등록 부트스트랩): 호출처 8곳 이상 수정, 빠뜨리면 "미등록 사이트" 오류 → 거부.
- 사이트 모듈은 코어를 import 하지 않고 `build_sites(SiteSpec)` 로 목록만 돌려준다 — 이 저장소는 같은 모듈이 `scripts.x` 와 `x` 두 이름으로 import 되는 `sys.path` 관례가 있어, 사이트 모듈이 코어를 import 하면 등록표가 두 개로 갈라질 수 있다.

## 5. 앞으로 지킬 규칙
1. 새 파일의 자동 분류(`registry_sync --fix`)가 이름 규칙으로 틀리게 나오면 **파일 내용을 근거로** overrides 에 이유와 함께 확정한다.
2. 층간 위반을 줄이려고 import 를 변수 문자열로 숨기지 않는다. 구조(누가 누구의 지식을 소유하는가)가 달라질 때만 분리하고, 남는 결합은 문서에 적는다.
3. 측정 도구(코드맵)를 고칠 때는 변경 전후 결과 차이를 비교해 의도한 변경만 확인한다.
4. 코드 변경은 동작 불변을 증명하는 테스트(현재 동작 스냅샷)를 **먼저** 만든다.
