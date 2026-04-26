# FFmpeg Availability (F-4S-13b)

## 목적

restricted render worker(F-4S-13)가 실제 렌더링을 수행하려면 ffmpeg가 PATH에 설치되어 있어야 한다.
이 문서는 설치 상태 확인 절차와 Windows 설치 가이드를 제공한다.
**ffmpeg 자동 설치 / 실제 렌더 실행은 이 단계에서 수행하지 않는다.**

## 왜 ffmpeg 설치를 자동화하지 않는가

- 시스템 전역 바이너리를 자동 설치하는 것은 승인 없는 외부 패키지 수령에 해당한다.
- 설치 대상 경로(`C:\Program Files\ffmpeg`, PATH 수정 등)는 사람이 검토해야 한다.
- 자동화 스크립트가 잘못된 바이너리를 받아 실행하는 supply chain 위험을 방지한다.

## Windows 설치 권장 방법

### 방법 1 — winget (권장)

```
winget install Gyan.FFmpeg
```

설치 후 새 터미널을 열고 PATH 반영 여부 확인:

```
ffmpeg -version
ffprobe -version
```

### 방법 2 — 공식 빌드 수동 설치

1. `https://ffmpeg.org/download.html` → Windows → gyan.dev 또는 BtbN 빌드 다운로드
2. 압축 해제 후 `bin\` 폴더를 시스템 PATH에 추가
3. 새 터미널에서 `ffmpeg -version` 확인

## PATH 반영 확인

새 터미널에서:

```
where ffmpeg
ffmpeg -version
```

또는 check script 실행:

```
python scripts/check_ffmpeg_availability.py --json
```

`ffmpeg_found: true`, `recommendation: ready_for_render_smoke` 이면 다음 단계 진행 가능.

## check script 사용법

```
python scripts/check_ffmpeg_availability.py [--out-dir runs/video/render] [--json]
```

결과 파일:
- `runs/video/render/ffmpeg_availability_YYYYMMDD_HHMMSS.json`
- `runs/video/render/ffmpeg_availability_YYYYMMDD_HHMMSS.md`

## ffmpeg 준비 후 다음 단계

`recommendation: ready_for_render_smoke` 확인 후 F-4S-13c에서:

```
python scripts/run_render_worker.py \
  --render-plan runs/video/render/render_plan_YYYYMMDD_HHMMSS.json \
  --execute
```

## 보안 원칙

| 항목 | 내용 |
|---|---|
| shell=True | 금지 |
| os.system | 금지 |
| 외부 URL 입력 | 금지 |
| 입력 경로 | runs/video, samples 하위만 |
| 출력 경로 | runs/video/render/output 하위만 |
| 출력 확장자 | .mp4만 |
| 업로드/OAuth | 금지 |
