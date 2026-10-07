# 자격증명 암호화 키 보호 + 네이버 자동 로그인 연동 기준서

작성: 2026-09-30 · 상태: **승인 대기 (코드 미작성)** · 대상: 고객 PC 설치형 데스크톱 앱

## 1. 배경과 목적

앱이 사용자의 사이트 아이디·비밀번호를 보유하고, CDP로 세션이 풀렸을 때 자동 로그인한다.
로그인 절차 자체(`scripts/naver/auth.py`)와 저장소(`scripts/credentials.py`)는 이미 있다.
이번 작업은 **새로 만들지 않고, 저장소의 키 보호를 고치고, 네이버 흐름을 그 위에서 검증**한다.

## 2. 현황 (실측, 2026-09-30)

| 항목 | 내용 |
|---|---|
| 저장소 | `scripts/credentials.py` — `data/credentials.json`, 비밀번호는 Fernet 암호화. 사이트별 `set_cred/get_cred/list_sites/delete_cred`, 계정별 키 `naver:<id>` 지원. CLI: `python -m scripts.credentials set/get/list/delete` (출력 마스킹) |
| **약점 1** | 암호화 키가 `data/.cred.key` 파일로 **암호문 바로 옆**에 있다. `chmod 0o600`은 Windows에서 효과가 없다. `data/` 폴더에 접근하면 복호화 가능 → 사실상 난독화 |
| **약점 2** | `scripts/naver/auth.py::save_credentials`가 `data/.env_naver`에 **평문**으로 쓴다. 이 PC에 실제로 존재(8월 16일). 로그인 코드가 폴백으로 이 파일도 읽는다 |
| 두 번째 키 사용처 | `scripts/form/personal_profile.py`가 `credentials._get_or_create_key`를 재사용 |
| 로그인 흐름 | `ensure_naver_login` → 세션 점검 → 로그아웃이면 `login_naver`(천천히 타이핑) → 캡차/2단계 인증 감지 시 중단하고 사용자에게 위임(`needs_manual`) |
| 정책 | 구글은 비밀번호 로그인 비활성(`_is_password_login_disabled`) — 변경하지 않음 |
| OS 저장소 | Windows 자격 증명 관리자(`keyring.backends.Windows.WinVaultKeyring`) 사용 가능. 로컬 에이전트 토큰이 이미 같은 방식 사용(`local_agent/token_store.py`) |

## 3. 변경 범위

레이어: **L3 Connectors** (`scripts/credentials.py`), L4/L5 (`scripts/naver/auth.py`). 신규 파일 없음(테스트 제외).

| 파일 | 변경 |
|---|---|
| `scripts/credentials.py` | 마스터 키 보관을 OS 자격 증명 관리자로 이전. `data/.cred.key`는 마이그레이션 원본/개발용 폴백 |
| `scripts/naver/auth.py` | `save_credentials`(평문 쓰기)를 통합 저장소 위임으로 교체. 평문 파일 읽기 경로는 마이그레이션 안내만 남김 |
| `tests/test_credentials_key_protection.py` (신규) | 키 이전·폴백·복호화·비출력 검증 |

**변경하지 않는 것:** 로그인 절차·타이핑·캡차 감지 로직, `credentials.json` 스키마와 암호 알고리즘(Fernet), 구글 정책, API 응답 키, DB.

## 4. 설계

### 4.1 마스터 키 보관 (`credentials.py`)
1. 키 조회 순서: **(a) keyring** (서비스 `haehan-ai/credentials`, 항목 `master-key`) → (b) 없고 `data/.cred.key`가 있으면 그 값으로 **마이그레이션** → (c) 둘 다 없으면 새 키 생성 후 keyring에 저장.
2. 마이그레이션: keyring에 저장 → **읽어서 동일함 확인** → 기존 `credentials.json`의 모든 항목이 새 키로 복호화되는지 확인 → 성공 시 `data/.cred.key`를 `data/.cred.key.migrated`로 **이름 변경(삭제하지 않음)**. 사용자가 확인 후 직접 지운다(비가역 삭제 방지).
3. keyring 사용 불가(Windows 이외, 백엔드 없음): 환경변수 `HAEHAN_CRED_KEY_BACKEND=file`이 명시된 경우에만 파일 폴백(개발용). 기본은 **fail-closed**(오류로 중단, 조용히 파일에 쓰지 않음).
4. `_get_or_create_key()`의 시그니처·반환형(bytes) 유지 → `scripts/form/personal_profile.py` 영향 없음.

