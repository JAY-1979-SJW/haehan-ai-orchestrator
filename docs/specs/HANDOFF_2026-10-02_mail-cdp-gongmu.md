# 인수인계 — 2026-10-02 세션 (메일·CDP·공무)

> 세션 기록이 커져서(8.8MB) `/clear` 후 새 세션에서 이어간다. 새 세션은 이 문서와 CLAUDE.md 를 먼저 읽는다.
> 커밋 해시는 2026-10-02 이력 정리(민감 값 제거)로 바뀐 것이 있어 **제목·`git log` 로 찾는다**: `git log --oneline origin/feat/login-state-by-element..HEAD` (푸시 전 커밋), `git log --oneline -40`.

## 1. 지금 진행 중: 건설업 공무 G1 구현 (다음에 바로 시작)
- 기준서: `docs/specs/2026-10-02_construction_gongmu.md` — **승인됨(권장안), 나라장터(P7) 제외**. 사용자 말: "나라장터는 제외하고 진행해".
- 시작 지점: **G1 업무판** — ① `gates/gongmu_task_policy.py`(순수, 금액 기준 경계값 시험부터) ② `persistence/gongmu_store.py`(sqlite, `sqlite_schema` 버전 단계) ③ `services/gongmu_service.py`(현장·계약 등록, 업무 자동 생성, 엑셀·CSV 가져오기) ④ `routers/gongmu_router.py` ⑤ 예약 액션 `gongmu_due_notice`(읽기 전용) ⑥ `admin-web/src/app/gongmu/*` ⑦ 테스트·게이트.
- 첫 시험 데이터는 **가상 현장 1곳**(실제 계약 정보는 저장소에 올리지 않음). 사이트 연동(G3)은 사용자가 사이트를 고를 때만.
- 새 세션 시작 문구 예: "공무 G1 진행해 (docs/specs/2026-10-02_construction_gongmu.md, 나라장터 제외)".

## 2. 이번 세션에서 끝낸 것 (모두 로컬 커밋, 푸시는 `feat/login-state-by-element` 에 한 번 완료)
- **메일**: 네이버 메일함 탭, AI 업무 창(초안만·카드 승인 발송), 새 메일 알림(STATUS 폴링), 순차 대량 발송 B1~B4(승인서·한 명씩 차례·자동 멈춤·화면 `/mailbox/bulk`, 실발송 검증 완료), 시간은 한국 시간(KST). 기준서 `2026-10-02_mail_bulk_sequential.md`.
- **CDP**: 칸(lane) 등록표 `scripts/cdp_lanes.py`, 새 탭 안전 열기 `scripts/cdp_tabs.py`(탭 안 실제 페이지 확인), 칸 시작 CLI `scripts/cdp_lane_start.py`, 사이트 정확 열림 검증 `scripts/cdp_verify.py`. 기준서 `2026-10-02_app_agent_dispatch.md` §9. 작업 분배 P1~P3 는 **다른 창**이 구현·커밋함.
- **정리**: `.gitignore` 에 자격증명 백업 규칙 추가, 푸시 전 이력에서 민감 값(팩스번호·잔액·메일 주소) 치환 후 푸시.

## 3. 미결·주의
| 항목 | 상태 |
|---|---|
| 하이웍스 오픈 API 앱 등록 | **가비아 로그인 대기**(사용자 로그인 필요). CDP 크롬에 `developers.hiworks.com` 탭이 열려 있음. 로그인 후 앱 등록 화면(`/apps/register`)·요금·인증 확인 → 폼 입력 → **최종 제출은 사용자 확인 후** → 키는 `.env` 로만. 벤더 목록 `configs/vendor_apis.json` 에 조사 결과 기록됨 |
| 윈도우 캡처 도구 | 시험 중 `화면 녹화` 모드로 저장됐을 수 있음(원래 `캡처`). PrintScreen 키 설정은 켬(`PrintScreenKeyForSnippingEnabled=1`). 영역 선택(드래그 사각형) 화면이 안 그려지는 증상은 **미해결** — 앱 재설정·그래픽 드라이버·모니터 배율 순으로 확인 |
| 알약 탐지 | `Gen:Variant.Adware.MSILHeracles.2158` 은 다른 세션이 마우스 클릭용으로 `Add-Type` 컴파일한 임시 DLL 오탐으로 판단(15:23). 앱 코드 무관. 마우스 조작용 `Add-Type` 사용 금지 안내 필요 |
| 푸시 | 이후 커밋(메일 시간·CDP·공무 기준서 등)은 **미푸시**. 푸시 전 반드시 타창 확인(민감 값 스캔 포함, 저장소가 PUBLIC) |
| 로컬 에이전트 | 등록 1개, 지금 offline. 동시 실행(P1)을 쓰려면 `python -m core.agent_runtime.agent --run` 필요 |
| 메모리 | PC 여유 메모리 부족(0.9~1.6GB). 칸 하나 기동 시 약 0.5GB 사용. 새 칸은 여유 1.5GB 이상일 때만 |
| 스마트스토어센터 CDP | 오래 켜 둔 브라우저 세션이 원인이었음 → 프로필 유지 재시작으로 해결. 한 사이트만 안 열리면 재시작 먼저 |
| 메일 후속 | 사전 승인 자동 발송, AI 분류 정리(이동·삭제·읽음 제안 카드), 대량 발송 B5(실제 목록 투입은 사용자 승인 후) |

## 4. 운영 규칙 재확인
- 타창이 같은 작업 폴더·브랜치를 쓴다 → 커밋은 내 파일만 스테이징, 공유 파일은 추가만, git 이력 재작성·서버 재시작·배포는 한 창만(타창 확인).
- 로그인·OTP·결제·최종 제출은 사용자만. 앱 창(CDP 9333)·사용자 마우스/화면 조작은 허락 후에만.
- 코드 작성 전 기준서 → 드라이런 → 승인, 완료 보고 전 테스트·게이트 증거. 한국어로 보고.
