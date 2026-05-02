import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { isSessionValid } from '@/lib/auth-session';

export const dynamic = 'force-dynamic';

type FileMapMaskingMode = 'mask_always' | 'reveal_after_auth' | 'reveal_on_trusted_device' | 'reveal_for_export_with_warning';
type RiskLevel = 'low' | 'medium' | 'high';

interface ApprovalItem {
  current_path: string;
  suggested_path: string;
  category: string;
  risk: RiskLevel;
  file_size_bytes?: number;
  modified_time?: string;
}

interface ApprovalGroup {
  group_id: string;
  label: string;
  default_selected: boolean;
  risk: RiskLevel;
  item_count: number;
  items: ApprovalItem[];
}

interface ExcludedGroup {
  group_id: string;
  label: string;
  reason: string;
  item_count: number;
  items: ApprovalItem[];
}

interface ApprovalSummary {
  total_preview_items: number;
  auto_selectable_items: number;
  excluded_sensitive_items: number;
  excluded_high_risk_items: number;
  duplicate_review_items: number;
}

interface ApiResponse {
  ok: boolean;
  generated_at: string;
  approval_request_id: string;
  approval_required: boolean;
  execution_enabled: boolean;
  request_only: boolean;
  mode?: FileMapMaskingMode;
  auth_verified?: boolean;
  summary: ApprovalSummary;
  approval_groups: ApprovalGroup[];
  excluded_groups: ExcludedGroup[];
  checklist: string[];
  error?: string;
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

function maskFilename(filename: string): string {
  const strongPatterns: Record<string, string> = {
    '신분증': '[신분증]',
    '주민등록증': '[주민등록증]',
    '운전면허': '[운전면허]',
    '여권': '[여권]',
    '통장.*사본': '[통장사본]',
    '계좌': '[계좌]',
    '금통': '[금융]',
    '은행': '[은행]',
    '형사.*사건': '[형사사건]',
    '고소': '[고소]',
    '소송': '[소송]',
    '변호인.*의견': '[법률문서]',
    '개인정보': '[개인정보]',
    '급여': '[급여]',
    '노임': '[급여]',
    '증거': '[증거]',
    '기밀': '[기밀]',
  };

  let masked = filename;

  for (const [pattern, replacement] of Object.entries(strongPatterns)) {
    masked = masked.replace(new RegExp(pattern, 'gi'), replacement);
  }

  const hasStrong = Object.keys(strongPatterns).some(
    (pattern) => new RegExp(pattern, 'i').test(filename)
  );

  if (hasStrong) {
    const weakPatterns: Record<string, string> = {
      '계약서': '[계약서]',
      '변호사': '[법률]',
      '합의금': '[계약]',
    };

    for (const [pattern, replacement] of Object.entries(weakPatterns)) {
      masked = masked.replace(new RegExp(pattern, 'gi'), replacement);
    }

    masked = masked.replace(/[가-힣]{2,4}(?=[\s_])/g, '****');
  }

  return masked;
}

function isSensitiveFile(filename: string): boolean {
  return /신분증|통장|계좌|급여|형사|고소|소송|변호인|개인정보/.test(filename);
}

function buildApprovalData(fileMap: any, shouldMask: boolean): { approval: ApprovalGroup[]; excluded: ExcludedGroup[] } {
  const approval: ApprovalGroup[] = [];
  const excluded: ExcludedGroup[] = [];

  // 기본 선택 가능 그룹
  const selectableGroups: Record<string, { label: string; risk: RiskLevel }> = {
    documents: { label: '업무문서', risk: 'low' },
    spreadsheets: { label: '엑셀/정산', risk: 'low' },
    cad: { label: 'CAD/도면', risk: 'low' },
    images: { label: '이미지/스캔', risk: 'low' },
    archive: { label: '설치파일 보관', risk: 'low' },
  };

  // 기본 제외 그룹
  const excludedGroups: Record<string, { label: string; reason: string }> = {
    sensitive: { label: '민감문서', reason: '민감정보 포함으로 기본 실행 대상 제외' },
    duplicates: { label: '중복검토', reason: '자동 삭제 불가능, 수동 확인 필요' },
  };

  // 파일 로드
  const files: Record<string, ApprovalItem[]> = {
    documents: [],
    spreadsheets: [],
    cad: [],
    images: [],
    archive: [],
    sensitive: [],
    duplicates: [],
  };

  // 문서 분류
  (fileMap.files_by_category?.document_files || []).forEach((file: any) => {
    files.documents.push({
      current_path: file.path || '',
      suggested_path: '01_업무문서',
      category: 'documents',
      risk: 'low',
      file_size_bytes: file.size_bytes,
      modified_time: file.modified_time,
    });
  });

  (fileMap.files_by_category?.spreadsheet_files || []).forEach((file: any) => {
    files.spreadsheets.push({
      current_path: file.path || '',
      suggested_path: '02_엑셀_내역_정산',
      category: 'spreadsheets',
      risk: 'low',
      file_size_bytes: file.size_bytes,
      modified_time: file.modified_time,
    });
  });

  (fileMap.files_by_category?.cad_files || []).forEach((file: any) => {
    files.cad.push({
      current_path: file.path || '',
      suggested_path: '03_CAD_도면',
      category: 'cad',
      risk: 'low',
      file_size_bytes: file.size_bytes,
      modified_time: file.modified_time,
    });
  });

  (fileMap.files_by_category?.image_files || []).forEach((file: any) => {
    files.images.push({
      current_path: file.path || '',
      suggested_path: '04_사진_스캔',
      category: 'images',
      risk: 'low',
      file_size_bytes: file.size_bytes,
      modified_time: file.modified_time,
    });
  });

  (fileMap.large_files || []).forEach((file: any) => {
    files.archive.push({
      current_path: file.path || '',
      suggested_path: '01_업무문서/06_설치파일_보관',
      category: 'archive',
      risk: 'low',
      file_size_bytes: file.size_bytes,
      modified_time: file.modified_time,
    });
  });

  // 민감 파일
  (fileMap.old_files || []).forEach((file: any) => {
    if (isSensitiveFile(file.name || '')) {
      files.sensitive.push({
        current_path: file.path || '',
        suggested_path: '01_업무문서/05_계약_증빙_민감',
        category: 'sensitive',
        risk: 'high',
        file_size_bytes: file.size_bytes,
        modified_time: file.modified_time,
      });
    }
  });

  // 중복 파일
  (fileMap.suspicious_duplicates || []).forEach((file: any) => {
    files.duplicates.push({
      current_path: file.path || '',
      suggested_path: '01_업무문서/08_중복검토',
      category: 'duplicates',
      risk: 'medium',
      file_size_bytes: file.size_bytes,
      modified_time: file.modified_time,
    });
  });

  // 기본 선택 가능 그룹 구성
  for (const [groupId, config] of Object.entries(selectableGroups)) {
    const groupFiles = files[groupId] || [];
    if (groupFiles.length > 0) {
      approval.push({
        group_id: groupId,
        label: config.label,
        default_selected: true,
        risk: config.risk,
        item_count: groupFiles.length,
        items: groupFiles.slice(0, 100),
      });
    }
  }

  // 기본 제외 그룹 구성
  for (const [groupId, config] of Object.entries(excludedGroups)) {
    const groupFiles = files[groupId] || [];
    if (groupFiles.length > 0) {
      excluded.push({
        group_id: groupId,
        label: config.label,
        reason: config.reason,
        item_count: groupFiles.length,
        items: groupFiles.slice(0, 50),
      });
    }
  }

  return { approval, excluded };
}

function buildApprovalSummary(approval: ApprovalGroup[], excluded: ExcludedGroup[]): ApprovalSummary {
  const autoSelectableItems = approval.reduce((sum, g) => sum + g.item_count, 0);
  const sensitiveItems = excluded.find((g) => g.group_id === 'sensitive')?.item_count || 0;
  const duplicateItems = excluded.find((g) => g.group_id === 'duplicates')?.item_count || 0;
  const totalItems = autoSelectableItems + sensitiveItems + duplicateItems;

  return {
    total_preview_items: totalItems,
    auto_selectable_items: autoSelectableItems,
    excluded_sensitive_items: sensitiveItems,
    excluded_high_risk_items: sensitiveItems,
    duplicate_review_items: duplicateItems,
  };
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
          approval_request_id: '',
          approval_required: false,
          execution_enabled: false,
          request_only: true,
          summary: {
            total_preview_items: 0,
            auto_selectable_items: 0,
            excluded_sensitive_items: 0,
            excluded_high_risk_items: 0,
            duplicate_review_items: 0,
          },
          approval_groups: [],
          excluded_groups: [],
          checklist: [],
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

    const { approval, excluded } = buildApprovalData(fileMap, shouldMask);
    const summary = buildApprovalSummary(approval, excluded);

    const requestId = `preview-local-${Date.now()}`;

    const response = NextResponse.json(
      {
        ok: true,
        generated_at: new Date().toISOString(),
        approval_request_id: requestId,
        approval_required: true,
        execution_enabled: false,
        request_only: true,
        mode,
        auth_verified: authVerified,
        summary,
        approval_groups: approval,
        excluded_groups: excluded,
        checklist: [
          '실제 파일 이동 전 최종 확인 필요',
          '민감문서는 기본 제외됨',
          '중복 파일은 수동 확인 후 삭제',
          '대용량 파일(1GB+)은 별도 검토 필요',
        ],
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
        approval_request_id: '',
        approval_required: false,
        execution_enabled: false,
        request_only: true,
        summary: {
          total_preview_items: 0,
          auto_selectable_items: 0,
          excluded_sensitive_items: 0,
          excluded_high_risk_items: 0,
          duplicate_review_items: 0,
        },
        approval_groups: [],
        excluded_groups: [],
        checklist: [],
        error: `api_failed: ${error instanceof Error ? error.message : 'unknown'}`,
      },
      { status: 500 }
    );
  }
}
