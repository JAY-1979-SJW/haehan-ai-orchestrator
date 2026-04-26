# Automation Authority Policy

## 기본 방향

Claude Code는 가능한 작업을 직접 실행한다. 대표님에게 터미널 명령 실행, 파일 확인, 결과 붙여넣기를 요구하지 않는다. 단, push, 운영 서버 변경, DB 변경, 송금/결제, 외부 게시/댓글/업로드, 삭제 등은 별도 승인형으로 남긴다.

## 1. 목적

Claude Code가 가능한 작업을 자율 실행하는 운영 원칙 정의.

## 2. 자동 실행 원칙

- 터미널 명령은 Claude Code가 직접 실행
- 결과 파일은 Claude Code가 직접 확인
- WARN/FAIL 원인 분리는 Claude Code가 직접 수행
- 대표님에게 파일 경로/명령어 복사 실행을 요구하지 않음
- 로그인/인증이 필요한 작업은 "대표님 대기"가 아니라 "인증 주체 필요(NEEDS_AUTH_PRINCIPAL)"로 분류
- 개발자 콘솔 작업은 전용 브라우저 프로필 기반 세션 재사용 구조로 실행한다. 로그인되어 있으면 즉시 업무를 수행하고, 세션 만료 시에는 NEEDS_REAUTH로 기록하여 재개 가능한 task 파일을 남긴다.

## 3. 자동 허용 범위

| 구분 | 항목 |
|------|------|
| 개발 | 로컬 명령 실행, 테스트 실행, smoke 테스트 |
| 파일 | 코드/문서 수정, 결과 파일 직접 확인 |
| Git | git add, git commit |
| 패키지 | allowlist 패키지 설치 (winget/pip/npm allowlist 기준) |
| Secret | safe env setter로 secret 등록 |
| 내부망 | localhost/internal URL 녹화, 내부 API 호출 |
| 콘솔 업무 | 개발자 콘솔 접속/설정/신청서 작성/제출/상태 확인 |
| 콘솔 업무 | API 활성화, Redirect URI 등록, 플랫폼 도메인 등록 |
| 콘솔 업무 | 권한 신청서 작성, 심사 자료 작성/업로드 |
| 콘솔 업무 | 반려 사유 확인, 보완 자료 작성, 재신청 |

## 4. 승인 필요 범위 (APPROVAL_REQUIRED)

- git push (원격 반영)
- 운영 서버 재시작/배포
- DB DDL/update/delete
- 외부 사용자 대상 게시/댓글/업로드
- 송금/결제 최종 실행
- 광고비 집행
- 앱 삭제, Client Secret 재발급/폐기
- 운영 데이터 삭제

## 인증 자동화 정책

- 본인 소유 계정에 한해 Playwright storageState, .env 기반 자격증명, 쿠키/세션 재사용을 통한 로그인 자동화를 허용한다.
- 타인 계정 자동화, credential 하드코딩, 공개 저장소에 .env·storageState 커밋은 금지한다.
- .gitignore에 .env, storageState.json, auth.json이 포함되어 있는지 확인한다.
- CAPTCHA, 2FA, 봇 탐지 등 보안 메커니즘 우회는 계속 금지한다.
- 자동화 대상 사이트의 이용약관(ToS)을 확인하고, 약관 위반 시 사용자에게 고지한다.

## 5. 금지 범위 (BLOCKED)

- Chrome/Google Password Manager 저장 비밀번호 추출
- 사이트별 ID/PW 목록 수집
- Windows Credential Manager 비밀번호 추출
- 비밀번호/OTP/인증서 비밀번호/TOTP seed 저장
- captcha/보안 우회
- 타인 계정 접근
- 무승인 송금/결제/삭제/광고비 집행
- 외부 사용자 대상 댓글/DM/게시/가입/업로드 무승인 실행
- API key/client secret 원문 출력
- `.env` cat/git add
- git push 무승인 실행
- 운영 서버 재시작 무승인 실행
- DB DDL/update/delete 무승인 실행

## 6. 작업 상태 분류

| 상태 | 설명 |
|------|------|
| `READY_AUTOMATED` | 키/토큰/서비스계정/권한이 준비되어 Claude Code가 즉시 자동 실행 가능 |
| `READY_LOGGED_IN` | 전용 프로필 세션 유효 — Claude Code가 즉시 콘솔 업무 수행 |
| `SESSION_REUSED` | 기존 세션 재사용 성공 |
| `SESSION_EXPIRED` | 세션 만료 감지, 재인증 필요 |
| `NEEDS_REAUTH` | 재인증 후 자동 재개 가능한 pending task 파일 생성됨 |
| `READY_AFTER_REAUTH` | 재인증 완료, 작업 자동 재개 |
| `NEEDS_AUTH_PRINCIPAL` | 지정 인증 주체 필요 (developer_console_operator, finance_approver 등) |
| `NEEDS_CONTRACT_OR_ADMIN_SETUP` | 법인 API, 펌뱅킹, Workspace domain-wide delegation, 비즈니스 권한 등 |
| `BLOCKED_BY_PERMISSION` | 권한 부족으로 진행 불가 |
| `APPROVAL_REQUIRED` | 송금, 결제, 삭제, 광고 집행, 외부 게시, 운영 DB/서버 변경 등 |
| `BLOCKED` | 공식 권한/위임 없이 진행 불가, 우회 시도 금지 |

## 7. 보고 형식

```
[작업 내용]
[자동 실행한 작업]
[변경 사항]
[보안 확인]
[커밋]
[다음 승인 필요 작업]
[최종 판정]
```
