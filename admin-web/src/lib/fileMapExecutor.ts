/**파일 정리 실행: API를 통한 파일 이동.*/

export interface ExecuteMoveRequest {
  preflightId: string;
  packageId: string;
  approvalToken: string;
  userConfirmedExecution: boolean;
  dryRun?: boolean;
}

export interface ExecuteMoveResult {
  ok: boolean;
  runId?: string;
  packageId?: string;
  timestamp?: string;
  successCount?: number;
  failedCount?: number;
  skippedCount?: number;
  conflictCount?: number;
  dryRun?: boolean;
  succeeded?: Array<{
    operationId: string;
    sourcePath: string;
    targetPath: string;
    category: string;
    fileSizeBytes: number;
    dryRun: boolean;
  }>;
  failed?: Array<{
    operationId: string;
    sourcePath: string;
    targetPath: string;
    error: string;
  }>;
  skipped?: Array<{
    operationId: string;
    sourcePath: string;
    targetPath: string;
    reason: string;
  }>;
  conflicts?: Array<{
    operationId: string;
    sourcePath: string;
    targetPath: string;
    reason: string;
  }>;
  error?: string;
}

/**
 * 파일 이동 실행 (API 호출).
 *
 * @param request 실행 요청
 * @returns 실행 결과
 */
export async function executeMoves(request: ExecuteMoveRequest): Promise<ExecuteMoveResult> {
  const payload = {
    preflight_id: request.preflightId,
    package_id: request.packageId,
    approval_token: request.approvalToken,
    user_confirmed_execution: request.userConfirmedExecution,
    dry_run: request.dryRun !== false, // 기본값: true
  };

  try {
    const response = await fetch('/api/file-map/cleanup-execute', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    const result = await response.json() as Record<string, any>;

    if (!response.ok) {
      return {
        ok: false,
        error: result.error || `API error: ${response.status}`,
      };
    }

    // API 응답 변환: snake_case → camelCase
    const transformed: ExecuteMoveResult = {
      ok: result.ok,
      runId: result.run_id,
      packageId: result.package_id,
      timestamp: result.timestamp,
      successCount: result.success_count,
      failedCount: result.failed_count,
      skippedCount: result.skipped_count,
      conflictCount: result.conflict_count,
      dryRun: payload.dry_run,
      succeeded: result.succeeded?.map((item: any) => ({
        operationId: item.operation_id,
        sourcePath: item.source_path,
        targetPath: item.target_path,
        category: item.category,
        fileSizeBytes: item.file_size_bytes,
        dryRun: item.dry_run,
      })),
      failed: result.failed?.map((item: any) => ({
        operationId: item.operation_id,
        sourcePath: item.source_path,
        targetPath: item.target_path,
        error: item.error,
      })),
      skipped: result.skipped?.map((item: any) => ({
        operationId: item.operation_id,
        sourcePath: item.source_path,
        targetPath: item.target_path,
        reason: item.reason,
      })),
      conflicts: result.conflicts?.map((item: any) => ({
        operationId: item.operation_id,
        sourcePath: item.source_path,
        targetPath: item.target_path,
        reason: item.reason,
      })),
      error: result.error,
    };

    return transformed;
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : 'Unknown error',
    };
  }
}

/**
 * 실행 결과 요약 텍스트 생성.
 */
export function formatExecutionSummary(result: ExecuteMoveResult): string {
  if (!result.ok) {
    return `오류: ${result.error}`;
  }

  const lines = [
    `실행 결과 (${result.runId})`,
    `성공: ${result.successCount || 0}개`,
    `실패: ${result.failedCount || 0}개`,
    `스킵: ${result.skippedCount || 0}개`,
    `충돌: ${result.conflictCount || 0}개`,
  ];

  if (result.dryRun !== false) {
    lines.push('(테스트 모드 - 실제 파일은 이동하지 않음)');
  }

  return lines.join('\n');
}
