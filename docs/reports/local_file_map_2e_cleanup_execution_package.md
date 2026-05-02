# LOCAL-FILE-MAP-2E: 정리 실행 패키지 생성 API/UI

**작성일**: 2026-05-02
**버전**: 1.0
**상태**: 구현 완료

## 목적

LOCAL-FILE-MAP-2D의 실행 승인 요청서를 기반으로, 사용자가 선택한 저위험 정리 후보만 묶은 "정리 실행 패키지"를 생성한다.

핵심은 **실행 패키지 생성만 수행**하며, **실제 파일 조작은 수행하지 않는다**.

## 핵심 원칙

1. **실행 패키지 생성만 수행** - 실제 파일 이동/삭제 금지
2. `execution_enabled=false` 고정 - 실행 비활성화
3. `package_only=true` 고정 - 패키지 모드
4. 민감 파일, 중복, 고위험 파일 기본 제외
5. 삭제 작업은 operation_type에 포함하지 않음
6. 대용량 파일(1GB+)은 기본 제외 또는 별도 검토 대상

## API: GET/POST /api/file-map/cleanup-execution-package

### GET 요청

기본 패키지 초안 조회

```
GET /api/file-map/cleanup-execution-package?mode=mask_always
GET /api/file-map/cleanup-execution-package?mode=reveal_after_auth
```

### POST 요청

사용자가 선택한 그룹 기준으로 실행 패키지 생성

```json
POST /api/file-map/cleanup-execution-package?mode=mask_always
{
  "selected_group_ids": ["documents", "spreadsheets", "cad", "images", "archive"],
  "confirm_exclusions": true,
  "package_only": true
}
```

### 응답 구조

```json
{
  "ok": true,
  "generated_at": "2026-05-02T10:00:00Z",
  "package_id": "cleanup-package-local-1234567890",
  "package_only": true,
  "execution_enabled": false,
  "approval_required_for_execution": true,
  "mode": "mask_always",
  "auth_verified": false,
  "selected_groups": ["documents", "spreadsheets"],
  "excluded_groups": ["sensitive", "duplicates", "hold", "huge_files"],
  "summary": {
    "total_candidate_items": 1000,
    "included_items": 800,
    "excluded_items": 200,
    "estimated_total_size_bytes": 52428800
  },
  "operations": [
    {
      "operation_id": "op-1234567890-abc123",
      "operation_type": "move_preview",
      "current_path": "/home/user/docs/report.docx",
      "suggested_path": "01_업무문서",
      "category": "documents",
      "risk": "low",
      "masked": true,
      "requires_final_approval": true,
      "rollback_hint": {
        "from": "01_업무문서",
        "to": "/home/user/docs/report.docx"
      },
      "file_size_bytes": 1024000,
      "modified_time": "2026-04-20T10:00:00Z"
    }
  ],
  "preflight_checks": [
    { "message": "대상 경로 충돌 여부 확인 필요" },
    { "message": "파일 존재 여부 최종 확인 필요" },
    { "message": "실행 전 백업/복구 계획 확인 필요" }
  ],
  "blocked_operations": [
    {
      "reason": "민감문서 기본 제외",
      "count": 50,
      "group_id": "sensitive"
    },
    {
      "reason": "중복 검토 대상 기본 제외",
      "count": 100,
      "group_id": "duplicates"
    },
    {
      "reason": "대용량 파일(1GB+) 별도 검토 필요",
      "count": 10,
      "group_id": "huge_files"
    }
  ]
}
```

## 선택 가능 그룹

사용자가 선택할 수 있는 그룹:

| 그룹 ID | 라벨 | 위험도 | 설명 |
|---------|------|--------|------|
| documents | 업무문서 | low | 일반 문서, 보고서 |
| spreadsheets | 엑셀/정산 | low | 스프레드시트, 재무 내역 |
| cad | CAD/도면 | low | 설계도, 도면 파일 |
| images | 이미지/스캔 | low | 사진, 스캔 이미지 |
| archive | 설치파일 보관 | low | 1년 이상 미사용 설치파일 |

