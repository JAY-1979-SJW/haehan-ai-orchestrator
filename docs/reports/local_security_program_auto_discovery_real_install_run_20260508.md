# Local Security Program Auto Discovery Real Install Run — 실행 보고

작성일: 2026-05-08
작업 ID: LOCAL_SECURITY_PROGRAM_AUTO_DISCOVERY_REAL_INSTALL_RUN_1

## 검색 후보

| 순위 | 사이트 | 도메인 | 접속 결과 | 설치 후보 |
|------|--------|--------|-----------|-----------|
| 1 | 우리은행 | spot.wooribank.com | PAGE_ACCESSED | 0 (JS 동적 로드) |
| 2 | **KB국민은행** | obank.kbstar.com | **PAGE_ACCESSED** | **1 (JS 추출)** |
| 3 | 정부24 | plus.gov.kr | PAGE_ACCESSED | 0 (외부 도메인) |

**선택: KB국민은행**  
선택 사유: 공식 도메인(kbstar.com) + JS 분석으로 `download.kbstar.com` 공식 다운로드 URL 추출 가능 + 공식 하위 도메인 검증 통과

## 대상 사이트

- selected_url: https://obank.kbstar.com/quics?page=C040531
- selected_host: obank.kbstar.com
- site_type: 은행 보안프로그램 설치 안내

## 보안프로그램 감지

- security program: ✅ SECURITY_PROGRAM_REQUIRED
- keyboard security: ✅ KEYBOARD_SECURITY_REQUIRED
- cert module: ✅ CERT_MODULE_REQUIRED
- e-signature module: ✅ E_SIGNATURE_MODULE_REQUIRED
- install guide: ✅ INSTALL_GUIDE_PAGE_DETECTED

## 설치 후보

- installer_url: https://download.kbstar.com/security/wizvera/delfino/g3/delfino-g3.exe
- source_host: download.kbstar.com (kbstar.com 루트 도메인 일치 — 공식 확인)
- safe_name: delfino-g3.exe
- extension: .exe (허용)
- size: 31,093,592 bytes (31MB, 500MB 제한 이내)
- sha256: 000cf27f21f06997ef22f26b3743425d4a095b1143a17ebb77b7e65822c1cb8f
- signature_status: **Valid — WIZVERA Co., Ltd. / DigiCert 발급 / 2026-09-18까지 유효**
- official_source: ✅

## 사용자 승인

- install_permission: 생성 완료 (permission_id: d9f43b34-970f-4bea-ab2c-651ee58e92ec)
- permission_id: d9f43b34-970f-4bea-ab2c-651ee58e92ec
- UAC/admin approval: 사용자 직접 승인 (PowerShell Start-Process 통해 실행, exit code 0)
- user_direct_required: UAC 승인 — 사용자 직접

## 설치 실행

- installer_launched: ✅ (Start-Process, silent 옵션 없음)
- install_status: INSTALL_COMPLETED (exit code 0)
- installed_detected: ✅ C:\Program Files (x86)\Wizvera\Delfino-G3\ 생성 확인
  - delfino.exe, DelfinoUAC.exe, delfino.dll 등 설치 완료
  - 설치 파일 서명 Valid (WIZVERA)
- restart_required: ✅ (브라우저 재시작 권장)
- retry_ready: 브라우저 재시작 후 가능

## 특이사항

**AhnLab headless 오류:**  
headless Playwright로 KB star 페이지 접속 시 페이지의 ASTx JavaScript(AhnLab)가 로컬 서비스(127.0.0.1:55920)에 연결을 시도하며 headless 환경을 감지하고 오류를 보고한 것. 설치 파일(delfino-g3.exe) 자체와 무관. 예상된 동작.

**headless 브라우저 설치 감지 한계:**  
headless Playwright는 로컬 설치 브릿지(로컬호스트 포트 기반)로 설치 여부를 확인하는 KB star 페이지 메커니즘을 사용할 수 없음. 실제 설치 확인은 Program Files 디렉터리로 대체.

## 재접속/작업 재개

- reconnect_result: headless 환경에서 설치 상태 DOM 감지 불가 (예상된 한계)
- security_signal_cleared: headed 브라우저 + 브라우저 재시작 후 확인 필요
- login_required: 실제 인터넷뱅킹 이용 시 공동인증서 필요 (USER_DIRECT_REQUIRED)
- original_task_status: RESTART_BROWSER_REQUIRED → 브라우저 재시작 후 재시도

## 보안 정책

- 우회/무력화: 없음
- silent install: 없음 (Start-Process 일반 실행)
- password/OTP/cert password: 수집/저장 없음
- cookie/session/storage_state: export 없음
- 인증서/NPKI: 접근 없음
- 서버 외부 브라우저 실행: 없음 (server_browser_used=False)
- 자동 결제/송금/투찰/전자서명: 없음
- safe field 위반: 0건

## 테스트 결과

- targeted (7개 파일): 95/95 PASS
- policy grep: PASS
