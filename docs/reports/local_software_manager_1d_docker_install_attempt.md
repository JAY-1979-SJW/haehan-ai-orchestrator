# Docker Desktop 사용자 승인형 설치 실행 (1D)

**생성일**: 2026-05-02  
**상태**: 설치 프레임워크 완료, 설치파일 없음 (B안)

---

## 개요

LOCAL-SOFTWARE-MANAGER-1C에서 구현한 설치 실행 프레임워크를 기반으로,
**Docker Desktop만** 실제 설치를 시도한다.

이번 1D는 단일 프로그램 전용:
- ✅ Docker Desktop만 대상
- ❌ 다른 프로그램 설치 절대 금지
- ✅ 사용자 명시적 승인 필수 (approval_token + user_confirmed_install=true)
- ❌ 관리자 비밀번호 저장/요청 금지
- ✅ UAC 팝업은 사용자가 직접 승인

---

## 현재 환경 상태

| 항목 | 상태 |
|------|------|
| **Docker 설치** | ❌ 미설치 |
| **docker CLI PATH** | ❌ 없음 |
| **Docker Desktop Installer.exe** | ❌ Downloads 폴더 없음 |
| **처리 방식** | B안 (공식 URL 안내) |

### 진단 결과

```
$ docker --version
docker: not installed or not in PATH

$ ls /c/Users/skyjw/Downloads/ | grep -i docker
(no docker files)
```

---

## 실행 조건 및 정책

### 설치 실행 요청 필수 필드

```json
{
  "action": "local_software.install",
  "program_id": "docker",
  "approval_token": "user-approved-token",
  "dry_run": false,
  "user_confirmed_install": true,
  "local_installer_path": null
}
```

### 실행 차단 조건

- `program_id != "docker"` → 실행 차단
- `approval_token` 없음 → 실행 차단
- `dry_run = true` → 계획만 반환 (dry_run=false 필수)
- `user_confirmed_install = false` → 실행 차단
- Docker 이미 설치됨 → already_installed 반환

---

## 설치파일 처리

### 현재: B안 (설치파일 없음)

```
A안: 사용자가 이미 다운로드한 설치파일 사용
     - 파일명: "Docker Desktop Installer.exe"
     - 경로 검증: Downloads 또는 명시 경로
     - **현재: 파일 없음**

B안: 설치파일 없으면 공식 URL 안내 (현재 상태)
     - 반환: "download_required"
     - URL: https://www.docker.com/products/docker-desktop/
     - 메시지: "Docker Desktop을 다운로드하여 설치하세요."
```

### B안 응답 구조

```json
{
  "status": "download_required",
  "docker_cli_installed": false,
  "docker_compose_installed": false,
  "reboot_may_be_required": false,
  "next_step": "Docker Desktop을 다운로드하여 설치하세요.",
  "official_url": "https://www.docker.com/products/docker-desktop/",
  "error": null
}
```

---

## 실제 설치 실행 (A안 코드)

설치파일이 있을 경우 아래와 같이 실행:

### 1. 설치파일 검증

```python
validator = DockerInstallerValidator()
success, error = validator.validate_path(installer_path)

검증 항목:
- 경로 존재 여부
- 확장자 .exe 확인
- 파일명 allowlist 확인
  * "Docker Desktop Installer.exe"
  * "DockerDesktopInstaller.exe"
```

### 2. 설치 실행 (UAC 팝업)

```powershell
Start-Process -FilePath "C:\Users\...\Docker Desktop Installer.exe" -Verb RunAs -Wait
```

**주의:**
- UAC 팝업이 나타남 → 사용자가 직접 "예" 클릭 (관리자 비밀번호 입력 안 함)
- 자동 설치 인자 없음 (--accept-license 미사용)
- silent install 미사용
- UAC 우회 금지

### 3. 설치 후 검증

```bash
docker --version
docker compose version
docker info
```

### 결과 판정

