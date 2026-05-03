import fs from 'fs';
import path from 'path';

export type FileMapMaskingMode = 'mask_always' | 'reveal_after_auth' | 'reveal_on_trusted_device' | 'reveal_for_export_with_warning';
export type RiskLevel = 'low' | 'medium' | 'high';

export interface PreviewItem {
  current_path: string;
  suggested_path: string;
  category: string;
  risk: RiskLevel;
  masked: boolean;
  action_type: 'move_preview';
  file_size_bytes?: number;
  modified_time?: string;
}

export interface ApiResponse {
  ok: boolean;
  generated_at: string;
  execution_enabled: boolean;
  preview_only: boolean;
  total_items: number;
  mode?: FileMapMaskingMode;
  auth_verified?: boolean;
  items: PreviewItem[];
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

export function computeRisk(category: string, filename: string): RiskLevel {
  if (category === 'sensitive') return 'high';
  if (category === 'duplicates') return 'medium';
  return 'low';
}

export function buildPreviewItems(fileMap: any, shouldMask: boolean): PreviewItem[] {
  const items: PreviewItem[] = [];

  const categoryMapping: Record<string, { key: string; suggested: string }> = {
    archive: { key: 'large_files', suggested: '01_업무문서/06_설치파일_보관' },
    documents: { key: 'files_by_category.document_files', suggested: '01_업무문서' },
    spreadsheets: { key: 'files_by_category.spreadsheet_files', suggested: '02_엑셀_내역_정산' },
    cad: { key: 'files_by_category.cad_files', suggested: '03_CAD_도면' },
    images: { key: 'files_by_category.image_files', suggested: '04_사진_스캔' },
    sensitive: { key: 'old_files.sensitive', suggested: '01_업무문서/05_계약_증빙_민감' },
    duplicates: { key: 'suspicious_duplicates', suggested: '01_업무문서/08_중복검토' },
    hold: { key: 'suspicious_temp', suggested: '99_분류보류' },
  };

  for (const [catKey, config] of Object.entries(categoryMapping)) {
    let files: any[] = [];

    if (catKey === 'archive') {
      files = fileMap.large_files || [];
    } else if (catKey === 'sensitive') {
      files = (fileMap.old_files || []).filter((f: any) =>
        /신분증|통장|계좌|급여|형사|고소|소송|변호인/.test(f.name || '')
      );
    } else if (catKey.includes('spreadsheets')) {
      files = fileMap.files_by_category?.spreadsheet_files || [];
    } else if (catKey.includes('documents')) {
      files = fileMap.files_by_category?.document_files || [];
    } else if (catKey.includes('images')) {
      files = fileMap.files_by_category?.image_files || [];
    } else if (catKey.includes('cad')) {
      files = fileMap.files_by_category?.cad_files || [];
    } else if (catKey === 'duplicates') {
      files = fileMap.suspicious_duplicates || [];
    } else if (catKey === 'hold') {
      files = fileMap.suspicious_temp || [];
    }

    for (const file of files) {
      const filename = file.name || '';
      const displayName = shouldMask ? maskFilename(filename) : filename;

      items.push({
        current_path: file.path || filename,
        suggested_path: config.suggested,
        category: catKey,
        risk: computeRisk(catKey, filename),
        masked: shouldMask,
        action_type: 'move_preview',
        file_size_bytes: file.size_bytes,
        modified_time: file.modified_time,
      });
    }
  }

  return items;
}
