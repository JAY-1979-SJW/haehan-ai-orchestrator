/**
 * 민감 파일명 마스킹 유틸리티
 * Python privacy.py와 동일한 정책 구현
 */

const STRONG_SENSITIVE_PATTERNS: Record<string, string> = {
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

const WEAK_SENSITIVE_PATTERNS: Record<string, string> = {
  '계약서': '[계약서]',
  '변호사': '[법률]',
  '합의금': '[계약]',
};

const EXCLUDE_PATTERNS = [
  '한컴오피스',
  'hwp',
  'hancom',
  '마이크로소프트.*오피스',
  'microsoft.*office',
  'office',

  '\\.iso$',
  '\\.cab$',
  'installer',
  'setup',
  '\\.msi$',
  '\\.exe$',
];

export function maskFilename(filename: string): string {
  if (!filename) return filename;

  // 1. 제외 패턴 확인
  for (const pattern of EXCLUDE_PATTERNS) {
    if (new RegExp(pattern, 'i').test(filename)) {
      return filename;
    }
  }

  let masked = filename;

  // 2. 강한 민감 패턴 마스킹
  for (const [pattern, replacement] of Object.entries(STRONG_SENSITIVE_PATTERNS)) {
    masked = masked.replace(new RegExp(pattern, 'gi'), replacement);
  }

  // 3. 약한 민감 패턴 처리
  const hasStrong = Object.keys(STRONG_SENSITIVE_PATTERNS).some(
    (pattern) => new RegExp(pattern, 'i').test(filename)
  );

  if (hasStrong) {
    for (const [pattern, replacement] of Object.entries(WEAK_SENSITIVE_PATTERNS)) {
      masked = masked.replace(new RegExp(pattern, 'gi'), replacement);
    }
    // 개인명 마스킹
    masked = masked.replace(/[가-힣]{2,4}(?=[\s_])/g, '****');
  }

  return masked;
}

export function renderFilename(
  filename: string,
  revealSensitiveNames: boolean = false,
  authVerified: boolean = false
): string {
  if (revealSensitiveNames && authVerified) {
    return filename;
  }
  return maskFilename(filename);
}

export function maskFileObject(
  file: any,
  reveal: boolean = false
): any {
  if (!file) return file;
  return {
    ...file,
    name: renderFilename(file.name, reveal, reveal),
    path: maskPath(file.path, reveal, reveal),
  };
}

export function maskPath(
  path: string,
  revealSensitiveNames: boolean = false,
  authVerified: boolean = false
): string {
  if (!path) return path;

  if (!revealSensitiveNames || !authVerified) {
    // 마스킹 모드
    const parts = path.split(/[\\\/]/);
    if (parts.length > 0) {
      const filename = parts[parts.length - 1];
      const masked = maskFilename(filename);
      parts[parts.length - 1] = masked;
      return parts.join('/');
    }
    return maskFilename(path);
  }

  return path;
}
