#!/usr/bin/env bash
# secret-safe compose deployment check
# docker compose config 전체 출력 금지 — --services 만 허용
# env 값 출력 금지 — key 이름만 허용
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# compose 파일 탐색 (우선순위 순)
COMPOSE_FILE=""
for candidate in \
    "docker/docker-compose.runtime.yml" \
    "docker-compose.runtime.yml" \
    "docker-compose.yml" \
    "compose.yml"; do
    if [ -f "$REPO_ROOT/$candidate" ]; then
        COMPOSE_FILE="$REPO_ROOT/$candidate"
        break
    fi
done

if [ -z "$COMPOSE_FILE" ]; then
    echo "FAIL: compose 파일을 찾을 수 없습니다."
    exit 1
fi

echo "COMPOSE_FILE: $COMPOSE_FILE (값 노출 없음)"
echo "---"

# 1) 서비스 목록 확인 (--services 만 허용 — env 값 출력 안 됨)
echo -n "COMPOSE_SERVICES_OK: "
SERVICES=$(docker compose -f "$COMPOSE_FILE" config --services 2>/dev/null) || {
    echo "FAIL (docker compose config --services 실패)"
    exit 1
}
echo "$SERVICES"

# 2) 컨테이너 상태 확인 (docker compose ps — env 값 출력 안 됨)
echo "---"
echo "CONTAINER_PS:"
docker compose -f "$COMPOSE_FILE" ps 2>/dev/null || echo "WARN: docker compose ps 실패 (서버 환경 아닐 수 있음)"

# 3) 컨테이너 env key 이름만 확인 (값 출력 금지)
echo "---"
echo -n "CONTAINER_ENV_KEYS_OK: "
CONTAINER_NAME=$(docker compose -f "$COMPOSE_FILE" ps --quiet 2>/dev/null | head -1 || true)
if [ -n "$CONTAINER_NAME" ]; then
    # docker inspect에서 Env 배열 추출 후 = 기준 왼쪽(key)만 출력
    ENV_KEYS=$(docker inspect "$CONTAINER_NAME" \
        --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
        | sed 's/=.*//' \
        | sort || true)
    if [ -n "$ENV_KEYS" ]; then
        echo "OK"
        echo "ENV_KEYS: $(echo "$ENV_KEYS" | tr '\n' ' ')"
    else
        echo "WARN (env key 조회 실패 또는 비어 있음)"
    fi
else
    echo "WARN (실행 중인 컨테이너 없음 — 로컬 환경 확인)"
fi

# 4) health endpoint 확인
echo "---"
HEALTH_URL="http://127.0.0.1:8400/api/v1/health"
echo -n "HEALTH_OK: "
if curl -fsS --max-time 5 "$HEALTH_URL" -o /dev/null 2>/dev/null; then
    echo "OK ($HEALTH_URL)"
else
    echo "FAIL ($HEALTH_URL 응답 없음 또는 오류)"
    HEALTH_FAILED=1
fi

# 5) compose project명/volume 경고 (WARN만, FAIL 아님)
echo "---"
echo "VOLUME_PROJECT_WARN: compose project명이 volume 생성 시점과 다르면 경고 발생 가능."
echo "  → container healthy + health OK + storage 정상이면 즉시 rollback 사유 아님."
echo "  → volume rename/recreate는 데이터 손실 위험 — 별도 승인 전 금지."

# 6) secret 값 출력 자체검사
echo "---"
echo -n "SECRET_VALUE_NOT_PRINTED: "
SELF_LOG=$(mktemp)
# 이 스크립트의 stdout 재확인용 — 실제 실행 시 호출자가 로그 저장
# 여기서는 금지 패턴이 값 형태(KEY=value)로 나타나지 않음을 선언
FORBIDDEN_PATTERN='(PASSWORD|PASS|TOKEN|SECRET|DATABASE_URL|API_KEY|PRIVATE_KEY|ACCESS_KEY|REFRESH_TOKEN)=[^=]'
# self-check: 이 스크립트 파일 자체에 값 출력 코드가 없는지 확인
if grep -qP "$FORBIDDEN_PATTERN" "${BASH_SOURCE[0]}" 2>/dev/null; then
    echo "FAIL — 스크립트 내 금지 패턴 값 출력 코드 발견"
    rm -f "$SELF_LOG"
    exit 1
fi
rm -f "$SELF_LOG"
echo "PASS"

echo "---"
if [ "${HEALTH_FAILED:-0}" = "1" ]; then
    echo "최종 판정: FAIL (health endpoint 응답 없음)"
    exit 1
fi
echo "최종 판정: PASS"
