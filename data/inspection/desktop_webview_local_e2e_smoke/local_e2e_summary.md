# DESKTOP_WEBVIEW_LOCAL_E2E_SMOKE_01 — 2026-05-21T09:10:31.552999+00:00

## 최종 판정: **PASS_DESKTOP_WEBVIEW_LOCAL_E2E_SMOKE**

## 항목별 결과

| 항목 | 결과 |
|------|------|
| 서버 8765 LISTEN | ✅ |
| React UI index 200 | ✅ |
| JS asset 200 | ✅ index-AJ57VSAW.js |
| CSS asset 200 | ✅ index-BNhZLJTm.css |
| WS /ws/ui 101 | ✅ |
| agent_id visible | ✅ |
| server_connected | ✅ |
| pywebview 설치 | ✅ |
| webview_app_pywebview.py | ✅ |
| lifecycle health | ✅ |
| secret leak | ✅ 없음 |

## Admin Proxy

- admin_dashboard: ✅ HTTP 200
- admin_ops: ✅ HTTP 200
- admin_approvals: ✅ HTTP 200
- admin_agents: ✅ HTTP 200
- admin_cad: ✅ HTTP 200

## 실행 명령

```bash
# 서버 단독
python -m uvicorn desktop.local_server:app --host 127.0.0.1 --port 8765

# pywebview 앱
python -m desktop.webview_app_pywebview
```