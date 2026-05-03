/**cleanup-plan 캐시 조회 (읽기 전용).*/

import fs from 'fs';
import path from 'path';

export interface CleanupPlanCategory {
  name: string;
  count: number;
  reason: string;
  suggested_path: string;
  samples: Array<{
    masked_name: string;
    file_path: string;
    size_bytes: number;
    modified_time: string;
  }>;
}

export interface CleanupPlanSummary {
  total_files: number;
  archive_candidates: number;
  document_candidates: number;
  spreadsheet_candidates: number;
  cad_candidates: number;
  image_candidates: number;
  sensitive_candidates: number;
  duplicate_review_candidates: number;
  hold_candidates: number;
}

/**
 * 저장소 경로 계산 (로컬 인벤토리).
 *
 * @returns 저장소 디렉토리 경로
 */
export function getStoragePath(): string {
  const home = process.env.USERPROFILE || process.env.HOME || '';
  return path.join(home, 'AppData', 'Local', 'HaehanAI', 'inventory');
}

/**
 * local_file_map.json 읽기 (캐시 로드).
 *
 * @returns 캐시 객체 또는 null
 */
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

/**
 * 파일명 마스킹 (민감 정보 보호).
 *
 * @param filename 원본 파일명
 * @returns 마스킹된 파일명
 */
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

/**
 * 파일맵 요약 구축.
 *
 * @param fileMap 로드된 파일맵 객체
 * @returns 요약 정보
 */
export function buildCleanupSummary(fileMap: any): CleanupPlanSummary {
  return {
    total_files: fileMap.total_files || 0,
    archive_candidates: fileMap.large_files?.length || 0,
    document_candidates: fileMap.files_by_category?.document || 0,
    spreadsheet_candidates: fileMap.files_by_category?.spreadsheet || 0,
    cad_candidates: fileMap.files_by_category?.cad || 0,
    image_candidates: fileMap.files_by_category?.image || 0,
    sensitive_candidates: Math.ceil((fileMap.old_files?.length || 0) * 0.02),
    duplicate_review_candidates: fileMap.suspicious_duplicates?.length || 0,
    hold_candidates: fileMap.suspicious_temp?.length || 0,
  };
}

/**
 * 정리 카테고리 구축.
 *
 * @param fileMap 로드된 파일맵 객체
 * @param shouldMask 마스킹 여부
 * @returns 카테고리 맵
 */
export function buildCategories(fileMap: any, shouldMask: boolean): Record<string, CleanupPlanCategory> {
  const processFiles = (files: any[], categoryName: string, reason: string, suggestedPath: string): CleanupPlanCategory => {
    const samples = (files || []).slice(0, 30).map((file: any) => ({
      masked_name: shouldMask ? maskFilename(file.name || '') : file.name || '',
      file_path: file.path || '',
      size_bytes: file.size_bytes || 0,
      modified_time: file.modified_time || '',
    }));

    return {
      name: categoryName,
      count: files?.length || 0,
      reason,
      suggested_path: suggestedPath,
      samples,
    };
  };

  return {
    archive: processFiles(fileMap.large_files, '보관', '오래된 설치파일', '01_업무문서/06_설치파일_보관'),
    documents: processFiles(
      (fileMap.files_by_category?.document_files || []).slice(0, 100),
      '업무문서',
      '분류 가능한 업무 문서',
      '01_업무문서'
    ),
    spreadsheets: processFiles(
      (fileMap.files_by_category?.spreadsheet_files || []).slice(0, 100),
      '엑셀/정산',
      '스프레드시트 및 내역서',
      '02_엑셀_내역_정산'
    ),
    cad: processFiles(
      (fileMap.files_by_category?.cad_files || []).slice(0, 50),
      'CAD/도면',
      '도면 및 설계 파일',
      '03_CAD_도면'
    ),
    images: processFiles(
      (fileMap.files_by_category?.image_files || []).slice(0, 100),
      '이미지/스캔',
      '사진, 스캔, 이미지',
      '04_사진_스캔'
    ),
    sensitive: processFiles(
      (fileMap.old_files || []).filter((f: any) =>
        /신분증|통장|계좌|급여|형사|고소|소송|변호인/.test(f.name || '')
      ).slice(0, 50),
      '민감문서',
      '보안이 필요한 민감문서',
      '01_업무문서/05_계약_증빙_민감'
    ),
    duplicates: processFiles(fileMap.suspicious_duplicates, '중복검토', '검토 후 삭제 가능한 중복 파일', '01_업무문서/08_중복검토'),
    hold: processFiles(fileMap.suspicious_temp, '분류보류', '현재 분류 불가 또는 최근 파일', '99_분류보류'),
  };
}
