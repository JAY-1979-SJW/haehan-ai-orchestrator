import fs from 'fs';
import path from 'path';

export type FileMapMaskingMode = 'mask_always' | 'reveal_after_auth' | 'reveal_on_trusted_device' | 'reveal_for_export_with_warning';
export type RiskLevel = 'low' | 'medium' | 'high';
export type OperationType = 'move_preview' | 'archive_preview';

export interface ExecutionOperation {
  operation_id: string;
  operation_type: OperationType;
  current_path: string;
  suggested_path: string;
  category: string;
  risk: RiskLevel;
  masked: boolean;
  requires_final_approval: boolean;
  rollback_hint: {
    from: string;
    to: string;
  };
  file_size_bytes?: number;
  modified_time?: string;
}

export interface PreflightCheck {
  check_id?: string;
  message: string;
  status?: 'pass' | 'warning' | 'fail';
}

export interface BlockedOperation {
  reason: string;
  count: number;
  group_id?: string;
}

export interface PackageSummary {
  total_candidate_items: number;
  included_items: number;
  excluded_items: number;
  estimated_total_size_bytes: number;
}

export interface ApiResponse {
  ok: boolean;
  generated_at: string;
  package_id: string;
  package_only: boolean;
  execution_enabled: boolean;
  approval_required_for_execution: boolean;
  mode?: FileMapMaskingMode;
  auth_verified?: boolean;
  selected_groups: string[];
  excluded_groups: string[];
  summary: PackageSummary;
  operations: ExecutionOperation[];
  preflight_checks: PreflightCheck[];
  blocked_operations: BlockedOperation[];
  error?: string;
}

export interface RequestBody {
  selected_group_ids?: string[];
  confirm_exclusions?: boolean;
  package_only?: boolean;
}

export function getStoragePath(): string {
  const home = process.env.USERPROFILE || process.env.HOME || '';
  return path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory');
}

export function loadLocalFileMap(): any {
  const storagePath = getStoragePath();
  const reportPath = path.join(storagePath, 'local_file_map.json');

  try {
    if (!fs.existsSync(reportPath)) {
      return null;
    }

    const content = fs.readFileSync(reportPath, 'utf-8');
    return JSON.parse(content);
  } catch (error) {
    console.error('Failed to load local_file_map:', error);
    return null;
  }
}

export function isSensitiveFile(filename: string): boolean {
  return /신분증|통장|계좌|급여|형사|고소|소송|변호인|개인정보/.test(filename);
}

export function isHugeFile(size?: number): boolean {
  if (!size) return false;
  return size >= 1024 * 1024 * 1024;
}

export function generateOperationId(): string {
  return `op-${Date.now()}-${Math.random().toString(36).substring(7)}`;
}

function addOperations(files: any[], groupId: string, path: string, type: OperationType, operations: ExecutionOperation[], excludedCount: Record<string, number>, shouldMask: boolean): void {
  (files || []).forEach((file: any) => {
    if (!isHugeFile(file.size_bytes)) {
      operations.push({
        operation_id: generateOperationId(),
        operation_type: type,
        current_path: file.path || '',
        suggested_path: path,
        category: groupId,
        risk: 'low',
        masked: shouldMask,
        requires_final_approval: true,
        rollback_hint: { from: path, to: file.path || '' },
        file_size_bytes: file.size_bytes,
        modified_time: file.modified_time,
      });
    } else {
      excludedCount.huge_files = (excludedCount.huge_files || 0) + 1;
    }
  });
}

function buildExcludedList(fileMap: any, excludedCount: Record<string, number>): BlockedOperation[] {
  const excluded: BlockedOperation[] = [];
  const sensitiveCount = (fileMap.old_files || []).filter((f: any) => isSensitiveFile(f.name || '')).length;
  const duplicateCount = (fileMap.suspicious_duplicates || []).length;

  if (sensitiveCount > 0) excluded.push({ reason: '민감문서 기본 제외', count: sensitiveCount, group_id: 'sensitive' });
  if (duplicateCount > 0) excluded.push({ reason: '중복 검토 대상 기본 제외', count: duplicateCount, group_id: 'duplicates' });
  if (excludedCount.huge_files > 0) excluded.push({ reason: '대용량 파일(1GB+) 별도 검토 필요', count: excludedCount.huge_files, group_id: 'huge_files' });

  return excluded;
}

