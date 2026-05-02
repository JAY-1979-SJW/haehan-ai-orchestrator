# LOCAL-SOFTWARE-WINDOWS-PREREQ-RUN-1: WSL2 선행조건 실제 활성화 실행

**작성일**: 2026-05-02
**대상**: WSL2 (Windows Subsystem for Linux 2) / VirtualMachinePlatform 활성화

---

## 1. 실행 전 환경

### Windows 정보
- **OS**: Windows 10 Home
- **빌드**: 26200 (Windows 11 포함 Windows 10 Pro 수준)
- **아키텍처**: 64-bit
- **RAM**: 32GB

### WSL 활성화 전 상태
- **wsl --version**: 명령 실패 (WSL 미설치)
- **wsl --status**: 명령 실패 (WSL 미설치)
- **Microsoft-Windows-Subsystem-Linux 기능**: 미활성화 (예상)
- **VirtualMachinePlatform 기능**: 미활성화 (예상)

---

## 2. dry_run 계획 단계

### 실행 요청
```json
{
  "action": "local_software.enable_windows_prereq",
  "target_prereq": "wsl2",
  "approval_token": "user-approved-wsl2-prereq",
  "user_confirmed_windows_feature_change": true,
  "dry_run": true
}
```

### 계획된 단계
1. 관리자 권한 확인 (UAC 팝업)
2. PowerShell에서 WSL 설치 명령 실행: `wsl --install`
3. 시스템 재부팅 (필요 시)
4. WSL 버전 확인: `wsl --version`

### 검증 명령
- `wsl --version`
- `wsl --status`
- `wsl -l -v`
- `Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux`
- `Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform`

### dry_run 결과
- **ok**: true ✓
- **status**: pending
- **메시지**: "WSL 활성화 계획이 준비되었습니다."
- **자동 재부팅 여부**: 없음 ✓
- **Docker 설치 여부**: 없음 ✓

---

## 3. 실제 활성화 실행

### 실행 요청
```json
{
  "action": "local_software.enable_windows_prereq",
  "target_prereq": "wsl2",
  "approval_token": "user-approved-wsl2-prereq",
  "user_confirmed_windows_feature_change": true,
  "dry_run": false
}
```

### 실행 과정
- **UAC 팝업**: 나타남 ✓
- **사용자 승인**: "예" 클릭 ✓
- **실행 명령**: `Start-Process powershell -Verb RunAs -Wait -ArgumentList "-Command", "wsl --install --no-launch"`
- **실행 시간**: 116.52초
- **자동 재부팅**: 없음 ✓

### 실행 결과
```json
{
  "ok": true,
  "dry_run": false,
  "status": "requires_reboot",
  "message": "WSL 설치가 실행되었습니다. 시스템 재부팅이 필요합니다.",
  "reboot_required": true,
  "error": null,
  "elapsed_seconds": 116.52
}
```

---

## 4. 실행 후 검증 (재부팅 전)

### WSL 상태
- **wsl --version**: 응답 있음 (재부팅 필요로 인해 완전한 정보 미표시)
- **wsl --status**: 응답 있음 (재부팅 필요 상태)
- **wsl -l -v**: 응답 있음 (설치된 배포판 없음)

### 현재 상태
재부팅 전이므로 WSL 명령이 완전히 작동하지 않음 (정상).
Windows 기능 활성화는 완료되었음.

---

## 5. 최종 판정

### 상태
- **판정**: **WARN** (활성화는 성공, 재부팅 필요)
- **reboot_required**: true
- **다음 조치**: 시스템 재부팅 필요

### 안전성 검증
- ✓ Docker 설치 실행 없음
- ✓ Docker 재다운로드 없음
- ✓ Restart-Computer 명령 없음
- ✓ shutdown /r 명령 없음
- ✓ 관리자 비밀번호/PIN 저장 없음
- ✓ Credential 저장 없음
- ✓ UAC 우회 없음

### 재부팅 후 예상
재부팅 후:
- `wsl --version` 정상 작동
- `wsl --status` 정상 작동
- Microsoft-Windows-Subsystem-Linux 기능 Enabled
- VirtualMachinePlatform 기능 Enabled
- Docker Desktop 설치 준비 완료

---

## 6. 상태 변수

```yaml
reboot_required: true
wsl_activated: true
docker_installer_executed: false
credential_stored: false
auto_reboot_executed: false
uac_approval_required: true
uac_approved: true
```

---

## 7. 다음 단계

1. **시스템 재부팅** (필수)
   - 사용자가 직접 재부팅 실행
   - 또는 `Restart-Computer -Force` (관리자 권한)

2. **재부팅 후 WSL 상태 확인**
   - `wsl --version`
   - `wsl --status`
   - `wsl -l -v`

3. **Docker Desktop 설치** (별도 단계)
   - WSL2 기능 활성화 후에 진행
   - 자동 재부팅 금지 조건 유지

---

## 첨부

- 실행 시점: 2026-05-02 (작업 실행 시간대)
- 관련 코드: `agent/local_software_manager/windows_feature_executor.py`
- 테스트: `agent/tests/test_local_software_windows_prereq.py`
