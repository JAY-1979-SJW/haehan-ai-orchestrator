# Google Live Read Partial Verification

Generated: 2026-05-26T00:11:55

## Summary

- planned: 31
- visited: 15
- failed: 16
- mode: read-only, no click, no input, no submit
- result: partial; not all Google domains passed live verification

## Tab Results

| Tab | Status | Planned | Visited | Failed | Report |
| --- | --- | ---: | ---: | ---: | --- |
| `search` | `completed` | 1 | 0 | 1 | `C:/work/01. haehan-ai-orchestrator/data/google_surface_live/google_surface_live_20260525_150611.json` |
| `identity` | `completed` | 1 | 1 | 0 | `C:/work/01. haehan-ai-orchestrator/data/google_surface_live/google_surface_live_20260525_150625.json` |
| `workspace` | `completed` | 12 | 7 | 5 | `C:/work/01. haehan-ai-orchestrator/data/google_surface_live/google_surface_live_20260525_150844.json` |
| `youtube` | `completed` | 2 | 1 | 1 | `C:/work/01. haehan-ai-orchestrator/data/google_surface_live/google_surface_live_20260525_150912.json` |
| `marketing` | `completed` | 8 | 6 | 2 | `C:/work/01. haehan-ai-orchestrator/data/google_surface_live/google_surface_live_20260525_151035.json` |
| `developer` | `failed` | 7 | 0 | 7 | `C:/work/01. haehan-ai-orchestrator/data/google_surface_live/google_surface_live_20260525_151046.json` |

## Failed Surfaces

- `search/google_home`: `failed` 
- `workspace/gmail`: `failed` 
- `workspace/calendar`: `failed` 
- `workspace/chat`: `failed` 
- `workspace/contacts`: `failed` 
- `workspace/tasks`: `failed` 
- `youtube/youtube_studio`: `failed` 
- `marketing/ads`: `failed` 
- `marketing/adsense`: `failed` 
- `developer`: report failed before per-surface capture; warnings=['CDP 서버 연결 실패: HTTPConnectionPool(host=\'127.0.0.1\', port=9222): Max retries exceeded with url: /json (Caused by NewConnectionError("HTTPConnection(host=\'127.0.0.1\', port=9222): Failed to establish a new connection: [WinError 10061] 대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다"))']