export function buildExecutionOperations(
  fileMap: any,
  selectedGroupIds: string[],
  shouldMask: boolean
): { operations: ExecutionOperation[]; excluded: BlockedOperation[] } {
  const operations: ExecutionOperation[] = [];
  const excludedCount: Record<string, number> = {};

  if (selectedGroupIds.includes('documents')) addOperations(fileMap.files_by_category?.document_files, 'documents', '01_업무문서', 'move_preview', operations, excludedCount, shouldMask);
  if (selectedGroupIds.includes('spreadsheets')) addOperations(fileMap.files_by_category?.spreadsheet_files, 'spreadsheets', '02_엑셀_내역_정산', 'move_preview', operations, excludedCount, shouldMask);
  if (selectedGroupIds.includes('cad')) addOperations(fileMap.files_by_category?.cad_files, 'cad', '03_CAD_도면', 'move_preview', operations, excludedCount, shouldMask);
  if (selectedGroupIds.includes('images')) addOperations(fileMap.files_by_category?.image_files, 'images', '04_사진_스캔', 'move_preview', operations, excludedCount, shouldMask);
  if (selectedGroupIds.includes('archive')) addOperations(fileMap.large_files, 'archive', '01_업무문서/06_설치파일_보관', 'archive_preview', operations, excludedCount, shouldMask);

  const excluded = buildExcludedList(fileMap, excludedCount);
  return { operations, excluded };
}

export function getMaskingPolicy(mode: FileMapMaskingMode, authVerified: boolean): boolean {
  switch (mode) {
    case 'mask_always': return true;
    case 'reveal_after_auth': return !authVerified;
    case 'reveal_on_trusted_device': return !authVerified;
    case 'reveal_for_export_with_warning': return true;
    default: return true;
  }
}

export function errorResponse(message: string, statusCode: number = 404): { body: ApiResponse; status: number } {
  return {
    body: {
      ok: false,
      generated_at: new Date().toISOString(),
      package_id: '',
      package_only: true,
      execution_enabled: false,
      approval_required_for_execution: true,
      selected_groups: [],
      excluded_groups: [],
      summary: { total_candidate_items: 0, included_items: 0, excluded_items: 0, estimated_total_size_bytes: 0 },
      operations: [],
      preflight_checks: [],
      blocked_operations: [],
      error: message,
    },
    status: statusCode,
  };
}

export function successResponse(
  operations: ExecutionOperation[],
  excluded: BlockedOperation[],
  mode: FileMapMaskingMode,
  authVerified: boolean,
  selectedGroups: string[]
): { body: ApiResponse; status: number } {
  const totalSize = operations.reduce((sum, op) => sum + (op.file_size_bytes || 0), 0);
  return {
    body: {
      ok: true,
      generated_at: new Date().toISOString(),
      package_id: `cleanup-package-local-${Date.now()}`,
      package_only: true,
      execution_enabled: false,
      approval_required_for_execution: true,
      mode,
      auth_verified: authVerified,
      selected_groups: selectedGroups,
      excluded_groups: ['sensitive', 'duplicates', 'hold', 'huge_files'],
      summary: {
        total_candidate_items: operations.length + excluded.reduce((sum, e) => sum + e.count, 0),
        included_items: operations.length,
        excluded_items: excluded.reduce((sum, e) => sum + e.count, 0),
        estimated_total_size_bytes: totalSize,
      },
      operations: operations.slice(0, 200),
      preflight_checks: [
        { message: '대상 경로 충돌 여부 확인 필요' },
        { message: '파일 존재 여부 최종 확인 필요' },
        { message: '실행 전 백업/복구 계획 확인 필요' },
      ],
      blocked_operations: excluded,
    },
    status: 200,
  };
}