## 기본 제외 그룹

패키지에서 기본적으로 제외되는 그룹:

| 그룹 ID | 라벨 | 이유 | 상태 |
|---------|------|------|------|
| sensitive | 민감문서 | 민감정보 포함 | 수동 처리 필요 |
| duplicates | 중복검토 | 검토 필요 | 수동 확인 필요 |
| hold | 분류보류 | 미분류 파일 | 별도 검토 필요 |
| huge_files | 대용량 파일 | 1GB 이상 | 별도 검토 필요 |

## Operation 정책

### operation_type

패키지에서 지원하는 작업 타입:

| 타입 | 설명 | 권장 대상 |
|------|------|----------|
| `move_preview` | 파일 이동 미리보기 | 일반 파일 분류 |
| `archive_preview` | 아카이브 미리보기 | 설치파일 보관 |

### 금지되는 작업

다음 작업은 operation_type에 포함하지 않음:
- `delete_preview` - 삭제 작업
- `remove_preview` - 제거 작업
- 자동 삭제 관련 모든 작업

### Rollback Hint

모든 작업은 롤백 정보를 포함:

```json
{
  "from": "01_업무문서",
  "to": "/original/path/file.docx"
}
```

이 정보는 실행 후 문제 발생 시 원래 경로로 복원할 때 사용됨.

## 민감파일 제외 정책

**민감 파일 판정 기준**:
- 신분증, 주민등록증, 운전면허, 여권
- 통장 사본, 계좌 정보
- 급여, 노임 관련
- 형사 사건, 고소, 소송
- 변호인 의견서, 법률 문서
- 기밀 문서, 개인정보

**정책**:
- blocked_operations의 reason: "민감문서 기본 제외"
- 사용자가 수동으로 처리해야 함
- 패키지에서 자동 제외

## 중복 파일 제외 정책

**정책**:
- 자동 삭제 금지
- 중복 검토 필요 안내
- operation_type에 delete 타입 금지
- blocked_operations로 표시

## 대용량 파일 정책

**기준**: 파일 크기 ≥ 1GB

**정책**:
- isHugeFile(size) 함수로 판정
- 기본 제외
- blocked_operations의 group_id: 'huge_files'

## UI: 실행 패키지 탭

**위치**: `/file-map` 페이지의 다섯 번째 탭

**탭 목록**:
1. 파일 지도 리포트
2. 정리 계획표
3. 정리 미리보기
4. 실행 승인 요청서
5. **실행 패키지** (신규)

### UI 주요 요소

#### 1. 안내 문구
```
📦 실행 패키지 생성
이 화면은 실행 패키지 생성 단계입니다. 
아직 실제 파일 이동, 삭제, 이름변경, 폴더 생성은 수행하지 않습니다.
민감문서, 중복 검토 후보, 고위험 파일은 기본 실행 패키지에서 제외됩니다.
```

#### 2. 패키지 정보
- 고유한 package_id 표시
- "📦 패키지 준비" 상태 배지
- "🔒 실행 비활성화" 배지

#### 3. 통계 카드 (4개)
- 총 대상 파일 수
- 포함 예정 파일 수
- 제외된 파일 수
- 예상 총 크기

#### 4. 선택 가능 그룹
- 5개 그룹 체크박스
- 각 그룹별 포함될 파일 수 표시
- 기본값: 모두 선택

#### 5. 예상 작업 목록
- 상위 10개 파일 샘플
- 현재 경로 → 제안 경로
- 파일 크기
- 초과 파일 수 안내

#### 6. 사전 점검 체크리스트
```
⚠️ 실행 전 사전 점검
• 대상 경로 충돌 여부 확인 필요
• 파일 존재 여부 최종 확인 필요
• 실행 전 백업/복구 계획 확인 필요
```

#### 7. 기본 제외 항목
- 민감문서 - 개수
- 중복 검토 - 개수
- 대용량 파일 - 개수

