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
| `scripts/grant_radar/scan.py` | L10/L5 | 헤드리스 Chromium 포털 스캔 → `data/grant_radar/scan_latest.json` |
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

## 다음 단계
- Phase 2: 회사 프로필 저장(L7) + 승인 게이트(approval.py 재사용) + 신청서 초안(LLM).
- Phase 3: CDP 폼 자동입력(form_runner 패턴) — **제출 직전 정지, 최종 제출은 사용자**.
- 포털 확장: 기업마당(bizinfo)·K-Startup·중소벤처24·CCEI 스캐너 추가.
