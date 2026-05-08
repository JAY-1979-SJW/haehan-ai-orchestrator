# Security Program User Assisted Install Mode 설계

작성일: 2026-05-08

## 핵심 원칙

AI는 자동 실행하지 않는다. 공식 설치파일 검색·다운로드·검증·탐색기 표시까지 자동화하고, **사용자가 직접 더블클릭/UAC 승인/설치를 수행**한다. 설치 완료 후 AI가 자동으로 감지하고 원래 작업을 재개한다.

## 모듈 구조

```
ai_orchestrator/local_agent/
  user_assisted_installer.py                          ← WAITING_USER_INSTALL_CLICK 상태 생성
  installer_folder_presenter.py                       ← explorer.exe /select 표시
  security_program_install_completion_detector.py     ← 설치 전후 페이지 비교
  security_program_user_install_result_sanitizer.py   ← 결과 민감 정보 제거
```

## 상태 흐름

```
SECURITY_PROGRAM_REQUIRED
  → INSTALLER_CANDIDATE_FOUND
  → INSTALLER_DOWNLOADED
  → INSTALLER_VERIFIED         (hash + signature)
  → WAITING_USER_INSTALL_CLICK ← AI는 여기서 대기
  → WAITING_USER_UAC           ← 사용자 직접 승인
  → USER_INSTALL_IN_PROGRESS
  → INSTALL_COMPLETED_DETECTED (또는 INSTALL_NOT_DETECTED)
  → RETRY_ORIGINAL_TASK_READY
  → ORIGINAL_TASK_RESUMED
```

## 핵심 정책

| 항목 | 값 |
|------|------|
| `auto_execute` | 항상 False |
| 탐색기 표시 | `explorer.exe /select,<path>` (runas 없음) |
| silent install | 사용 안 함 |
| UAC 자동 승인 | 사용 안 함 |
| 완료 감지 | headed 브라우저 재접속 필수 |
| local full path | 결과에서 제외 |

## 사용자 안내 메시지

```
공식 설치파일을 다운로드하고 검증했습니다.
탐색기에서 선택된 설치파일을 더블클릭해 설치를 진행해 주세요.
UAC/관리자 권한 창이 뜨면 사용자가 직접 승인해야 합니다.
설치가 끝나면 이 화면에서 '설치 완료 확인'을 눌러 주세요.
이후 앱이 자동으로 사이트에 재접속합니다.
```

## 완료 감지 결과

| 상태 | 의미 |
|------|------|
| INSTALL_COMPLETED_DETECTED | 모든 신호 해소 — 재시도 가능 |
| PARTIAL_RESOLVED | 일부 해소 — 추가 설치 필요 |
| INSTALL_NOT_DETECTED | 미해소 — 사용자 확인 필요 |
| HEADLESS_REQUIRES_HEADED | headless 환경에서 감지 불가 |

## 테스트 (3파일, 31 테스트)

| 파일 | 수 |
|------|----|
| test_user_assisted_installer | 12 |
| test_installer_folder_presenter | 10 |
| test_security_program_install_completion_detector | 10 |

전체: 31 PASS (1 skip — non-Windows 전용)
