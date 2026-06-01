# 정부 지원사업 레이더 — Phase 1 설계서

## 목적
정부 포털(현재 NIPA)의 지원사업 공고를 **별도 헤드리스 브라우저**로 스캔하고,
사업 프로필(소방·CAD 물량산출·AI·소상공인) 기준 적합도를 산정해 보고서로 제공한다.
메인 Chrome(9222) 및 사용자 전면 작업과 무간섭.

## 범위 (Phase 1 = read-only)
탐색 → 적합도 분석 → 보고서 표시. **승인·신청서 작성·폼 자동입력은 Phase 2/3** (미포함).

## 레이어/파일
| 파일 | 레이어 | 역할 |
|------|--------|------|
| `scripts/grant_radar/scan.py` | L10/L5 | 헤드리스 Chromium 6개 포털 스캔(anchor: NIPA·기업마당·중기부 / rows: CCEI·중소벤처24·SBA) → `data/grant_radar/scan_latest.json` |
| `scripts/grant_radar/report.py` | L6 | 적합도 점수(키워드+가중치) + 마감/담당자 파싱 + LLM 요약(상위 8건) → `report_latest.json`/`.md` |
| `configs/grant_radar_profile.json` | L1 | 업종 키워드·가중치 (민감정보 미포함) |
| `ai_orchestrator/connectors/grant_radar_router.py` | L8 | `GET /api/v1/grant-radar/report`, `POST /api/v1/grant-radar/scan` |
| `admin-web/src/app/grant-radar/page.tsx` | L9 | 보고서 표·스캔 버튼 (`/api/proxy` 경유) |

## 데이터 흐름
```
[스캔] POST /grant-radar/scan → scan.py(헤드리스) → scan_latest.json
                              → report.py(적합도+LLM) → report_latest.json
[조회] GET /grant-radar/report → report_latest.json → 표 렌더
```

## 적합도 산정
`configs/grant_radar_profile.json`의 `keyword_weights`로 공고 원문 텍스트 매칭 합산.
마감(D-day/신청기간 종료일)·담당자는 원문 정규식 추출(생성·추정 금지, 원문 출처 링크 동반).

## 보안/안전
- secret/token 미출력. 프로필에 사업자번호 등 민감정보 미포함.
- 외부 발행/제출/결제/서명 없음. mutation은 로컬 JSON 생성뿐.
- 스캔은 로그인 불필요한 공개 페이지만 대상.

## Phase 2 (구현 완료) — 회사 프로필 + 승인 + 신청서 초안
- `configs/grant_radar_company.json` — 회사 프로필(사업자번호 등 민감정보는 placeholder, repo 미포함).
- `openai_client.generate_application_draft(grant, company)` — 공고+프로필 기반 LLM 초안(MOCK 폴백). 응답에서 business_no 마스킹.
- `grant_radar_router`: `POST /grant-radar/draft`(confirm=true 승인 시에만 생성·저장·`log_event("GRANT_DRAFT_CREATED")`), `GET /grant-radar/drafts`.
- UI: 행별 "초안 작성" 버튼 → 승인 확인 → 편집 가능 초안 패널. 초안 저장 `data/grant_radar/drafts/`.
- **안전**: 초안=로컬 파일, 외부 제출 없음. confirm 없으면 미생성(미리보기만).

## Phase 3 (구현 완료) — CDP 신청폼 자동입력
- `scripts/grant_radar/form_fill.py` — stdin JSON, CDP(9222) 대상 탭 입력칸 탐지→가장 큰 textarea에 초안 입력. **submit 절대 미클릭**. confirm=False=계획만.
- `grant_radar_router`: `POST /grant-radar/fill`(confirm 게이트→subprocess→`log_event("GRANT_FORM_FILLED")`). 로컬 전용.
- UI: 초안 패널 "신청폼에 채우기" 버튼 → 사이트주소 입력 → 필드 감지 확인 → 입력. **제출은 사용자 직접**.

## 번들(설치본) 실행 수정 — 데이터 경로 + 동결 exe 디스패치
PyInstaller 동결 exe에선 `-m` 미지원 + 데이터 경로가 MEIPASS(휘발성)로 어긋나는 문제 수정:
- **데이터 경로**: `HAEHAN_DATA_DIR` env 우선(없으면 dev 소스 `data/grant_radar`). scan·report·router 공유.
- **동결 디스패치**: `run_server.py --grant-task {scan|report|fill}` → 해당 모듈 main 실행. router는 `getattr(sys,'frozen')`로 `--grant-task`/`-m` 분기(`_grant_cmd`).
- **번들**: `haehan-server.spec` datas에 `scripts/grant_radar` 추가.
- **Electron**: `fastapi_server.js`가 spawn env에 `HAEHAN_DATA_DIR=userData/data` 주입. (없을 때 run_server는 `%APPDATA%/Haehan AI/data` 기본값)
- 검증: dev=소스경로, env지정=해당경로 OK.

## 다음 단계(선택)
- 포털 확장: K-Startup(AJAX go_view)·소상공인24 등.
- 라벨 정밀 매핑(현재 v1은 최대 textarea 단일 입력).
