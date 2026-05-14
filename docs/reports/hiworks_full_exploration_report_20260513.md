# 하이웍스 전체 탐색 보고

작성일: 2026-05-13  
site_id: `hiworks`  
범위: 회사 하이웍스 오피스 read-only 탐색

## 결론

하이웍스 로그인 세션 저장과 주요 업무 앱 탐색을 완료했다. 대시보드, 앱 카탈로그, 메일함, 메일 작성 화면 구조, 17개 업무 서비스 표면, 섹션별 입력/버튼 action catalog까지 확인했으며 실제 발송, 결재 상신, 휴가 신청, 게시글 작성 같은 상태 변경 동작은 실행하지 않았다.

## 세션 및 감시

- 실시간 로그인 감시 명령: `python scripts\cdp_client.py login-watch 1 3`
- 저장 세션: `office.hiworks.com`
- DB 세션 상태: `hiworks` 로그인 저장됨
- 감사 이벤트: `LOGIN_SESSION_SAVED`

## 서비스 표면 스캔 결과

명령:

```powershell
python scripts\cdp_client.py hiworks service all --limit=60
```

| key | 제목 | links | buttons | inputs | tables |
| --- | --- | ---: | ---: | ---: | ---: |
| `mail` | 하이웍스 메일 | 45 | 184 | 27 | 0 |
| `approval` | 하이웍스 전자결재 | 51 | 20 | 4 | 1 |
| `scheduler` | 하이웍스 일정 | 19 | 39 | 5 | 6 |
| `boards` | 하이웍스 게시판 | 67 | 69 | 2 | 0 |
| `address-book` | 하이웍스 주소록 | 15 | 21 | 2 | 2 |
| `booking` | 하이웍스 예약 | 20 | 19 | 2 | 2 |
| `hr-work` | 하이웍스 근무/경비처리 | 22 | 38 | 0 | 2 |
| `team-mail` | 하이웍스 공용메일 | 13 | 24 | 0 | 0 |
| `files` | 하이웍스 드라이브 | 19 | 27 | 4 | 0 |
| `tasks` | 하이웍스 업무관리 | 12 | 22 | 1 | 0 |
| `admins` | 하이웍스 관리 | 21 | 23 | 0 | 0 |
| `bills` | 세금계산서 | 48 | 27 | 1 | 0 |
| `sms` | 하이웍스 메시징 | 29 | 23 | 13 | 1 |
| `notes` | 하이웍스 쪽지 | 9 | 19 | 1 | 0 |
| `groups` | 하이웍스 오피스 - 그룹 | 10 | 12 | 0 | 0 |
| `ai-chat` | 하이웍스 AI채팅 | 10 | 29 | 2 | 0 |
| `plus` | 하이웍스 플러스앱 | 9 | 13 | 0 | 0 |

## 저장 산출물

| 파일 | 내용 |
| --- | --- |
| `data/hiworks_apps_latest.json` | 대시보드/앱/업무 링크 카탈로그 |
| `data/hiworks_compose_page_latest.json` | 메일 작성 화면 입력 요소/버튼 구조 |
| `data/hiworks_service_surfaces_latest.json` | 17개 업무 서비스 read-only 표면 구조 |
| `data/hiworks_action_catalog_latest.json` | 17개 업무 서비스 입력/버튼 안전 분류 |
| `data/hiworks_section_prepare_plan_latest.json` | 모든 섹션 입력 prepare 및 버튼 게이트 계획 |
| `data/hiworks_submit_section_latest.json` | 승인 실행 또는 승인 dry-run 증적 |
| `data/hiworks_runs/*/*.json` | 하이웍스 workflow 실행 로그 |
| `data/sessions/office.hiworks.com.json` | 암호화된 하이웍스 세션 |

## 안전 경계

- 메일 본문 열람 자동화는 수행하지 않았다.
- 메일 발송 버튼은 클릭하지 않았다.
- 결재/휴가/근무 신청/게시글 작성 같은 submit 동작은 승인과 확인문구 없이는 수행하지 않는다.
- 승인 실행 경로는 구현되어 있으며, 배포/운영 전에는 `--dry-run`으로 버튼 매칭과 증적 저장을 먼저 확인한다.
- 보고서에는 메일 본문, 인증 코드, 토큰, 쿠키 값을 기록하지 않는다.

## 다음 분해 작업

1. 전자결재 read-only 목록/대기문서 구조 수집
2. 일정 read-only 일정표 구조 수집
3. 게시판 read-only 목록 구조 수집
4. 주소록 read-only 검색/목록 구조 수집
5. 예약 read-only 리소스/가용 현황 구조 수집
6. 근무/경비처리 read-only 현황 구조 수집
7. 드라이브/업무관리/관리 영역별 권한과 제출 동작 분리

각 영역은 `discover -> plan -> prepare -> submit -> verify -> log` 기준으로 분리하고, submit 계열은 승인 게이트 없이는 구현하지 않는다.
