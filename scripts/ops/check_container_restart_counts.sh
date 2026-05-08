#!/usr/bin/env bash
# scripts/ops/check_container_restart_counts.sh
#
# read-only 컨테이너 RestartCount 점검 스크립트.
# RestartCount > 0 인 컨테이너를 WARN으로 보고한다.
# 자동 restart, docker rm, 알림 발송은 수행하지 않는다.
#
# 사용:
#   ./scripts/ops/check_container_restart_counts.sh           # 전체 컨테이너
#   ./scripts/ops/check_container_restart_counts.sh --watch   # 우선 감시 대상만
#   ./scripts/ops/check_container_restart_counts.sh --json    # JSON 출력
#
# 종료 코드:
#   0 = 모든 우선 감시 대상이 RestartCount=0 + Exited 없음 (PASS)
#   1 = 하나 이상 WARN
#   2 = docker 명령 실패

set -u

WATCH_ONLY=false
JSON_OUT=false
for arg in "$@"; do
    case "$arg" in
        --watch) WATCH_ONLY=true ;;
        --json)  JSON_OUT=true ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \?//'
            exit 0
            ;;
    esac
done

# 우선 감시 대상 패턴 (정규식 OR)
WATCH_PATTERN='^(nginx|haehan-edge|haehan-ai-orchestrator-(api|admin-web|browser-worker|file-map-executor)|.*local-agent.*)$'

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker 명령을 찾을 수 없습니다." >&2
    exit 2
fi

# 모든 컨테이너 (실행 중 + 종료) 이름 수집
mapfile -t ALL_NAMES < <(docker ps -a --format '{{.Names}}' 2>/dev/null) || {
    echo "ERROR: docker ps 실패" >&2
    exit 2
}

if [ ${#ALL_NAMES[@]} -eq 0 ]; then
    echo "PASS: 컨테이너 없음"
    exit 0
fi

WARN_COUNT=0
WATCH_WARN_COUNT=0
declare -a REPORT_LINES=()
declare -a JSON_ENTRIES=()

for name in "${ALL_NAMES[@]}"; do
    # docker inspect로 RestartCount + Status + Image 일괄 조회
    info=$(docker inspect "$name" --format '{{.RestartCount}}|{{.State.Status}}|{{.State.ExitCode}}|{{.Config.Image}}' 2>/dev/null)
    if [ -z "$info" ]; then
        continue
    fi
    rc=$(echo "$info" | cut -d'|' -f1)
    status=$(echo "$info" | cut -d'|' -f2)
    exit_code=$(echo "$info" | cut -d'|' -f3)
    image=$(echo "$info" | cut -d'|' -f4)

    is_watch="no"
    if echo "$name" | grep -qE "$WATCH_PATTERN"; then
        is_watch="yes"
    fi

    if [ "$WATCH_ONLY" = true ] && [ "$is_watch" != "yes" ]; then
        continue
    fi

    severity="OK"
    reason=""
    if [ "$rc" -gt 0 ] 2>/dev/null; then
        severity="WARN"
        reason="RestartCount=$rc"
        WARN_COUNT=$((WARN_COUNT + 1))
        [ "$is_watch" = "yes" ] && WATCH_WARN_COUNT=$((WATCH_WARN_COUNT + 1))
    fi
    if [ "$status" = "exited" ]; then
        severity="WARN"
        reason="${reason:+$reason; }exited(exit=$exit_code)"
        WARN_COUNT=$((WARN_COUNT + 1))
        [ "$is_watch" = "yes" ] && WATCH_WARN_COUNT=$((WATCH_WARN_COUNT + 1))
    fi
    if [ "$status" = "restarting" ]; then
        severity="WARN"
        reason="${reason:+$reason; }restarting"
        WARN_COUNT=$((WARN_COUNT + 1))
        [ "$is_watch" = "yes" ] && WATCH_WARN_COUNT=$((WATCH_WARN_COUNT + 1))
    fi

    if [ "$severity" = "WARN" ] || [ "$JSON_OUT" = true ]; then
        REPORT_LINES+=("$severity: $name (status=$status, watch=$is_watch) $reason")
        # JSON entry — image는 결과에 포함하지 않음 (민감 정보 회피)
        JSON_ENTRIES+=("{\"name\":\"$name\",\"severity\":\"$severity\",\"status\":\"$status\",\"restart_count\":$rc,\"exit_code\":$exit_code,\"watch\":\"$is_watch\"}")
    fi
done

if [ "$JSON_OUT" = true ]; then
    printf '{"warn_count":%d,"watch_warn_count":%d,"entries":[' "$WARN_COUNT" "$WATCH_WARN_COUNT"
    first=true
    for e in "${JSON_ENTRIES[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            printf ','
        fi
        printf '%s' "$e"
    done
    printf ']}\n'
else
    if [ ${#REPORT_LINES[@]} -eq 0 ]; then
        if [ "$WATCH_ONLY" = true ]; then
            echo "PASS: 우선 감시 대상 모두 RestartCount=0, Exited 없음"
        else
            echo "PASS: 모든 컨테이너 RestartCount=0, Exited 없음"
        fi
    else
        for line in "${REPORT_LINES[@]}"; do
            echo "$line"
        done
        echo "---"
        echo "총 WARN: $WARN_COUNT (우선 감시 대상 WARN: $WATCH_WARN_COUNT)"
    fi
fi

# 우선 감시 대상에 WARN이 있으면 비정상 exit
if [ "$WATCH_WARN_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
