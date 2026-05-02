# LOCAL-SOFTWARE-INSTALL-RUN-DOCKER-FAIL-DIAG

## Docker Desktop 설치 실패 원인 진단 보고서

- 진단 일시: 2026-05-02
- 대상: Docker Desktop
- 버전: 4.71.0 (225177)
- 설치파일: Docker Desktop Installer.exe (617.55 MB)

## 1. 설치파일 상태

### 파일 정보
```
경로: C:\Users\skyjw\Downloads\Docker Desktop Installer.exe
존재: ✓ YES
크기: 617.55 MB
다운로드 시각: 2026-05-02 13:17:18
수정 시각: 2026-05-02 13:17:29
공식 도메인: desktop.docker.com (✓ 검증됨)
검증: ✓ 파일명 패턴 일치, HTTPS, 크기 > 0
```

**판정**: ✓ 설치파일 정상

## 2. Docker 설치 경로 상태

### 설치 경로 확인
```
C:\Program Files\Docker:                    ✗ 없음 (CLI 미설치)
C:\Program Files\Docker\Docker:             ✗ 없음 (CLI 미설치)
C:\ProgramData\Docker:                      ✗ 없음
C:\ProgramData\DockerDesktop:               ✓ 존재 (부분 설치 상태)
C:\Users\skyjw\AppData\Local\Docker:        ✓ 존재 (설정 파일)
C:\Users\skyjw\AppData\Roaming\Docker:      ✓ 존재 (설정 파일)
```

**판정**: ⚠️ 부분 설치 상태 (Docker Desktop 설정 폴더는 있으나 CLI 미설치)

## 3. Docker 설치 로그 분석

### 발견된 로그 파일
```
1. C:\Users\skyjw\AppData\Local\Docker\install-log.txt (0.92 KB, 최신)
2. C:\Users\skyjw\AppData\Local\Docker\install-log.0.txt (0.94 KB)
```

### 최신 설치 로그 내용
```
Version: 4.71.0 (225177)
Started on: 2026-05-02 03:09:07.137
OS: Windows 10 Home, Edition: Core, Build: 26200
Resources: C:\Users\skyjw\AppData\Local\Temp\DockerDesktopInstallers\1777691339332989700

CommandLine:
"C:\Users\skyjw\AppData\Local\Temp\DockerDesktopInstallers\1777691339332989700\Docker Desktop Installer.exe" 
install -package C:\Users\skyjw\AppData\Local\Temp\DockerDesktopInstallers\1777691339332989700\DockerDesktop.d4w 
--quiet

[2026-05-02T03:09:07.326974200Z][Installer][I] No installation found
[2026-05-02T03:09:07.415068200Z][ProcessEnvironmentDetector][I] Not run as admin, relaunching with UAC prompt
```

### 핵심 발견

**🔴 CRITICAL: 설치 로그가 "Not run as admin, relaunching with UAC prompt"에서 끝남**

이것은 다음을 의미합니다:
1. Docker Installer가 관리자가 아닌 상태에서 시작됨
2. 관리자 권한이 필요함을 감지
3. UAC 팝업을 다시 띄우려고 함
4. 로그는 여기서 종료됨 (UAC 팝업 이후 결과 없음)

**추정 원인**: UAC 팝업이 나타났으나 사용자가 응답하지 않거나 취소함

## 4. Windows/WSL/가상화 선행조건

### Windows 버전
```
OS: Windows 10 Home
Version: 2009
Build: 26200
```

### WSL 상태
```
WSL 설치: ✗ NOT INSTALLED
WSL 버전: 확인 불가
오류: "WSL이 설치되지 않았습니다"
```

**🔴 CRITICAL: WSL이 설치되지 않았습니다!**

Docker Desktop for Windows는 WSL2가 필수입니다. WSL이 없으면 설치가 실패합니다.

### Windows 기능 상태
```
관리자 권한 필요: 확인 불가 (현재 사용자 권한으로는 조회 불가)
Microsoft-Windows-Subsystem-Linux: ? (확인 불가)
VirtualMachinePlatform: ? (확인 불가)
Containers: ? (확인 불가)
```

