/**cleanup-rollback 롤백 매니페스트 조회 (읽기 전용, 자동 실행 금지).*/

import fs from 'fs';
import path from 'path';
import os from 'os';

export interface RollbackEntry {
  operation_id: string;
  original_path: string;
  moved_to_path: string;
  rollback_possible: boolean;
  timestamp: string;
}

export interface RollbackManifest {
  run_id: string;
  package_id: string;
  generated_at: string;
  total_moved: number;
  entries: RollbackEntry[];
  notes: string;
}

/**
 * 롤백 매니페스트 저장 디렉토리 경로 계산.
 *
 * @returns 롤백 저장소 디렉토리 경로
 */
export function getRollbackDirPath(): string {
  const home = os.homedir();
  return path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory');
}

/**
 * 롤백 매니페스트 로드.
 *
 * @param runId 실행 ID
 * @returns 롤백 매니페스트 또는 null
 */
export function loadManifest(runId: string): RollbackManifest | null {
  const rollbackDir = getRollbackDirPath();
  const manifestFile = path.join(rollbackDir, `rollback_${runId}.json`);

  if (!fs.existsSync(manifestFile)) {
    return null;
  }

  try {
    const content = fs.readFileSync(manifestFile, 'utf-8');
    return JSON.parse(content) as RollbackManifest;
  } catch (error) {
    console.error('Failed to load manifest:', error);
    return null;
  }
}

/**
 * UUID v4 형식 검증.
 *
 * @param id 검증할 ID
 * @returns 유효한 UUID 형식이면 true
 */
export function isValidUuid(id: string): boolean {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(id);
}
