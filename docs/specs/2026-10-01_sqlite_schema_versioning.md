# sqlite 스키마 버전 관리 (결함 #14) — 기준서

## 1. 문제
- sqlite DB 약 25개가 `CREATE TABLE IF NOT EXISTS` 를 **연결할 때마다** 다시 실행하고, 컬럼 추가는 실행 중 `ALTER TABLE` 로
  한다(4곳: 예약 작업·인스타 DM·팝업 이벤트·쇼핑 크롤). 스키마 버전 기록이 없어 (a) 어떤 DB 가 어느 모양인지 알 수 없고,
  (b) 코드가 새 컬럼을 기대하는데 옛 DB 라 깨져도 감지가 늦고, (c) 새 코드가 만든 DB 를 옛 코드가 열어도 막지 못한다.
- 지금까지의 방식(`PRAGMA table_info` 로 컬럼 확인 후 ALTER, 또는 `suppress(OperationalError)`)은 컬럼 추가만 되고
  타입 변경·테이블 분리·데이터 이전은 표현할 수 없다.

## 2. 설계
- 공용 도우미 `ai_orchestrator/persistence/sqlite_schema.py` (L7, 표준 라이브러리만 사용).
- 버전은 sqlite 내장 `PRAGMA user_version`(DB 파일 헤더의 정수)에 저장한다. 별도 테이블이 필요 없다.
- DB 마다 **순서가 있는 단계 목록**(`steps`)을 코드에 둔다. `steps[i]` 는 버전 `i` → `i+1` 로 올리는 함수.
  `apply_schema(con, steps)` 는 현재 버전보다 뒤의 단계만 순서대로 실행한다.
- 한 번 배포된 단계는 **수정하지 않는다**. 스키마를 바꾸려면 새 단계를 뒤에 추가한다.
- 모든 단계는 멱등이어야 한다(`CREATE ... IF NOT EXISTS`, 컬럼은 `add_column_if_missing`). 그래야 버전 장치가 없던
  기존 DB(user_version=0, 이미 테이블 있음)가 같은 단계를 다시 지나가도 안전하다.
- 실행은 `BEGIN IMMEDIATE` 트랜잭션 하나로 묶는다(sqlite 의 DDL 은 트랜잭션 안에서 롤백된다). 단계가 실패하면
  전부 롤백하고 버전은 오르지 않는다. 잠금을 잡은 **뒤** 버전을 다시 읽어 동시 프로세스가 같은 단계를 두 번 실행하지 않게 한다.
- DB 가 코드보다 새로우면(`user_version > len(steps)`) `SchemaTooNewError` 로 막는다 — 옛 코드가 새 DB 를 건드려 망가뜨리지 않게.
- 버전이 이미 최신이면 `PRAGMA user_version` 한 번만 읽고 반환한다(연결마다 DDL 을 다시 실행하던 비용 제거).

## 3. 제약: DB 파일 하나에 소유 모듈 하나
`user_version` 은 파일당 정수 하나다. 한 파일을 여러 모듈이 나눠 쓰면 서로의 번호를 덮어쓴다.
- `data/cdp.db` 는 `scripts/cdp_db.py` 와 `scripts/popup_monitor.py` 가 함께 쓴다 → **이번 범위에서 제외**.
  스키마 소유자를 `cdp_db.py` 하나로 합친 뒤(popup_events DDL 이전) 적용한다.
- 새 DB 를 만들 때는 처음부터 이 도우미를 쓰고, 소유 모듈을 모듈 docstring 에 적는다.

## 4. 이번 범위(시범 2개, 파일 단독 소유)
| DB | 모듈 | 단계 |
|---|---|---|
| `ai_orchestrator/storage/scheduled_jobs.db` | `persistence/scheduled_job_store.py` | v1 jobs·runs·인덱스 생성 → v2 `runs.decided_by` |
| `ai_orchestrator/storage/instagram_dm.db` | `connectors/instagram_dm_db.py` | v1 기존 테이블 전부 → v2 `instagram_accounts.legacy_instagram_user_id` |

보류(사이트 작업 보류 방침): `scripts/naver/shopping/crawl.py`(쇼핑 크롤 DB, `shopping_items.is_ad` ALTER).
나머지 DB(약 20개)는 같은 방식으로 단계 1(현재 스키마 그대로)만 붙이면 되며, 소유 모듈 확인 후 순차 적용한다.

## 5. 영향·위험
- 스키마 결과(테이블·컬럼)는 기존과 동일하다. 달라지는 것은 DB 헤더의 `user_version` 값뿐이다.
- 기존 DB 는 첫 연결 때 단계 1·2 가 멱등으로 실행된 뒤 버전 2 가 된다. 데이터는 건드리지 않는다.
- 롤백: 코드를 되돌려도 DB 는 정상 동작한다(옛 코드는 `user_version` 을 보지 않음).
- 드라이런: 실제 DB 를 **복사본**에 적용해 행 수·컬럼·버전 확인 후 코드 반영.
- 보안/외부 API/레이어: 해당 없음(L7 persistence, 표준 라이브러리). 새 파일 1개 + 테스트 1개 → module_registry 등록 필요.
