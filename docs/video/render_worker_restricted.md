# Render Worker Restricted (F-4S-13)

## 목적

F-4S-12 render plan을 기반으로 실제 ffmpeg 렌더링을 수행하는 worker.
기본값은 dry-run이며, 실제 실행은 `--execute` 명시 + ffmpeg 설치 확인 + 경로 검증 통과 시에만 허용된다.

## F-4S-12 render plan과의 관계

- F-4S-12: edit_queue → ffmpeg 명령 계획 생성 (실행 없음, `planned_only=True`)
- F-4S-13: render_plan → 계획 검증 후 실제 ffmpeg 실행 (조건부 허용)

render_plan JSON의 `render_items[].command_plan` 을 읽어 실행한다.

## restricted execution 조건

| 조건 | 설명 |
|---|---|
| `--execute` 명시 | 없으면 dry-run만 수행 |
| ffmpeg 설치 확인 | `shutil.which("ffmpeg")` 결과 있어야 실행 |
| program == "ffmpeg" | command_plan.program 이 ffmpeg 이어야 함 |
| args는 list[str] | shell=True 사용 불가 |
| 입력 파일 존재 | Path.exists() 확인 |
| 입력 경로 제한 | runs/video 또는 samples 하위만 허용 |
| 출력 경로 제한 | runs/video/render/output 하위만 허용 |
| 출력 확장자 | .mp4만 허용 |
| 외부 URL 금지 | http://, https://, file:// 등 입력 금지 |
| shell metachar 금지 | ; & | ` $ < > \ 포함 args 차단 |

## shell=True 금지

`subprocess.run(..., shell=True)` 는 절대 사용하지 않는다.
`os.system()` 도 사용 금지다.
모든 실행은 `subprocess.run([ffmpeg_path, *args], shell=False)` 형태로만 허용된다.

## 허용 입력/출력 경로

```
입력: runs/video/**, samples/**
출력: runs/video/render/output/**
확장자: .mp4만
```

## ffmpeg 미설치 시 동작

ffmpeg가 설치되지 않은 경우 (`shutil.which("ffmpeg")` == None):

- dry-run 모드: 정상 동작 (dry_run 결과만 생성)
- execute 모드: 각 항목을 `blocked` 처리, `error: ffmpeg_not_found` 기록
- 전체 실패(FAIL)가 아니라 WARN 수준 — 결과 파일은 정상 생성됨

## 실제 렌더 smoke

ffmpeg 미설치 환경에서는 실제 render smoke를 수행하지 않는다.
ffmpeg 설치 후 별도 승인형 단계에서 `--execute` 플래그와 함께 수행한다.

## YouTube 업로드

YouTube 업로드는 별도의 OAuth 승인형 단계에서 진행한다.
이 worker에는 업로드/publish/OAuth 관련 코드가 없다.
