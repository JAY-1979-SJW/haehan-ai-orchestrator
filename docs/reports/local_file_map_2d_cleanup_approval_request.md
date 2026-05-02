# LOCAL-FILE-MAP-2D: 정리 실행 승인 요청서 API/UI

**작성일**: 2026-05-02
**버전**: 1.0
**상태**: 구현 완료

## 목적

LOCAL-FILE-MAP-2C의 정리 미리보기를 기반으로, 사용자가 실제 파일 이동 전에 승인할 수 있는 "정리 실행 승인 요청서" 기능을 제공한다.

핵심은 **승인 요청서 생성만 수행**하며, **실제 파일 조작은 수행하지 않는다**.

## 핵심 원칙

1. **승인 요청서 생성만 수행** - 실제 파일 이동/삭제 금지
2. `execution_enabled=false` 고정 - 실행 비활성화
3. `request_only=true` 고정 - 요청서 모드
4. 민감 파일, 고위험 파일 기본 제외
5. 중복 검토 후보는 "수동 확인 필요"로 표시

## API: GET /api/file-map/cleanup-approval-request

### 요청 파라미터

```
GET /api/file-map/cleanup-approval-request?mode=mask_always
GET /api/file-map/cleanup-approval-request?mode=reveal_after_auth
GET /api/file-map/cleanup-approval-request?mode=reveal_on_trusted_device
```

### 응답 구조

```json
{
  "ok": true,
  "generated_at": "2026-05-02T10:00:00Z",
  "approval_request_id": "preview-local-1234567890",
  "approval_required": true,
  "execution_enabled": false,
  "request_only": true,
  "mode": "mask_always",
  "auth_verified": false,
  "summary": {
    "total_preview_items": 1000,
    "auto_selectable_items": 800,
    "excluded_sensitive_items": 150,
    "excluded_high_risk_items": 150,
    "duplicate_review_items": 50
  },
  "approval_groups": [
    {
      "group_id": "documents",
      "label": "업무문서",
      "default_selected": true,
      "risk": "low",
      "item_count": 300,
      "items": [
        {
          "current_path": "/home/user/docs/report.docx",
          "suggested_path": "01_업무문서",
          "category": "documents",
          "risk": "low",
          "file_size_bytes": 1024000,
          "modified_time": "2026-04-20T10:00:00Z"
        }
      ]
    }
  ],
  "excluded_groups": [
    {
      "group_id": "sensitive",
      "label": "민감문서",
      "reason": "민감정보 포함으로 기본 실행 대상 제외",
      "item_count": 150,
      "items": []
    }
  ],
  "checklist": [
    "실제 파일 이동 전 최종 확인 필요",
    "민감문서는 기본 제외됨",
    "중복 파일은 수동 확인 후 삭제",
    "대용량 파일(1GB+)은 별도 검토 필요"
  ]
}
```

## 기본 선택 가능 그룹

실행 승인 요청서에서 사용자가 선택 가능한 그룹:

| 그룹 ID | 라벨 | 위험도 | 기본 선택 |
|---------|------|--------|----------|
| documents | 업무문서 | low | ✓ |
| spreadsheets | 엑셀/정산 | low | ✓ |
| cad | CAD/도면 | low | ✓ |
| images | 이미지/스캔 | low | ✓ |
| archive | 설치파일 보관 | low | ✓ |

## 기본 제외 그룹

실행 승인 요청서에서 기본적으로 제외되는 그룹:

| 그룹 ID | 라벨 | 이유 | 위험도 |
|---------|------|------|--------|
| sensitive | 민감문서 | 민감정보 포함으로 기본 실행 대상 제외 | high |
| duplicates | 중복검토 | 자동 삭제 불가능, 수동 확인 필요 | medium |

## 민감문서 제외 정책

**민감 파일 판정 기준**:
- 신분증, 주민등록증, 운전면허, 여권
- 통장 사본, 계좌 정보, 급여, 노임
- 형사 사건, 고소, 소송 관련 문서
- 변호인 의견서, 법률 문서
- 기밀 문서, 개인정보 포함 파일

**정책**:
- 민감 파일은 자동으로 excluded_groups에 배치
- UI에서 "기본 제외 그룹"으로 표시
- 사용자가 수동으로 처리해야 함
- 요청서에서는 확인만 가능, 자동 이동 불가

## 중복 자동삭제 금지 정책

**이유**:
- 중복 판정 기준 불명확
- 사용자 검증 필수
- 의도하지 않은 파일 손실 위험

