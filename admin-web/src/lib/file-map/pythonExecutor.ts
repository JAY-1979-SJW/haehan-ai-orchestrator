/**파일 정리 executor 호출 (HTTP client).*/

/**
 * file-map-executor HTTP API를 호출하는 클라이언트.
 * 기존 spawn 기반 구조에서 HTTP 기반으로 전환.
 */

/**
 * file-map-executor 서비스 호출.
 *
 * @param inputData cleanup 실행 요청 payload
 * @returns executor 응답을 admin-web 형식으로 변환한 결과
 * @throws HTTP 호출 실패 또는 응답 파싱 실패 시 오류 발생
 */
export async function callPythonExecutor(
  inputData: Record<string, unknown>
): Promise<Record<string, unknown>> {
  // file-map-executor 서비스 URL
  const executorUrl =
    process.env.FILE_MAP_EXECUTOR_URL || 'http://file-map-executor:8510';

  const endpoint = `${executorUrl}/cleanup/execute`;

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(inputData),
      // 30초 timeout
      signal: AbortSignal.timeout(30000),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMsg =
        typeof errorData.error === 'string'
          ? errorData.error
          : `HTTP ${response.status}`;
      return {
        ok: false,
        error: `Executor error: ${errorMsg}`,
      };
    }

    const executorResponse = (await response.json()) as Record<
      string,
      unknown
    >;

    // file-map-executor 응답을 admin-web route.ts가 기대하는 형식으로 변환
    const adaptedResponse = adaptExecutorResponse(executorResponse, inputData);
    return adaptedResponse;
  } catch (error) {
    const errorMsg =
      error instanceof Error ? error.message : 'Unknown error';
    return {
      ok: false,
      error: `Executor service error: ${errorMsg}`,
    };
  }
}

/**
 * file-map-executor 응답을 admin-web route.ts 기대 형식으로 변환.
 *
 * @param executorResponse executor 서비스 응답
 * @param inputData 원본 요청 payload
 * @returns admin-web route가 기대하는 형식으로 변환된 응답
 */
function adaptExecutorResponse(
  executorResponse: Record<string, unknown>,
  inputData: Record<string, unknown>
): Record<string, unknown> {
  // executor가 오류를 반환한 경우
  if (!executorResponse.ok) {
    return {
      ok: false,
      error: executorResponse.error || 'Executor returned error',
    };
  }

  // admin-web route가 기대하는 구조로 변환
  // executor 응답: { ok, run_id, dry_run, success_count, succeeded, failed_count, failed, error }
  // admin-web 기대: { ok, result: { run_id, package_id, timestamp, success_count, failed_count, skipped_count, conflict_count, succeeded, failed, skipped, conflicts } }

  return {
    ok: true,
    result: {
      run_id: executorResponse.run_id || '',
      package_id: inputData.package_id || '',
      timestamp: new Date().toISOString(),
      success_count: executorResponse.success_count || 0,
      failed_count: executorResponse.failed_count || 0,
      skipped_count: 0, // executor에서 제공하지 않음
      conflict_count: 0, // executor에서 제공하지 않음
      succeeded: (executorResponse.succeeded as Array<any>) || [],
      failed: (executorResponse.failed as Array<any>) || [],
      skipped: [], // executor에서 제공하지 않음
      conflicts: [], // executor에서 제공하지 않음
    },
  };
}
