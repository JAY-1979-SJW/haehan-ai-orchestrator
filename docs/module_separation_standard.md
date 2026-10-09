# 모듈 분리 기준서 (Module Separation Standard)

> 목적: 비대해진 코드를 **단일 책임 leaf 모듈**로 쪼개고, **상위(컴포지션 루트)가 하위를
> wiring·관리**하며, leaf 끼리는 직접 결합하지 않고 **공유 계약·주입·이벤트로 통신**하도록
> 앱 전체를 분리한다. 기존 레이어(L1–L12, CLAUDE.md)와 의존성 방향을 그대로 따른다.

---

## 1. 핵심 패턴 — 상위 모듈이 하위를 관리

```
[상위] Composition Root        : 진입점(__init__ / router / main). 하위 모듈을 import·wiring 만.
                                  업무 로직 최소화. "무엇을 연결하는가"만 안다.
[하위] Leaf 모듈 (단일 책임)    : 자기 책임만. sibling leaf 를 직접 import 하지 않는다.
[공유] Contracts/Shared (L1)   : 타입·DTO·상수·이벤트명. 누구나 import 가능.
[통신] 주입(DI) / 이벤트버스    : leaf 간 상호작용은 상위가 주입하거나 버스 이벤트로.
```

**참조 구현(이미 적용됨):** `admin-web/electron/`
- `main.js` = 컴포지션 루트(모든 lib 모듈 wiring + 버스 구독)
- `lib/{config,bus,agent,mainWindow,licenseWindow,youtube,tray}.js` = leaf
- `lib/bus.js` = 통신 채널, `lib/config.js` = 공유 계약
- 게이트 `scripts/ops/desktop_version_separation_gate.py` 의 `LEAF_COUPLING` 규칙으로 강제

---

## 2. 분리 기준 — 언제/무엇을 쪼개나

| 신호 | 기준 |
|------|------|
| 파일 크기 | 단일 `.py`/`.tsx` **≤ 400 LOC 권장**, **800 LOC+ 는 필수 분리 대상** |
| 혼합 책임 | router 안 SQL/산식, service 안 HTTP, core 안 IO 등 → 책임별 분리 |
| 거대 클래스/믹스인 | 1 클래스가 다기능(예: cafe_mixin 1500+) → 능력별 서브모듈 |
| god `__init__` | eager 전체 import 재노출 → 얇은 파사드 + 지연/명시 재노출 |

**책임 경계(재확인):** router=HTTP만 / service=업무 흐름 / core=순수 정책·산식·판정 /
repository=DB / adapter=외부 연동.

---

## 3. 통신·결합 규칙 (게이트로 강제)

1. leaf → sibling leaf **직접 import 금지**. 필요 시 상위가 주입하거나 버스 이벤트.
2. 공유 타입/상수/계약은 **Contracts(L1)** 에. (도메인 모듈에 흩지 않음)
3. **cross-domain 직접 import 금지** (hiworks ↔ eum ↔ youtube ↔ google ↔ naver ↔ g2b ↔ gabia).
4. **역방향/순환 import 금지.** (순환 회피용 함수내 지연 import 는 허용 — 감사도 이를 false-positive 로 세지 않도록 정확화됨)
5. 공개 API(기존 import 경로/응답 key/DB schema/산식)는 **분리 후에도 보존**. 파사드로 유지.

---

## 4. 모듈별 드라이런 체크리스트 (코드 변경 없이 분석)

각 비대 모듈에 대해 아래를 산출한다:

```
[모듈] <경로> (현재 LOC)
1. 책임 인벤토리   : 이 파일이 하는 일들을 항목화 (N개 책임)
2. 의존 맵         : 무엇을 import 하고 무엇이 이걸 import 하나 (공개 API 표면)
3. 위반            : 크기 / 혼합책임 / cross-domain / 순환 / god-init
4. 제안 분리       : 하위 모듈 목록(책임 1:1) + 상위(루트) wiring + 파사드 재노출
5. 보존 계약       : 바뀌면 안 되는 공개 import 경로 / 응답 key
6. 위험·테스트     : 영향받는 호출처 / 기존 테스트 / 회귀 위험
7. 분리 순서       : 의존 적은 leaf 부터
```

---

## 5. 실행 절차 (모듈 1개당, 직렬)

1. **드라이런 산출**(위 체크리스트) → 검토
2. **하위 서브모듈 생성** — 기존 코드 이동(무단 삭제 금지, 동작 보존)
3. **상위 wiring** — 루트가 서브모듈을 import·조립
4. **파사드 유지** — 기존 공개 import 경로를 `__init__` 재노출로 보존 (호출처 무변경)
5. **게이트** — `codebase_layer_audit` (FORBIDDEN/CIRCULAR/SECURITY=0) + `quality_gate`
6. **테스트** — 관련 pytest / 타입체크
7. **커밋 1회** — 모듈 단위로 작게. 푸시.

> 병렬 금지(같은 파일/도메인 동시 수정·git·DB). 모듈 단위 직렬 + 게이트 직렬 재실행.

---

## 6. 게이트 강제

- `python tools/repo_gates/codebase_layer_audit.py` → FORBIDDEN_IMPORT / CIRCULAR_IMPORT / SECURITY_PATTERN = 0
- `python tools/quality/quality_gate.py --staged --enforce --allow-existing-code-change` → errors = 0
- (옵션 신설) **파일 크기 게이트** — 800 LOC+ 신규 유입 차단. 분리 완료 모듈은 화이트리스트.
- (적용됨) 데스크톱 `LEAF_COUPLING` 게이트 — leaf 간 직접 import 차단. 백엔드 도메인에도 동형 규칙 확장 검토.

---

## 7. 분리 대상 우선순위 (측정 기반, tests 제외)

| 순위 | 모듈 | LOC | 성격 |
|------|------|-----|------|
| 1 | `ai_orchestrator/agent_hub/router/root.py` | 1763 | L8 라우터 비대 — 핸들러 책임별 분리 |
| 2 | `scripts/google/common/live_inputs.py` | 1684 | L5 사이트 — 입력 종류별 분리 |
| 3 | `scripts/naver/cafe/cafe_mixin.py` | 1592 | L4 믹스인 — 능력별 분리 |
| 4 | `scripts/page_helper.py` | 1475 | L4 범용 — 헬퍼군 분리 |
| 5 | `scripts/google/youtube/search.py` | 1451 | L5 — 검색/분석/수집 분리 |
| 6 | `scripts/youtube/research.py` | 1429 | L6 — 수집/분석/리포트 분리 |
| 7 | `scripts/naver/blog/blog_mixin.py` | 1416 | L4 믹스인 |
| 8 | `scripts/naver/router.py` | 1155 | L5 라우터 |
| 9 | `scripts/naver/smartstore/navigation/cdp_popup_manager.py` | 1000 | L4 |
| 10 | `scripts/naver/blog/core/writer.py` | 928 | L6 |

> 우선순위는 LOC + 결합도/위험으로 조정. 라우터(L8)·믹스인(L4)부터 효과 큼.
> tests 파일(1865/1174 등)은 대상 외(테스트는 길어도 무방).

---

## 8. 완료 정의 (Definition of Done)

- 대상 모듈이 단일 책임 leaf 들로 분리되고 상위가 wiring.
- 기존 공개 import 경로·응답 key 보존(파사드).
- leaf 간 직접 결합 0, 순환 0, cross-domain 0.
- 전 게이트 PASS, 관련 테스트 통과, 모듈 단위 커밋.
