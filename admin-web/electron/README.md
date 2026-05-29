# Haehan AI 데스크톱 앱

서버(FastAPI + Chrome CDP + AI)에 접속하는 씬 클라이언트입니다.

## 설치 및 실행

```bash
cd admin-web/electron
npm install
npm start            # 개발 실행
npm run dist:win     # Windows EXE 빌드 → dist-electron/
```

## 서버 주소 설정

| 방법 | 설명 |
|------|------|
| 환경변수 | `HAEHAN_SERVER_URL=https://your-domain.com` |
| 앱 내 설정 | 트레이 아이콘 → 서버 주소 변경 |
| config 파일 | `%APPDATA%/haehan-ai-desktop/config.json` |

기본값: `http://localhost:3000`

## 아이콘

`electron/icon.png` (256×256 PNG) 파일을 추가하면 트레이·창·EXE 아이콘으로 사용됩니다.

## 배포 흐름

```
서버                        사용자 PC
├── Next.js :3000    ←───  Electron (서버 URL 접속)
├── FastAPI :8400
├── Chrome CDP :9222
└── OPENAI_API_KEY
```