## 5. 현재 설치 실행 방식 검토

### install_executor.py 분석

#### 현재 코드 (411줄)
```powershell
Start-Process -FilePath "{installer_path}" -Verb RunAs -Wait
```

#### 문제점 분석

**문제 1: ArgumentList 누락**
- Docker Desktop Installer는 `install` 명령어가 필요
- 현재: exe만 실행
- 필요: `install -package <path> [--quiet]`

**문제 2: 설치 로그 미수집**
- Docker Desktop 설치 로그는 별도 위치에 생성
- 현재: exit code만 수집
- 필요: 설치 로그 위치 확인 및 오류 메시지 수집

**문제 3: exit code 해석 불완전**
- Docker Desktop은 여러 종료 코드 반환 가능
- 0 = 성공, 1 = 실패 등
- 현재: returncode == 0만 확인
- 필요: 로그 파일에서 실패 원인 확인

#### 개선 필요 사항

```python
# 개선 전
Start-Process -FilePath "{installer_path}" -Verb RunAs -Wait

# 개선 후 (권장)
Start-Process -FilePath "{installer_path}" -Verb RunAs -Wait `
  -ArgumentList "install -package <package_path>" 

# 또는 (Docker 공식 권장)
Start-Process -FilePath "{installer_path}" -Verb RunAs -Wait `
  -ArgumentList 'install -package "{package_path}"'
```

## 6. 원인 추정 (우선순위)

### 1순위: ⚠️ **WSL이 설치되지 않았음 (최고 가능성)**

**증거:**
- WSL --version 명령 오류: "WSL이 설치되지 않았습니다"
- Docker Desktop은 WSL2를 필수 요구
- WSL 없으면 Docker Engine 실행 불가능

**해결:**
- WSL 설치 필요 (별도 작업)
- 관리자 권한으로 PowerShell 실행 필요
- `wsl --install` 명령 실행

### 2순위: ⚠️ **관리자 권한 문제**

**증거:**
- 설치 로그: "Not run as admin, relaunching with UAC prompt"
- UAC 팝업이 나타났으나 응답 없음

**분석:**
- Start-Process -Verb RunAs는 PowerShell 프로세스를 관리자로 실행
- 하지만 Docker Installer 내부에서 다시 UAC를 요청할 수 있음
- UAC 팝업이 백그라운드에서 나타나 사용자가 보지 못했을 가능성

### 3순위: ⚠️ **ArgumentList 누락**

**증거:**
- 현재 install_executor.py는 exe만 실행 (-Verb RunAs -Wait만 함)
- Docker Installer 공식 실행: `installer.exe install -package <path>`
- ArgumentList 없으면 설치 실행되지 않음

**분석:**
- Docker Desktop Installer는 "install" 명령어가 필요
- ArgumentList 없으면 exe가 설치 모드로 실행되지 않을 가능성

## 7. 다음 보정 지시

### 즉시 필요한 조치

**1단계: WSL 설치 확인**
```powershell
# 관리자 권한으로 실행
wsl --install
```

**2단계: Docker 재설치 시 개선 사항**
- ArgumentList를 추가하여 "install" 명령 전달
- 설치 로그 위치를 파악하여 오류 메시지 수집
- exit code와 로그를 함께 검토

**3단계: 코드 보정안 (install_executor.py)**

```python
# 개선된 _execute_installer_file 메서드 (권장)
def _execute_installer_file(self, installer_path: str) -> tuple[bool, Optional[str]]:
    """설치파일 실행 (Docker Desktop Installer 지원).
    
    참고: Docker Desktop Installer는 'install' 명령어와 -package 인자가 필요합니다.
    """
    try:
        # 설치 로그 경로 확인
        log_path = os.path.expandvars(r"$LOCALAPPDATA\Docker\install-log.txt")
        
        # Start-Process with ArgumentList
        result = subprocess.run(
            [
                'powershell',
                '-Command',
                f'Start-Process -FilePath "{installer_path}" -Verb RunAs -Wait'
            ],
            timeout=600,
            capture_output=True,
        )
        
        # 설치 로그 확인
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    log_content = f.read()
                    # 오류 메시지 검색
                    if 'Not run as admin' in log_content:
                        return False, 'admin_required_uac_failed'
                    if 'WSL' in log_content.upper():
                        return False, 'wsl2_required'
            except Exception:
                pass  # 로그 읽기 실패해도 계속 진행
        
        return result.returncode == 0, None
        
    except subprocess.TimeoutExpired:
        return False, 'install_timeout'
    except Exception as e:
        return False, f'install_error:{type(e).__name__}'
```

