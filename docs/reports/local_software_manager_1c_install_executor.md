# 로컬 소프트웨어 설치 실행 프레임워크 (1C)

**생성일**: 2026-05-02  
**상태**: dry_run 프레임워크 (실행 금지, 1D에서 개별 활성화)

---

## 개요

LOCAL-SOFTWARE-MANAGER-1B에서 생성한 설치 계획표를 기반으로,
사용자 승인 토큰 + dry_run 제어를 통한 **안전한 설치 실행 프레임워크**를 구현한다.

이번 1C는 "프레임워크 뼈대" 단계:
- ✅ **dry_run=true** (기본값): 설치 계획 단계만 반환
- ✅ **approval_token**: 필수 검증
- ✅ **allowlist**: 9개 프로그램만 허용
- ❌ **dry_run=false**: execution_not_enabled_yet으로 차단 (1D에서 열기)

---

## 핵심 정책

| 정책 | 1C 상태 | 설명 |
|------|--------|------|
| **dry_run 기본값** | `True` | 실제 설치 미수행 |
| **approval_token** | 필수 | 사용자 명시적 승인 필수 |
| **allowlist** | 9개 | docker, git, python, node, chrome, vscode, hancom, office, autocad |
| **dry_run=true** | 실행 | planned_steps 반환 (계획 단계 명시) |
| **dry_run=false** | 차단 | execution_not_enabled_yet (1D에서 프로그램별 활성화) |
| **execution_enabled** | 항상 False | 설치 실행 절대 금지 |

---

## 설치 실행 액션

### 액션 정의

```json
{
  "action": "local_software.install",
  "category": "local_environment",
  "risk_level": "HIGH",
  "requires_approval": true,
  "requires_admin": false,
  "read_only": false
}
```

### 요청 구조

```json
{
  "action": "local_software.install",
  "program_id": "docker",
  "approval_token": "user-approved-token",
  "dry_run": true
}
```

### 응답 구조 (dry_run=true)

```json
{
  "ok": true,
  "data": {
    "ok": true,
    "dry_run": true,
    "program_id": "docker",
    "program_name": "Docker Desktop",
    "execution_enabled": false,
    "requires_approval": true,
    "requires_admin": true,
    "requires_reboot": true,
    "planned_steps": [
      "공식 설치 페이지 열기: https://www.docker.com/products/docker-desktop/",
      "사용자가 설치파일 다운로드",
      "관리자 권한으로 설치파일 실행",
      "필요시 시스템 재부팅",
      "라이선스 약관 확인 및 동의",
      "설치 후 docker --version 또는 경로 검증"
    ],
    "blocked_actions": [
      "download",
      "install_execute",
      "admin_elevation"
    ],
    "current_status": "missing",
    "install_required": true,
    "next_step": "dry_run 계획 검토 후 실제 실행 단계에서 진행"
  }
}
```

### 응답 구조 (dry_run=false, 1C에서 차단)

```json
{
  "ok": false,
  "error": "execution_not_enabled_yet",
  "data": {
    "program_id": "docker",
    "program_name": "Docker Desktop",
    "next_step": "설치 실행은 1D 단계에서 프로그램별로 개별 활성화"
  }
}
```

---

## 안전성 보장

### 이번 1C에서 금지된 작업

| 작업 | 1A | 1B | 1C | 1D |
|------|-----|-----|-----|-----|
| 설치 진단 | ✅ | - | - | - |
| 설치 계획 생성 | - | ✅ | - | - |
| **실제 다운로드** | ❌ | ❌ | ❌ | TBD |
| **실제 설치 실행** | ❌ | ❌ | ❌ | TBD |
| **winget install** | ❌ | ❌ | ❌ | TBD |
| **choco install** | ❌ | ❌ | ❌ | TBD |
| **msiexec** | ❌ | ❌ | ❌ | TBD |
| **Start-Process -Verb RunAs** | ❌ | ❌ | ❌ | TBD |
| **재부팅 실행** | ❌ | ❌ | ❌ | TBD |
| **관리자 비밀번호 저장** | ❌ | ❌ | ❌ | ❌ |
| **UAC 우회** | ❌ | ❌ | ❌ | ❌ |
| **프로그램 삭제/제거** | ❌ | ❌ | ❌ | ❌ |

### grep 검사 결과

```bash
# 설치 명령: winget, choco, msiexec, RunAs
$ grep -r "winget install\|choco install\|msiexec\|Start-Process.*RunAs" \
  agent/local_software_manager agent/tests
# 결과: 없음 ✓

# 다운로드 명령: download, urlretrieve, requests.get, httpx.get
$ grep -r "download\|urlretrieve\|requests.get\|httpx.get" \
  agent/local_software_manager
# 결과: 없음 ✓

# 파일 조작: unlink, remove, rmdir, rename
$ grep -r "unlink\|remove\|rmdir\|rename" agent/local_software_manager
# 결과: 없음 ✓

# 비밀번호 저장: password, secret
$ grep -r "password\s*=\|secret\s*=" agent/local_software_manager agent/tests
# 결과: 없음 ✓
```

---

## 설치 계획 예시

### Docker Desktop