#### 8. 롤백 참고정보
```
💾 롤백 참고정보
• 모든 파일 이동 작업은 기록되며, 원본 경로 정보가 보존됩니다
• 실행 후 문제가 발생한 경우 원본 경로로 복원 가능합니다
• 이동된 파일의 메타데이터(수정 시간 등)는 유지됩니다
• 중복/삭제 작업은 포함되지 않습니다
```

#### 9. 보안 및 정책 안내
```
🔐 보안 및 정책
• 민감문서, 중복 검토 후보, 고위험 파일은 기본 실행 패키지에서 제외됩니다
• 이 화면은 패키지 생성 단계만 제공합니다
• 삭제 작업은 패키지에 포함되지 않습니다
• 실제 파일 이동은 별도 최종 승인 단계에서만 가능합니다
```

#### 10. 패키지 생성 버튼
- "패키지 생성" 버튼 (활성화)
- POST 요청으로 사용자 선택 반영
- 준비 중 상태 표시

### 허용된 버튼 라벨

- "패키지 생성" (실행 패키지 생성)
- "선택 후보 확인" (그룹 토글)
- "다시 마스킹" (마스킹 재적용)

### 금지된 버튼 라벨

- "실행"
- "삭제"
- "이동"
- "적용"
- "정리 시작"
- "바로 정리"

## maskingMode 연동

API는 `mode` 파라미터를 통해 maskingMode 정책을 따른다:

| Mode | 동작 |
|------|------|
| `mask_always` | 항상 마스킹 |
| `reveal_after_auth` | 인증 시 원본 표시 (임시) |
| `reveal_on_trusted_device` | 이 PC에서 원본 표시 |
| `reveal_for_export_with_warning` | 외부 공유도 원본 허용 (항상 마스킹) |

## 안전성 보장

### 파일 조작 함수 제거

API와 UI 코드에 다음 함수가 없음:
- `fs.rename()`, `fs.unlink()`, `fs.rm()`, `fs.rmdir()`
- `shutil.move()`, `shutil.remove()`
- `mkdir()`, `copyFile()`

### 원본 패키지 저장 금지

- 원본 파일명 포함 패키지 파일 저장 금지
- localStorage에 원본 operations 저장 금지
- 다운로드용 원본 패키지 생성 금지
- 메모리 응답만 제공

### 민감정보 보호

- 비밀번호, PIN, secret 저장 금지
- 요청서는 기본 마스킹 적용
- console.log로 원본 파일명 출력 금지

### 실행 불가능 설계

- `execution_enabled=false` 고정
- `package_only=true` 고정
- 삭제 operation_type 금지
- 자동 삭제 버튼 없음

## 다음 단계: LOCAL-FILE-MAP-2F

실제 파일 이동 실행 기능은 **다음 단계 2F에서만 구현** 가능:

### 2F에서 수행할 수 있는 것

1. 별도의 "최종 실행 승인" 프로세스
2. execution_enabled 조건부 활성화
3. 패키지의 operations 실제 실행
4. 이동 로그 기록
5. 실패 시 롤백 지원

### 2F에서 금지되는 것

1. 민감문서 자동 이동
2. 중복 파일 자동 삭제
3. 사용자 확인 없는 대량 이동
4. 원본 파일명 노출

## 구현 파일

### API
- `admin-web/src/app/api/file-map/cleanup-execution-package/route.ts` (510줄)

### UI
- `admin-web/src/components/file-map/FileMapExecutionPackage.tsx` (360줄)

### 페이지
- `admin-web/src/app/file-map/page.tsx` (탭 추가)
- `admin-web/src/components/file-map/index.ts` (export 추가)

## 테스트 완료

- ✓ Lint: No ESLint warnings or errors
- ✓ Build: 성공, `/api/file-map/cleanup-execution-package` 등록
- ✓ 안전성: 파일 조작 함수 없음
- ✓ 안전성: 민감정보 저장 금지 준수
- ✓ 안전성: console.log 원본 출력 없음
- ✓ 안전성: 삭제 operation_type 없음
- ✓ API: package_only=true 고정
- ✓ API: execution_enabled=false 고정
- ✓ UI: 금지된 버튼명 없음
- ✓ UI: 패키지 생성 버튼 있음