**정책**:
- 중복 파일은 "중복검토" 그룹으로 excluded_groups 배치
- UI 안내: "수동 확인 후 삭제"
- 자동 삭제 기능 금지
- 다음 단계(2E)에서도 중복 자동삭제 기능 구현 금지

## UI: 실행 승인 요청서 탭

**위치**: `/file-map` 페이지의 네 번째 탭

**탭 목록**:
1. 파일 지도 리포트
2. 정리 계획표
3. 정리 미리보기
4. **실행 승인 요청서** (신규)

### UI 주요 요소

#### 1. 안내 문구
```
📋 실행 승인 요청서
이 화면은 실행 승인 요청서입니다. 실제 파일은 아직 변경되지 않았습니다.
민감문서와 중복 검토 후보는 기본 실행 대상에서 제외됩니다.
```

#### 2. 요청 ID 및 상태
- 고유한 approval_request_id 표시
- 요청 검토 중 상태 배지
- 실행 비활성화 안내

#### 3. 요약 카드 (5개)
- 총 파일 수
- 선택 가능 파일 수
- 중복 검토 필요 파일 수
- 민감문서 수
- 현재 선택된 파일 수

#### 4. 기본 선택 가능 그룹
- 체크박스로 그룹별 선택 가능
- 기본값: 모두 선택 (default_selected=true인 그룹)
- 그룹 확장/축소로 파일 샘플 표시
- 위험도 배지 표시

#### 5. 기본 제외 그룹
- 읽기 전용 표시 (체크박스 없음)
- 제외 이유 표시
- 그룹 확장/축소로 파일 샘플 표시
- 배경색: 회색(비활성)

#### 6. 체크리스트
```
⚠️ 주의사항
• 실제 파일 이동 전 최종 확인 필요
• 민감문서는 기본 제외됨
• 중복 파일은 수동 확인 후 삭제
• 대용량 파일(1GB+)은 별도 검토 필요
```

#### 7. 보안 정책 안내
```
🔐 보안 정책
• 민감문서는 기본 제외되며, 수동으로만 처리 가능
• 중복 파일은 자동 삭제하지 않으며, 수동 확인 필요
• 이 화면은 요청서만 표시합니다
• 실제 파일 이동은 다음 단계에서 별도 승인 필요
```

### 금지된 버튼

다음 버튼은 절대 구현하지 않음:
- "실행"
- "삭제"
- "이동"
- "정리 시작"
- "적용"

### 허용된 버튼 라벨

- "요청서 보기" (읽기 전용)
- "선택 후보 확인" (그룹 토글)
- "다시 마스킹" (마스킹 재적용)

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

### 민감정보 보호

- 비밀번호, PIN, secret 저장 금지
- 원본 파일명을 localStorage/sessionStorage에 저장하지 않음
- 요청서는 기본 마스킹 적용
- console.log로 원본 파일명 출력 금지

### 실행 불가능 설계

- `execution_enabled=false` 고정
- `request_only=true` 고정
- 실제 파일 조작 버튼 없음
- 실행 토큰 생성 금지

## 다음 단계: LOCAL-FILE-MAP-2E

실제 파일 이동 실행 기능은 **다음 단계 2E에서만 구현** 가능:

### 2E에서 수행할 수 있는 것

1. 별도의 "실행 승인" 프로세스
2. execution_enabled 조건부 활성화
3. 파일 이동/삭제 실행 (단, 민감문서/중복 제외)
4. 이동 로그 기록

### 2E에서 금지되는 것

1. 민감문서 자동 이동
2. 중복 파일 자동 삭제
3. 사용자 확인 없는 대량 삭제
4. 원본 파일명 노출

## 구현 파일

### API
- `admin-web/src/app/api/file-map/cleanup-approval-request/route.ts` (390줄)

### UI
- `admin-web/src/components/file-map/FileMapApprovalRequest.tsx` (400줄)

### 페이지
- `admin-web/src/app/file-map/page.tsx` (탭 추가)
- `admin-web/src/components/file-map/index.ts` (export 추가)

## 테스트 완료

- ✓ Lint: No ESLint warnings or errors
- ✓ Build: 성공, `/api/file-map/cleanup-approval-request` 등록
- ✓ 안전성: 파일 조작 함수 없음
- ✓ 민감정보: 저장 금지 정책 준수
- ✓ 버튼: 금지된 버튼명 없음
- ✓ execution_enabled: false 고정
- ✓ request_only: true 고정
