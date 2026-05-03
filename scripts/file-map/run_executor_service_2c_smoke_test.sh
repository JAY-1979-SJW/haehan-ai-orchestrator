#!/bin/bash
# EXECUTOR-SERVICE-2C: Local container smoke test
# 목표: admin-web + file-map-executor docker 통합 테스트
# 실행: bash scripts/file-map/run_executor_service_2c_smoke_test.sh

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker/docker-compose.dev.yml"
SMOKE_TEST="$REPO_ROOT/scripts/file-map/smoke_cleanup_execute_api_dry_run.py"

echo "========================================="
echo "EXECUTOR-SERVICE-2C: Local Smoke Test"
echo "========================================="
echo ""

# Step 1: Check prerequisites
echo "[Step 1/5] 전제조건 확인..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 설치 필요"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 설치 필요"
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ Compose 파일 없음: $COMPOSE_FILE"
    exit 1
fi

if [ ! -f "$SMOKE_TEST" ]; then
    echo "❌ Smoke test 파일 없음: $SMOKE_TEST"
    exit 1
fi

echo "✅ 필수 도구 확인 완료"
echo ""

# Step 2: Start services
echo "[Step 2/5] Docker services 시작..."
cd "$REPO_ROOT"
docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
docker compose -f "$COMPOSE_FILE" up -d

echo "⏳ Services 시작 대기 (30초)..."
sleep 30

# Check if services are healthy
echo "⏳ Service health 확인..."
max_retries=10
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    admin_health=$(docker compose -f "$COMPOSE_FILE" ps admin-web 2>/dev/null | grep -c "healthy" || echo 0)
    executor_health=$(docker compose -f "$COMPOSE_FILE" ps file-map-executor 2>/dev/null | grep -c "healthy" || echo 0)

    if [ "$admin_health" -gt 0 ] && [ "$executor_health" -gt 0 ]; then
        echo "✅ 모든 서비스 정상 (healthy)"
        break
    fi

    echo "  Retry $((retry_count + 1))/$max_retries..."
    sleep 3
    ((retry_count++))
done

if [ $retry_count -eq $max_retries ]; then
    echo "⚠️  Services 완전 준비 안 됨 (계속 진행)"
fi

echo ""

# Step 3: Run smoke test
echo "[Step 3/5] Smoke test 실행..."
export FILE_MAP_BASE_URL="http://localhost:3000"
echo "  FILE_MAP_BASE_URL=$FILE_MAP_BASE_URL"

smoke_result=$(python3 "$SMOKE_TEST" 2>&1 || echo '{"status":"FAIL","error":"script failed"}')
echo ""
echo "Smoke test 결과:"
echo "$smoke_result" | python3 -m json.tool || echo "$smoke_result"

echo ""

# Step 4: Verify results
echo "[Step 4/5] 결과 검증..."
test_status=$(echo "$smoke_result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'FAIL'))" 2>/dev/null || echo "FAIL")

if [ "$test_status" = "PASS" ] || [ "$test_status" = "WARN" ]; then
    echo "✅ Smoke test PASS"
    exit_code=0
else
    echo "❌ Smoke test FAIL"
    exit_code=1
fi

echo ""

# Step 5: Cleanup (optional)
echo "[Step 5/5] Cleanup..."
if [ "${KEEP_CONTAINERS:-0}" = "0" ]; then
    echo "🧹 Containers 정리 중..."
    docker compose -f "$COMPOSE_FILE" down
    echo "✅ Cleanup 완료"
else
    echo "⏸️  Containers 유지 (KEEP_CONTAINERS=1)"
fi

echo ""
echo "========================================="
echo "최종 상태: $test_status"
echo "========================================="

exit $exit_code
