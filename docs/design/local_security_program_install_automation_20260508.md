# Local Security Program Install Automation 설계 문서

작성일: 2026-05-08

## 개요

은행/카드/보험/정부/세무/조달 등 보안프로그램 설치가 필요한 사이트에서
로컬 에이전트가 설치 필요 신호 감지 → 공식 설치 후보 수집 → 사용자 승인 → 설치 보조 → 원래 작업 재개까지 지원한다.

## 핵심 원칙

- 보안프로그램 설치는 LOCAL_PC_ONLY 작업
- 서버에서 보안프로그램 설치 시도 금지
- 서버에서 은행/정부/카드/보험 사이트 브라우저 실행 금지
- 설치는 사용자 승인 후에만 실행
- UAC/관리자 권한 승인은 사용자 직접
- 보안프로그램 우회/무력화/차단 회피 구현 금지

## 모듈 구조

```
ai_orchestrator/local_agent/
  security_program_detector.py                  ← 신호 감지
  security_installer_candidate_finder.py        ← 설치 후보 수집
  security_installer_policy.py                  ← 안전 정책 검증
  local_security_installer_runner.py            ← 설치 실행 보조
  security_program_permission_gate.py           ← 권한 객체 관리
  security_program_install_result_sanitizer.py  ← 결과 민감 정보 제거
  security_program_auto_resume.py               ← 전체 흐름 오케스트레이션
```

## 실행 등급

| 등급 | 작업 |
|------|------|
| AUTO_ALLOWED | 신호 감지, 설치 안내 탐색, 설치 상태 확인, 재접속, read-only 재개 |
| USER_DELEGATED | 다운로드, 설치 실행, 브라우저 재시작, 재접속, 재시도 |
| USER_DIRECT | UAC 승인, 관리자 권한 승인, 설치 마법사 확인, OTP/로그인/전자서명 |
| BLOCKED | 우회, 무력화, 캡차 우회, 자동 UAC, 비밀번호/OTP/인증서 저장, cookie/session export |

## 감지 신호 (9종)

- SECURITY_PROGRAM_REQUIRED
- KEYBOARD_SECURITY_REQUIRED
- CERT_MODULE_REQUIRED
- E_SIGNATURE_MODULE_REQUIRED
- BROWSER_EXTENSION_REQUIRED
- INSTALL_GUIDE_PAGE_DETECTED
- INSTALL_COMPLETE_RETRY_REQUIRED
- UNSUPPORTED_BROWSER
- ADMIN_PERMISSION_REQUIRED

## 설치 파일 허용/차단 정책

| 허용 | 차단 |
|------|------|
| .exe, .msi, .dmg, .pkg, .zip(추가 승인) | .bat, .cmd, .ps1, .js, .vbs |
| 공식 도메인/하위 도메인 | .pfx, .p12, .key, .pem, .crt, .cer |
| | NPKI 경로, 단축 URL, 외부 도메인 |

## 무인 설치 플래그 기본 금지

`/silent`, `/quiet`, `/qn`, `/verysilent`, `-silent`, `-quiet`, `--silent`, `--quiet`, `/s`, `-s`

## 설치 흐름

```
detect_signals → find_candidates → evaluate_policy
    → has_permission? → N: AWAIT_PERMISSION
    → requires_uac? → Y: AWAIT_UAC (사용자 직접 클릭)
    → dry_run? → Y: INSTALLER_VERIFIED
    → check_install_completed → retry_original_task
```

## 결과 sanitizer — 허용/금지 필드

| 허용 | 금지 |
|------|------|
| task_id, domain, installer_safe_name, source_host | local_path, full_path |
| status, error_category, install_detected | cookie, session, token, storage_state |
| restart_required, retry_ready | password, otp, cert_password |
| | registry 민감값, npki_path, cert_file, raw_log |

## 테스트 파일 (7개, 95 테스트)

| 파일 | 수 |
|------|----|
| test_security_program_detector_20260508.py | 15 |
| test_security_installer_candidate_finder_20260508.py | 17 |
| test_security_installer_policy_20260508.py | 13 |
| test_local_security_installer_runner_20260508.py | 18 |
| test_security_program_permission_gate_20260508.py | 14 |
| test_security_program_install_result_sanitizer_20260508.py | 10 |
| test_security_program_auto_resume_20260508.py | 11 |

**전체: 95/95 PASS + 전체 회귀 4589 passed, 0 failed**
