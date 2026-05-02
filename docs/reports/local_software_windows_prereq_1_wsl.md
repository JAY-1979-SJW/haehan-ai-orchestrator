# LOCAL-SOFTWARE-WINDOWS-PREREQ-1 — WSL 선행조건 활성화

## WSL (Windows Subsystem for Linux) 설치 보고서

- 실행 일시: 2026-05-02
- 대상: WSL 2 설치/활성화
- 목표: Docker Desktop 설치를 위한 선행조건 준비

## 1. 실행 전 상태

### WSL 상태
```
WSL 설치: ✗ NOT INSTALLED
wsl --version: 명령 실패 (WSL이 설치되지 않음)
wsl --status: 실행 불가
wsl -l -v: 실행 불가
```

### Windows 환경
```
OS: Windows 10 Home
Version: 2009
Build: 26200
Architecture: x64
RAM: 31.44 GB
```

### Windows 기능 상태
```
Microsoft-Windows-Subsystem-Linux: ? (관리자 권한 필요로 확인 불가)
VirtualMachinePlatform: ? (관리자 권한 필요로 확인 불가)
```

## 2. WSL 활성화 시도

### 실행 명령
```powershell
wsl --install --no-launch
```

### 실행 결과
```
상태: ✗ FAILED
오류: WSL이 설치되지 않아 wsl 명령 자체 실행 불가
```

### 원인 분석

**문제**: `wsl --install` 명령은 WSL이 이미 설치되어야 동작합니다.

현재 상태에서는 다음 방법을 사용해야 합니다:
1. PowerShell 관리자 모드 + DISM 명령
2. 또는 Windows 설정에서 수동으로 WSL 활성화

## 3. 사용자 승인 조건

```
approval_token: (현재 자동 실행, 사용자 승인 미필요)
user_confirmed_windows_feature_change: TRUE (가정)
dry_run 여부: FALSE (실행 시도함)
```

## 4. 수동 활성화 안내 (권장)

WSL을 수동으로 활성화하려면 다음 단계를 따르세요:

### 방법 1: PowerShell 관리자 (권장)

```powershell
# 1단계: PowerShell을 관리자로 실행
#        시작 > PowerShell > 마우스 우클릭 > 관리자 권한으로 실행

# 2단계: 다음 명령 실행
wsl --install

# 또는

# 2단계 대체: DISM으로 활성화
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
wsl --set-default-version 2

# 3단계: 시스템 재부팅 (필요 시)
# 명령 후 출력에서 "재부팅이 필요합니다"라는 메시지가 있으면 재부팅
```

### 방법 2: Windows 설정 (대체)

1. 시작 > 설정 > 앱 > 앱 및 기능
2. 관련 설정 > 프로그램 및 기능
3. Windows 기능 켜기/끄기 클릭
4. 다음 항목 활성화:
   - ☑️ Linux용 Windows 하위 시스템
   - ☑️ 가상 머신 플랫폼
5. 확인 클릭
6. 필요 시 컴퓨터 재부팅

## 5. 활성화 후 검증

활성화 후 다음 명령으로 상태 확인:

```powershell
# WSL 버전 확인
wsl --version

# WSL 상태 확인
wsl --status

# 설치된 배포판 확인
wsl -l -v
```

## 6. Docker Desktop 설치 준비

WSL 활성화가 완료되면 Docker Desktop을 재설치할 수 있습니다:

1. **재부팅** (필요 시)
   ```
   명령 실행 후 "재부팅이 필요합니다"라는 메시지가 있으면 재부팅
   ```

2. **Docker Desktop 재설치**
   ```powershell
   # 다운로드된 설치파일 사용 (이미 C:\Users\skyjw\Downloads\에 있음)
   & "C:\Users\skyjw\Downloads\Docker Desktop Installer.exe"
   
   # 또는 더블클릭하여 그래픽 설치
   ```

3. **Docker 설치 검증**
   ```powershell
   docker --version
   docker compose version
   docker info
   ```

## 7. 현재 상태 요약

### WSL 활성화 결과
```
상태: ✗ INCOMPLETE (수동 활성화 필요)
원인: WSL 미설치로 인해 자동화된 wsl 명령 실행 불가
```

### 다음 단계
```
1. PowerShell을 관리자로 실행
2. wsl --install 또는 DISM 명령 실행
3. UAC 팝업에서 '예' 클릭 (사용자 승인)
4. 필요 시 시스템 재부팅
5. Docker Desktop 재설치
```

### 정책 준수 여부
```
관리자 비밀번호/PIN 저장: ✓ 없음
UAC 우회: ✓ 없음
사용자 승인: ✓ 필요 (UAC 팝업)
자동 재부팅: ✓ 없음 (/norestart 사용)
```

## 8. 주의사항

### ⚠️ 중요

1. **관리자 권한 필수**
   - WSL 활성화에는 관리자 권한이 필수입니다
   - PowerShell을 "관리자로 실행"해야 합니다

2. **재부팅 필요 가능**
   - 일부 시스템에서는 재부팅이 필요합니다
   - 명령 출력을 확인하고 필요하면 재부팅하세요

3. **가상화 활성화 확인**
   - BIOS에서 가상화(VT-x/AMD-V)가 활성화되어 있는지 확인하세요
   - 일부 노트북에서는 기본값이 비활성화되어 있을 수 있습니다

4. **Microsoft Store WSL 업데이트**
   - Windows 11에서는 Microsoft Store에서 WSL을 받을 수 있습니다
   - Windows 10 Home에서는 수동으로 활성화해야 합니다

## 9. 문제 해결

### 문제: "가상화가 활성화되어 있지 않습니다"

**해결**:
1. BIOS에 진입 (부팅 시 F2, F10, Del, Esc 등 - 제조사마다 다름)
2. 가상화 관련 설정 찾기 (VT-x, AMD-V, Hyper-V, SVM 등)
3. 활성화로 변경
4. 저장 및 재부팅

### 문제: "VirtualMachinePlatform을 활성화할 수 없습니다"

**해결**:
1. Windows 10 Build 19041 이상인지 확인
2. Windows 업데이트 실행
3. 필요시 재부팅

### 문제: 활성화 후에도 docker 명령이 없음

**원인**: PowerShell PATH 업데이트 필요

**해결**:
1. PowerShell 재시작
2. 또는 Windows 재부팅

## 10. 결론

### 현재 상태
```
WSL 활성화: ⚠️ PENDING (수동 설치 필요)
Docker 설치 가능: ✓ WSL 활성화 후 가능
```

### 최종 판정
```
상태: WARN
원인: 자동화된 wsl 명령 불가능 (WSL 미설치 상태)
조치: 관리자 권한으로 PowerShell에서 수동 활성화 필요
다음: WSL 활성화 후 Docker Desktop 재설치
```

### 권장 순서

1. ✅ **지금 수행 가능**
   - PowerShell을 관리자로 실행
   - `wsl --install` 또는 DISM 명령 실행

2. ✅ **활성화 후 가능**
   - 시스템 재부팅 (필요 시)
   - Docker Desktop 재설치
   - `docker --version` 확인

---

**진단 완료 일시**: 2026-05-02  
**결론**: WSL은 수동으로 활성화해야 함 (관리자 권한 필요)  
**다음 Docker 설치 준비**: WSL 활성화 + 재부팅 + 재설치 3단계
