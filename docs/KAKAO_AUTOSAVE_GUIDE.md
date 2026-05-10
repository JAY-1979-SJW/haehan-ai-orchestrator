# 카카오 자동 파일 수집 — 사용자 가이드

> 작성일: 2026-05-10
> 목적: 카카오톡/카카오워크에서 받은 사진·파일을 AI가 자동 수집·분류하기 위한 1회성 설정.

---

## 1. 카카오톡 PC — 받은 파일 자동 저장 활성화

> **카카오톡 PC는 기본적으로 받은 파일/사진의 원본을 저장하지 않습니다.** 환경설정에서 자동 저장을 켜면 지정 폴더로 즉시 떨어집니다.

### 설정 방법

1. **카카오톡 PC 실행** → 좌측 하단 **⋯ (더보기)** 클릭 → **환경설정** (또는 `Ctrl + ,`)
2. **저장** 또는 **파일** 탭 진입
3. **"받은 파일 자동 다운로드"** 체크박스 활성화
4. **저장 경로** 다음으로 지정:
   ```
   C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator\data\kakao_inbox\kakaotalk
   ```
5. **확인** → 환경설정 닫기

### 사진은 어떻게?

카카오톡 PC는 **사진 자동 저장 옵션이 별도로 없을 수 있습니다.** 이 경우:
- 받은 사진을 우클릭 → **이미지 저장** → 저장 경로를 위와 같이 지정 (한 번 설정하면 다음부터 동일 경로로 저장)
- 또는 사진 위에 마우스 hover → 다운로드 아이콘 클릭

저장된 파일은 즉시 AI가 감지하여 분류·요약합니다.

---

## 2. 카카오워크 — 받은 파일 자동 저장

1. 카카오워크 → **설정 (톱니바퀴)** → **다운로드 설정**
2. **"파일 자동 다운로드"** 활성화
3. 경로:
   ```
   C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator\data\kakao_inbox\kakaowork
   ```

---

## 3. AI 자동 처리 흐름

```
사용자가 카카오 메신저 사용
     ↓
파일/사진 수신 → 자동저장 또는 수동 저장
     ↓
data/kakao_inbox/ 에 파일 도착
     ↓
kakao_daemon (백그라운드)
     ↓
DownloadWatcher 즉시 감지
     ↓
파일 분류 (카카오톡 vs 카카오워크 / 사진/문서/영상 / 발견 시간)
     ↓
서버 API POST → /kakao/event (file_downloaded)
     ↓
서버: 카테고리별 자동 분류 + 검색 인덱스 + 알림
```

---

## 4. 폴더 구조 (자동 생성)

```
data/kakao_inbox/
├── kakaotalk/           ← 카카오톡 자동 저장 경로
│   ├── images/          ← 자동 분류
│   ├── documents/
│   └── videos/
├── kakaowork/           ← 카카오워크 자동 저장 경로
│   ├── images/
│   ├── documents/
│   └── videos/
└── _processed/          ← 분류 완료 파일 (월/일별 정리)
    └── 2026-05/
        └── 10/
```

---

## 5. 검증 방법

```powershell
# 데몬 실행 확인
Get-ScheduledTask -TaskName "KakaoDaemon"

# 최근 수집된 파일 (서버에서)
curl https://haehan-ai.kr/orchestrator/api/v1/kakao/downloads
```
