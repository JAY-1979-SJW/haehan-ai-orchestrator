import fs from 'fs';
import path from 'path';

export type FileMapMaskingMode = 'mask_always' | 'reveal_after_auth' | 'reveal_on_trusted_device' | 'reveal_for_export_with_warning';
export type RiskLevel = 'low' | 'medium' | 'high';

export interface ApprovalItem {
  current_path: string;
  suggested_path: string;
  category: string;
  risk: RiskLevel;
  file_size_bytes?: number;
  modified_time?: string;
}

export interface ApprovalGroup {
  group_id: string;
  label: string;
  default_selected: boolean;
  risk: RiskLevel;
  item_count: number;
  items: ApprovalItem[];
}

export interface ExcludedGroup {
  group_id: string;
  label: string;
  reason: string;
  item_count: number;
  items: ApprovalItem[];
}

export interface ApprovalSummary {
  total_preview_items: number;
  auto_selectable_items: number;
  excluded_sensitive_items: number;
  excluded_high_risk_items: number;
  duplicate_review_items: number;
}

export interface ApiResponse {
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

export function maskFilename(filename: string): string {
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

export function isSensitiveFile(filename: string): boolean {
  return /신분증|통장|계좌|급여|형사|고소|소송|변호인|개인정보/.test(filename);
}

function addApprovalItems(fileList: any[], category: string, path: string, risk: RiskLevel, files: Record<string, ApprovalItem[]>): void {
  (fileList || []).forEach((file: any) => {
    files[category] = files[category] || [];
    files[category].push({ current_path: file.path || '', suggested_path: path, category, risk, file_size_bytes: file.size_bytes, modified_time: file.modified_time });
  });
}

export function buildApprovalData(fileMap: any, shouldMask: boolean): { approval: ApprovalGroup[]; excluded: ExcludedGroup[] } {
  const approval: ApprovalGroup[] = [];
  const excluded: ExcludedGroup[] = [];
  const files: Record<string, ApprovalItem[]> = { documents: [], spreadsheets: [], cad: [], images: [], archive: [], sensitive: [], duplicates: [] };

  const selectableGroups: Record<string, { label: string; risk: RiskLevel }> = {
    documents: { label: '업무문서', risk: 'low' },
    spreadsheets: { label: '엑셀/정산', risk: 'low' },
    cad: { label: 'CAD/도면', risk: 'low' },
    images: { label: '이미지/스캔', risk: 'low' },
    archive: { label: '설치파일 보관', risk: 'low' },
  };

  const excludedGroups: Record<string, { label: string; reason: string }> = {
    sensitive: { label: '민감문서', reason: '민감정보 포함으로 기본 실행 대상 제외' },
    duplicates: { label: '중복검토', reason: '자동 삭제 불가능, 수동 확인 필요' },
  };

  addApprovalItems(fileMap.files_by_category?.document_files || [], 'documents', '01_업무문서', 'low', files);
  addApprovalItems(fileMap.files_by_category?.spreadsheet_files || [], 'spreadsheets', '02_엑셀_내역_정산', 'low', files);
  addApprovalItems(fileMap.files_by_category?.cad_files || [], 'cad', '03_CAD_도면', 'low', files);
  addApprovalItems(fileMap.files_by_category?.image_files || [], 'images', '04_사진_스캔', 'low', files);
  addApprovalItems(fileMap.large_files || [], 'archive', '01_업무문서/06_설치파일_보관', 'low', files);

  (fileMap.old_files || []).forEach((file: any) => {
    if (isSensitiveFile(file.name || '')) {
      files.sensitive.push({ current_path: file.path || '', suggested_path: '01_업무문서/05_계약_증빙_민감', category: 'sensitive', risk: 'high', file_size_bytes: file.size_bytes, modified_time: file.modified_time });
    }
  });

  (fileMap.suspicious_duplicates || []).forEach((file: any) => {
    files.duplicates.push({ current_path: file.path || '', suggested_path: '01_업무문서/08_중복검토', category: 'duplicates', risk: 'medium', file_size_bytes: file.size_bytes, modified_time: file.modified_time });
  });

  for (const [groupId, config] of Object.entries(selectableGroups)) {
    const groupFiles = files[groupId] || [];
    if (groupFiles.length > 0) {
      approval.push({ group_id: groupId, label: config.label, default_selected: true, risk: config.risk, item_count: groupFiles.length, items: groupFiles.slice(0, 100) });
    }
  }

  for (const [groupId, config] of Object.entries(excludedGroups)) {
    const groupFiles = files[groupId] || [];
    if (groupFiles.length > 0) {
      excluded.push({ group_id: groupId, label: config.label, reason: config.reason, item_count: groupFiles.length, items: groupFiles.slice(0, 50) });
    }
  }

  return { approval, excluded };
}

export function buildApprovalSummary(approval: ApprovalGroup[], excluded: ExcludedGroup[]): ApprovalSummary {
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