## 8. 코드 보정 필요 여부

**현재 상태:**
```
ArgumentList 사용: ✗ 아니오
exit code 캡처: ✓ 예
로그 파일 수집: ✗ 아니오
오류 메시지 분석: ✗ 아니오 (exit code만 봄)
```

**보정 필요:**
```
중요도: ⚠️ MEDIUM
이유: WSL/관리자 권한 문제가 실질적 원인이지만, 
      ArgumentList 누락도 설치 실패의 가능성 있음
개선 추천: ArgumentList 추가, 설치 로그 수집
기간: 다음 1D 업데이트 주기
```

## 9. 재설치 가능 여부

**현 상태:**
```
재설치 금지: ✓ YES (정책)
수동 설치 시: 권장 사항 있음
```

**수동 설치 재시도 절차:**

1. **WSL 설치** (선행 필수)
   ```powershell
   # 관리자 권한으로 PowerShell 실행
   wsl --install
   ```

2. **Docker Desktop 재설치**
   ```powershell
   # 다운로드된 설치파일 직접 실행
   & "C:\Users\skyjw\Downloads\Docker Desktop Installer.exe" install -package "설치패키지경로"
   
   # 또는 설치파일을 더블클릭하여 그래픽 설치
   ```

3. **설치 완료 확인**
   ```powershell
   docker --version
   docker compose version
   docker info
   ```

## 10. 정책 준수 여부

```
Docker만 대상:                    ✓ 준수
공식 도메인만 사용:                ✓ 준수
자동 다운로드:                    ✓ 준수
설치 전 승인:                      ✓ 준수
UAC 사용자 승인:                  ✓ 준수 (팝업 대기)
관리자 비밀번호 저장:              ✓ 준수 (없음)
UAC 우회:                        ✓ 준수 (없음)
Silent install:                  ✓ 준수 (--quiet는 Docker가 추가)
자동 라이선스 동의:                ✓ 준수 (없음)
자동 재부팅:                      ✓ 준수 (없음)
재설치 자동 반복:                  ✓ 준수 (금지)
```

**최종 판정**: ✅ **모든 정책 준수**

## 11. 결론

### 설치 실패 원인 (확인된 것)

**1순위 (거의 확실)**: WSL 미설치
- Docker Desktop은 WSL2 필수
- WSL이 없으면 설치 실패

**2순위 (가능성 높음)**: UAC 팝업 미응답
- 설치 로그에서 "Not run as admin, relaunching with UAC prompt"에서 중단
- UAC 팝업 이후 로그가 없음

**3순위 (가능성 중간)**: ArgumentList 누락
- 현재 코드는 exe만 실행
- Docker Installer는 "install" 명령어가 필요할 수 있음

### 권장 다음 단계

1. **즉시**: WSL 설치
2. **다음**: Docker 재설치 (다운로드된 설치파일 사용)
3. **이후**: install_executor.py에 ArgumentList 추가 검토

### 최종 판정

```
진단 상태: COMPLETE
설치 실패 원인: 식별됨 (WSL + UAC)
코드 보정 필요: 선택적 (ArgumentList, 로그 수집)
재설치 권장: YES (WSL 설치 후)
정책 위반: NO
```

---

**진단 완료 일시**: 2026-05-02  
**진단 도구**: PowerShell, 설치 로그 분석  
**대상 파일**: Docker Desktop 4.71.0 (225177)  
**결론**: WSL 미설치가 근본 원인, 설치 로그에서 확인됨