```
상태: install_completed / install_failed
- docker --version 성공 → docker_cli_installed=true
- docker compose version 성공 → docker_compose_installed=true
- 둘 다 실패 → 재부팅 필요 (reboot_may_be_required=true)
```

---

## 안전성 보장

### 이번 1D에서 수행하는 것

| 항목 | 상태 |
|------|------|
| **approval_token 검증** | ✅ |
| **user_confirmed_install 필수** | ✅ |
| **allowlist 제한 (Docker만)** | ✅ |
| **설치파일 검증** | ✅ |
| **A안: UAC 팝업** | ✅ (코드: Start-Process -Verb RunAs) |
| **B안: 공식 URL 안내** | ✅ (현재) |

### 이번 1D에서 금지하는 것

| 항목 | 상태 |
|------|------|
| **다른 프로그램 설치** | ❌ 금지 |
| **자동 다운로드** | ❌ 금지 |
| **관리자 비밀번호 저장** | ❌ 금지 |
| **관리자 비밀번호 요청** | ❌ 금지 |
| **UAC 우회** | ❌ 금지 |
| **silent install** | ❌ 금지 |
| **--accept-license** | ❌ 금지 |
| **재부팅 자동 실행** | ❌ 금지 |
| **삭제/제거** | ❌ 금지 |

---

## 다음 단계 (향후)

### A안 활성화 (설치파일 있을 경우)

1. 사용자가 `https://www.docker.com/products/docker-desktop/`에서 설치파일 다운로드
2. 설치파일을 `C:\Users\{user}\Downloads\Docker Desktop Installer.exe`에 저장
3. `local_software.install` 호출 with:
   ```json
   {
     "local_installer_path": "C:\\Users\\...\\Downloads\\Docker Desktop Installer.exe",
     "user_confirmed_install": true
   }
   ```
4. Start-Process -Verb RunAs로 설치 실행
5. UAC 팝업 → 사용자가 직접 "예" 클릭
6. 설치 후 docker --version 등으로 검증

---

## 파일 구조

```
agent/local_software_manager/
├── docker_installer.py (신규 1D)
│   ├── DockerInstallerValidator
│   ├── DockerInstallResult
│   └── DockerInstaller
└── install_executor.py (수정 1D)
    └── _execute_docker() 메서드 추가

agent/tests/
└── test_local_software_install_docker.py (신규 1D, 12개 테스트)

docs/reports/
└── local_software_manager_1d_docker_install_attempt.md
```

---

## 주의사항

### ✅ 이번 1D에서 구현한 것

- Docker Desktop 전용 설치 엔진
- 설치파일 검증 (allowlist 기반)
- A안 코드 (Start-Process -Verb RunAs)
- B안 처리 (공식 URL 안내)
- 설치 전/후 상태 진단
- 재부팅 필요 여부 판정
- 실패 시 원인 분류

### ❌ 이번 1D에서 제외된 것

- 다른 프로그램 설치 (Git/Python/Node 등)
- 자동 다운로드
- 관리자 비밀번호 저장/요청
- UAC 우회
- 자동 재부팅

---

## 정책 선언

**이번 1D 단계에서는:**

1. **Docker Desktop만** 실제 설치 시도
2. **approval_token + user_confirmed_install** 모두 필수
3. **설치파일 없으면** B안 (공식 URL 안내)
4. **설치파일 있으면** A안 (Start-Process -Verb RunAs)
5. **UAC는 사용자가 직접 승인** (팝업 → "예" 클릭)
6. **관리자 비밀번호 저장 절대 금지**
7. **UAC 우회 금지**
8. **다른 프로그램 설치 절대 금지**
9. **설치 전후 상태 기록**
10. **실패 시 원인만 보고, 자동 재시도 금지**

---

**버전**: 1.0  
**상태**: LOCAL-SOFTWARE-MANAGER-1D-DOCKER  
**실행 결과**: B안 (download_required, 설치파일 없음)
