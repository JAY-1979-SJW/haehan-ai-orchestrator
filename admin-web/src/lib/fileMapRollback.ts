/**파일 정리 롤백: 매니페스트 조회 (자동 롤백 실행 금지).*/

export interface RollbackEntry {
  operationId: string;
  originalPath: string;
  movedToPath: string;
  rollbackPossible: boolean;
  timestamp: string;
}

export interface RollbackManifest {
  runId: string;
  packageId: string;
  generatedAt: string;
  totalMoved: number;
  entries: RollbackEntry[];
  notes: string;
}

export interface RollbackResponse {
  ok: boolean;
  manifest?: RollbackManifest;
  error?: string;
}

/**
 * 롤백 매니페스트 조회.
 *
 * @param runId 실행 ID
 * @returns 롤백 매니페스트 (로드 실패 시 null)
 */
export async function loadRollbackManifest(runId: string): Promise<RollbackManifest | null> {
  if (!runId) {
    return null;
  }

  try {
    const response = await fetch(`/api/file-map/cleanup-rollback?run_id=${encodeURIComponent(runId)}`);
    const result: RollbackResponse = await response.json();

    if (!result.ok) {
      console.error('Failed to load rollback manifest:', result.error);
      return null;
    }

    return result.manifest || null;
  } catch (err) {
    console.error('Error loading rollback manifest:', err);
    return null;
  }
}

/**
 * 롤백 매니페스트 정보 표시용 텍스트.
 */
export function formatRollbackInfo(manifest: RollbackManifest): string {
  const lines = [
    `🔄 롤백 정보`,
    `실행 ID: ${manifest.runId}`,
    `이동된 파일: ${manifest.totalMoved}개`,
    `생성 시간: ${new Date(manifest.generatedAt).toLocaleString('ko-KR')}`,
    '',
    `📝 주의:`,
    manifest.notes,
  ];

  return lines.join('\n');
}

/**
 * 롤백 가능한 항목 필터링.
 */
export function getRollbackableEntries(manifest: RollbackManifest): RollbackEntry[] {
  return manifest.entries.filter((e) => e.rollbackPossible);
}