### 4.2 평문 제거 (`auth.py`)
- `save_credentials(id, pw)` → 내부적으로 `credentials.set_cred("naver:<id>", ...)` 호출, 반환은 저장소 경로 문자열(호환).
- `data/.env_naver`는 자동 삭제하지 않는다. `migrate_legacy()`가 이미 아카이브 이동을 제공하므로 그 결과를 로그(값 제외)로만 안내.

### 4.3 비출력 원칙
- 아이디는 마스킹, 비밀번호·키는 로그·예외 메시지·CLI 어디에도 출력하지 않는다. 기존 `_redact_input_result` 유지.

## 5. 이 작업에서 하지 않는 것 (범위 밖)
- 캡차·문자/앱 인증(OTP)·기기 등록 자동 처리 → 원칙상 사용자에게 위임 유지
- 다른 사이트(EUM, 하이웍스 등) 로그인 구현 → 저장소는 이미 사이트별을 지원하므로 후속 작업
- 등록 화면(UI) → 보류. 지금은 기존 CLI 사용
- 비밀번호 재설정/계정 잠금 해제 → 사용자 작업

## 6. 드라이런 결과 (파일 미수정)

| 확인 | 결과 |
|---|---|
| 기존 저장소 열림 | 11개 사이트 저장, 그중 6개가 아이디+비밀번호 보유, 전부 복호화 성공(값 미출력) |
| keyring 왕복 | 44자 값 저장·조회·삭제 성공, 정리 후 조회 `None` |
| 키 함수 사용처 | `scripts/credentials.py`(정의), `scripts/form/personal_profile.py`(재사용), 테스트 1개 |
| 기존 테스트 영향 | `tests/test_credentials_cli_security.py`가 `KEY_FILE`을 바꿔치기함 → 새 설계에서도 `KEY_FILE`을 폴백 경로로 유지해 호환 |

**예상 diff:** `credentials.py` +약 50줄/-약 10줄, `auth.py` +약 10줄/-약 12줄, 신규 테스트 약 90줄.
**예상 게이트:** 신규 위반 0 목표. `SECURITY_PATTERN`(비밀 출력 금지)에 걸릴 가능성이 있어 테스트에서 실제 값을 쓰지 않고 더미만 사용.

## 7. 사이드 이펙트와 위험

| 위험 | 대응 |
|---|---|
| 마이그레이션 중 실패로 기존 비밀번호 소실 | 원본 키 파일을 삭제하지 않고 이름만 변경, 복호화 검증을 통과한 뒤에만 진행, 실패 시 원상 유지 |
| 다른 Windows 계정/PC로 `data/` 복사 시 복호화 불가 | 의도된 동작(키가 OS 계정에 묶임). 이전이 필요하면 CLI로 재입력 |
| keyring 잠금/권한 오류 | fail-closed + 명확한 메시지(값 미포함) |
| `.env_naver` 평문 잔존 | 자동 삭제하지 않고 안내 → 사용자가 확인 후 정리 |

롤백: `git revert` + `data/.cred.key.migrated`를 `data/.cred.key`로 되돌리면 이전 상태.

## 8. 검증 계획
1. 단위: 키 이전(정상/부분 실패), keyring 불가 시 fail-closed, 파일 폴백 명시 시 동작, 복호화 왕복, 로그·예외에 값 미포함
2. 기존 `test_credentials_cli_security.py` 통과 유지
3. 게이트: layer audit 3종, quality gate, ruff 신규 위반 0
4. 실전(로그인 필요): 비밀번호 재설정된 네이버 계정으로 세션 만료 상태에서 자동 로그인 → 캡차/2단계 시 사용자 위임 확인

## 9. 승인 요청
위 범위(4.1 키 이전, 4.2 평문 쓰기 제거, 신규 테스트)로 코드 작성 진행 여부. 승인 시 이 문서를 그대로 근거로 삼는다.
