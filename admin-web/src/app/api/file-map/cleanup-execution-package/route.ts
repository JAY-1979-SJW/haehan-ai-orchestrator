import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { isSessionValid } from '@/lib/auth-session';

export const dynamic = 'force-dynamic';

type FileMapMaskingMode = 'mask_always' | 'reveal_after_auth' | 'reveal_on_trusted_device' | 'reveal_for_export_with_warning';
type RiskLevel = 'low' | 'medium' | 'high';
type OperationType = 'move_preview' | 'archive_preview';

interface ExecutionOperation {
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

interface PreflightCheck {
  check_id?: string;
  message: string;
  status?: 'pass' | 'warning' | 'fail';
}

interface BlockedOperation {
  reason: string;
  count: number;
  group_id?: string;
}

interface PackageSummary {
  total_candidate_items: number;
  included_items: number;
  excluded_items: number;
  estimated_total_size_bytes: number;
}

interface ApiResponse {
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

interface RequestBody {
  selected_group_ids?: string[];
  confirm_exclusions?: boolean;
  package_only?: boolean;
}

function getStoragePath(): string {
  const home = process.env.USERPROFILE || process.env.HOME || '';
  return path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory');
}

function loadLocalFileMap(): any {
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

function isSensitiveFile(filename: string): boolean {
  return /신분증|통장|계좌|급여|형사|고소|소송|변호인|개인정보/.test(filename);
}

function isHugeFile(size?: number): boolean {
  if (!size) return false;
  return size >= 1024 * 1024 * 1024; // 1GB
}

function generateOperationId(): string {
  return `op-${Date.now()}-${Math.random().toString(36).substring(7)}`;
}

function buildExecutionOperations(
  fileMap: any,
  selectedGroupIds: string[],
  shouldMask: boolean
): { operations: ExecutionOperation[]; excluded: BlockedOperation[] } {
  const operations: ExecutionOperation[] = [];
  const excludedCount: Record<string, number> = {};

  const groupMappings: Record<string, { path: string; type: OperationType }> = {
    documents: { path: '01_업무문서', type: 'move_preview' },
    spreadsheets: { path: '02_엑셀_내역_정산', type: 'move_preview' },
    cad: { path: '03_CAD_도면', type: 'move_preview' },
    images: { path: '04_사진_스캔', type: 'move_preview' },
    archive: { path: '01_업무문서/06_설치파일_보관', type: 'archive_preview' },
  };

  // 문서 그룹
  if (selectedGroupIds.includes('documents')) {
    (fileMap.files_by_category?.document_files || []).forEach((file: any) => {
      if (!isHugeFile(file.size_bytes)) {
        operations.push({
          operation_id: generateOperationId(),
          operation_type: 'move_preview',
          current_path: file.path || '',
          suggested_path: '01_업무문서',
          category: 'documents',
          risk: 'low',
          masked: shouldMask,
          requires_final_approval: true,
          rollback_hint: { from: '01_업무문서', to: file.path || '' },
          file_size_bytes: file.size_bytes,
          modified_time: file.modified_time,
        });
      } else {
        excludedCount.huge_files = (excludedCount.huge_files || 0) + 1;
      }
    });
  }

  // 스프레드시트 그룹
  if (selectedGroupIds.includes('spreadsheets')) {
    (fileMap.files_by_category?.spreadsheet_files || []).forEach((file: any) => {
      if (!isHugeFile(file.size_bytes)) {
        operations.push({
          operation_id: generateOperationId(),
          operation_type: 'move_preview',
          current_path: file.path || '',
          suggested_path: '02_엑셀_내역_정산',
          category: 'spreadsheets',
          risk: 'low',
          masked: shouldMask,
          requires_final_approval: true,
          rollback_hint: { from: '02_엑셀_내역_정산', to: file.path || '' },
          file_size_bytes: file.size_bytes,
          modified_time: file.modified_time,
        });
      } else {
        excludedCount.huge_files = (excludedCount.huge_files || 0) + 1;
      }
    });
  }

  // CAD 그룹
  if (selectedGroupIds.includes('cad')) {
    (fileMap.files_by_category?.cad_files || []).forEach((file: any) => {
      if (!isHugeFile(file.size_bytes)) {
        operations.push({
          operation_id: generateOperationId(),
          operation_type: 'move_preview',
          current_path: file.path || '',
          suggested_path: '03_CAD_도면',
          category: 'cad',
          risk: 'low',
          masked: shouldMask,
          requires_final_approval: true,
          rollback_hint: { from: '03_CAD_도면', to: file.path || '' },
          file_size_bytes: file.size_bytes,
          modified_time: file.modified_time,
        });
      } else {
        excludedCount.huge_files = (excludedCount.huge_files || 0) + 1;
      }
    });
  }

  // 이미지 그룹
  if (selectedGroupIds.includes('images')) {
    (fileMap.files_by_category?.image_files || []).forEach((file: any) => {
      if (!isHugeFile(file.size_bytes)) {
        operations.push({
          operation_id: generateOperationId(),
          operation_type: 'move_preview',
          current_path: file.path || '',
          suggested_path: '04_사진_스캔',
          category: 'images',
          risk: 'low',
          masked: shouldMask,
          requires_final_approval: true,
          rollback_hint: { from: '04_사진_스캔', to: file.path || '' },
          file_size_bytes: file.size_bytes,
          modified_time: file.modified_time,
        });
      } else {
        excludedCount.huge_files = (excludedCount.huge_files || 0) + 1;
      }
    });
  }

  // 설치파일 보관 그룹
  if (selectedGroupIds.includes('archive')) {
    (fileMap.large_files || []).forEach((file: any) => {
      if (!isHugeFile(file.size_bytes)) {
        operations.push({
          operation_id: generateOperationId(),
          operation_type: 'archive_preview',
          current_path: file.path || '',
          suggested_path: '01_업무문서/06_설치파일_보관',
          category: 'archive',
          risk: 'low',
          masked: shouldMask,
          requires_final_approval: true,
          rollback_hint: { from: '01_업무문서/06_설치파일_보관', to: file.path || '' },
          file_size_bytes: file.size_bytes,
          modified_time: file.modified_time,
        });
      } else {
        excludedCount.huge_files = (excludedCount.huge_files || 0) + 1;
      }
    });
  }

  // 기본 제외 항목들 카운팅
  const sensitiveCount = (fileMap.old_files || []).filter((f: any) => isSensitiveFile(f.name || '')).length;
  const duplicateCount = (fileMap.suspicious_duplicates || []).length;

  const excluded: BlockedOperation[] = [];

  if (sensitiveCount > 0) {
    excluded.push({
      reason: '민감문서 기본 제외',
      count: sensitiveCount,
      group_id: 'sensitive',
    });
  }

  if (duplicateCount > 0) {
    excluded.push({
      reason: '중복 검토 대상 기본 제외',
      count: duplicateCount,
      group_id: 'duplicates',
    });
  }

  if (excludedCount.huge_files > 0) {
    excluded.push({
      reason: '대용량 파일(1GB+) 별도 검토 필요',
      count: excludedCount.huge_files,
      group_id: 'huge_files',
    });
  }

  return { operations, excluded };
}

export async function GET(request: NextRequest): Promise<NextResponse<ApiResponse>> {
  try {
    const { searchParams } = new URL(request.url);

    const modeParam = searchParams.get('mode');
    const validModes: FileMapMaskingMode[] = ['mask_always', 'reveal_after_auth', 'reveal_on_trusted_device', 'reveal_for_export_with_warning'];
    const mode: FileMapMaskingMode = (modeParam && validModes.includes(modeParam as FileMapMaskingMode)) ? (modeParam as FileMapMaskingMode) : 'reveal_after_auth';

    const authVerified = isSessionValid();
    const fileMap = loadLocalFileMap();

    if (!fileMap) {
      return NextResponse.json(
        {
          ok: false,
          generated_at: new Date().toISOString(),
          package_id: '',
          package_only: true,
          execution_enabled: false,
          approval_required_for_execution: true,
          selected_groups: [],
          excluded_groups: [],
          summary: {
            total_candidate_items: 0,
            included_items: 0,
            excluded_items: 0,
            estimated_total_size_bytes: 0,
          },
          operations: [],
          preflight_checks: [],
          blocked_operations: [],
          error: 'file_map_not_found',
        },
        { status: 404 }
      );
    }

    let shouldMask = true;

    switch (mode) {
      case 'mask_always':
        shouldMask = true;
        break;
      case 'reveal_after_auth':
        shouldMask = !authVerified;
        break;
      case 'reveal_on_trusted_device':
        shouldMask = false;
        break;
      case 'reveal_for_export_with_warning':
        shouldMask = true;
        break;
    }

    const defaultSelected = ['documents', 'spreadsheets', 'cad', 'images', 'archive'];
    const { operations, excluded } = buildExecutionOperations(fileMap, defaultSelected, shouldMask);

    const totalSize = operations.reduce((sum, op) => sum + (op.file_size_bytes || 0), 0);

    const response = NextResponse.json(
      {
        ok: true,
        generated_at: new Date().toISOString(),
        package_id: `cleanup-package-local-${Date.now()}`,
        package_only: true,
        execution_enabled: false,
        approval_required_for_execution: true,
        mode,
        auth_verified: authVerified,
        selected_groups: defaultSelected,
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
      { status: 200 }
    );

    if (!shouldMask) {
      response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    }

    return response;
  } catch (error) {
    console.error('API error:', error);
    return NextResponse.json(
      {
        ok: false,
        generated_at: new Date().toISOString(),
        package_id: '',
        package_only: true,
        execution_enabled: false,
        approval_required_for_execution: true,
        selected_groups: [],
        excluded_groups: [],
        summary: {
          total_candidate_items: 0,
          included_items: 0,
          excluded_items: 0,
          estimated_total_size_bytes: 0,
        },
        operations: [],
        preflight_checks: [],
        blocked_operations: [],
        error: `api_failed: ${error instanceof Error ? error.message : 'unknown'}`,
      },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest): Promise<NextResponse<ApiResponse>> {
  try {
    const { searchParams } = new URL(request.url);

    const modeParam = searchParams.get('mode');
    const validModes: FileMapMaskingMode[] = ['mask_always', 'reveal_after_auth', 'reveal_on_trusted_device', 'reveal_for_export_with_warning'];
    const mode: FileMapMaskingMode = (modeParam && validModes.includes(modeParam as FileMapMaskingMode)) ? (modeParam as FileMapMaskingMode) : 'reveal_after_auth';

    const body: RequestBody = await request.json();
    const selectedGroupIds = body.selected_group_ids || [];
    const confirmExclusions = body.confirm_exclusions || false;

    // 유효성 검사: 선택 가능한 그룹만 허용
    const allowedGroups = new Set(['documents', 'spreadsheets', 'cad', 'images', 'archive']);
    const validSelectedGroups = selectedGroupIds.filter((id: string) => allowedGroups.has(id));

    // 민감/중복/고위험은 무시
    const forbiddenGroups = ['sensitive', 'duplicates', 'high_risk', 'hold'];
    const hasFormiddenGroups = selectedGroupIds.some((id: string) => forbiddenGroups.includes(id));

    const authVerified = isSessionValid();
    const fileMap = loadLocalFileMap();

    if (!fileMap) {
      return NextResponse.json(
        {
          ok: false,
          generated_at: new Date().toISOString(),
          package_id: '',
          package_only: true,
          execution_enabled: false,
          approval_required_for_execution: true,
          selected_groups: [],
          excluded_groups: [],
          summary: {
            total_candidate_items: 0,
            included_items: 0,
            excluded_items: 0,
            estimated_total_size_bytes: 0,
          },
          operations: [],
          preflight_checks: [],
          blocked_operations: [],
          error: 'file_map_not_found',
        },
        { status: 404 }
      );
    }

    let shouldMask = true;

    switch (mode) {
      case 'mask_always':
        shouldMask = true;
        break;
      case 'reveal_after_auth':
        shouldMask = !authVerified;
        break;
      case 'reveal_on_trusted_device':
        shouldMask = false;
        break;
      case 'reveal_for_export_with_warning':
        shouldMask = true;
        break;
    }

    const { operations, excluded } = buildExecutionOperations(fileMap, validSelectedGroups, shouldMask);

    const totalSize = operations.reduce((sum, op) => sum + (op.file_size_bytes || 0), 0);

    const response = NextResponse.json(
      {
        ok: true,
        generated_at: new Date().toISOString(),
        package_id: `cleanup-package-local-${Date.now()}`,
        package_only: true,
        execution_enabled: false,
        approval_required_for_execution: true,
        mode,
        auth_verified: authVerified,
        selected_groups: validSelectedGroups,
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
      { status: 200 }
    );

    if (!shouldMask) {
      response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    }

    return response;
  } catch (error) {
    console.error('API error:', error);
    return NextResponse.json(
      {
        ok: false,
        generated_at: new Date().toISOString(),
        package_id: '',
        package_only: true,
        execution_enabled: false,
        approval_required_for_execution: true,
        selected_groups: [],
        excluded_groups: [],
        summary: {
          total_candidate_items: 0,
          included_items: 0,
          excluded_items: 0,
          estimated_total_size_bytes: 0,
        },
        operations: [],
        preflight_checks: [],
        blocked_operations: [],
        error: `api_failed: ${error instanceof Error ? error.message : 'unknown'}`,
      },
      { status: 500 }
    );
  }
}