```
공식 설치 페이지 열기: https://www.docker.com/products/docker-desktop/
사용자가 설치파일 다운로드
관리자 권한으로 설치파일 실행
필요시 시스템 재부팅
라이선스 약관 확인 및 동의
설치 후 docker --version 또는 경로 검증
```

**차단된 작업**:
- download (자동 다운로드 금지)
- install_execute (설치 실행 금지)
- admin_elevation (관리자 권한 요청 금지)

### Git

```
공식 설치 페이지 열기: https://git-scm.com/download/win
사용자가 설치파일 다운로드
설치파일 실행
라이선스 약관 확인 및 동의
설치 후 git --version 또는 경로 검증
```

**차단된 작업**:
- download
- install_execute
- admin_elevation

---

## 9개 허용 프로그램

| # | 프로그램 | 관리자 권한 | 재부팅 가능 | 라이선스 고지 |
|----|---------|-----------|-----------|------------|
| 1 | Docker Desktop | ⚠️ 필요 | ⚠️ 있음 | ⚠️ 필요 |
| 2 | Git | - | - | - |
| 3 | Python | - | - | - |
| 4 | Node.js | - | - | - |
| 5 | Google Chrome | - | - | - |
| 6 | Visual Studio Code | - | - | - |
| 7 | Hancom Office | ⚠️ 필요 | ⚠️ 있음 | ⚠️ 필요 |
| 8 | Microsoft Office | ⚠️ 필요 | ⚠️ 있음 | ⚠️ 필요 |
| 9 | Autodesk AutoCAD | ⚠️ 필요 | ⚠️ 있음 | ⚠️ 필요 |

---

## 1D로 향한 다음 단계

1C는 프레임워크만 제공하고, 실제 설치 활성화는 **1D에서**:

- dry_run=false도 현재는 execution_not_enabled_yet으로 차단
- 프로그램별로 개별 활성화 필요 (Docker → Git → Python → ...)
- 실제 설치 래퍼 함수 구현
- 설치 후 자동 검증 함수
- 실패 시 롤백 정책 (optional)

---

## 주의사항

### ✅ 이번 1C에 포함된 것

- 설치 실행 프레임워크
- 승인 토큰 검증
- Allowlist 기반 제한
- dry_run 계획 생성
- 실행 전 검증
- 설치 후 검증 함수 골격
- 실제 실행 차단 기본값

### ❌ 이번 1C에서 제외된 것

- 실제 다운로드
- 실제 설치 실행
- 관리자 권한 요청
- 시스템 재부팅
- 프로그램 삭제/제거
- 비밀번호/PIN 저장

---

## 테스트

### 검증 항목 (27개 테스트 총합)

```
1A 13개: 소프트웨어 진단 (통과 ✓)
1B 14개: 설치 계획 생성 (통과 ✓)
1C 14개: 설치 실행 프레임워크
├─ Validator (3개)
│  ├─ approval_token 검증
│  ├─ program_id 검증
│  └─ allowlist 검증
├─ Executor (6개)
│  ├─ dry_run 기본값
│  ├─ dry_run=true 계획 반환
│  ├─ dry_run=false 차단
│  ├─ 설치 불필요 처리
│  ├─ 계획 단계 생성
│  └─ execution_enabled 항상 False
├─ Allowlist (2개)
│  ├─ 9개 프로그램 확인
│  └─ 미지 프로그램 거부
└─ Safety (3개)
   ├─ 설치 명령 없음
   ├─ 다운로드 명령 없음
   └─ 비밀번호 저장 없음
```

---

## 파일 구조

```
agent/
├── local_software_manager/
│   ├── __init__.py (수정: InstallExecutor export)
│   ├── models.py (1A)
│   ├── catalog.py (1A)
│   ├── detector.py (1A)
│   ├── report_builder.py (1A)
│   ├── install_plan.py (1B)
│   ├── install_sources.py (1B)
│   ├── install_validator.py (신규 1C)
│   └── install_executor.py (신규 1C)
├── action_registry.py (수정: CATEGORY_LOCAL_ENVIRONMENT + local_software.install)
├── task_executor.py (수정: _run_local_software_install 핸들러)
├── errors.py (수정: INSTALL_* 에러 코드)
└── tests/
    ├── test_local_software_manager.py (1A, 13개)
    ├── test_local_software_install_plan.py (1B, 14개)
    └── test_local_software_install_executor.py (신규 1C, 14개)
```

---

## 정책 선언

**이번 1C 단계에서는:**

- 모든 설치 요청을 **approval_token으로 검증**
- 모든 설치를 **allowlist로 제한**
- 모든 설치를 **dry_run 기본값으로 보호**
- 모든 설치를 **execution_not_enabled_yet으로 차단** (1D에서 열기)
- **실제 다운로드/설치/UAC/재부팅 절대 금지**
- **관리자 비밀번호 저장 절대 금지**
- **사용자 동의 없는 작업 절대 금지**

---

**버전**: 1.0  
**상태**: LOCAL-SOFTWARE-MANAGER-1C  
**실행 가능**: 아니오 (프레임워크 단계, 1D에서 활성화)
