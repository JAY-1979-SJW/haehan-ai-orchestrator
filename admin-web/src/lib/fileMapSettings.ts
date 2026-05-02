/**
 * 파일 지도 마스킹 설정
 * 사용자가 민감 파일명 표시 정책을 제어할 수 있도록 함
 */

/**
 * 마스킹 모드
 * - mask_always: 항상 마스킹
 * - reveal_after_auth: 인증 후 원본 표시 (기본, 15분 제한)
 * - reveal_on_trusted_device: 로컬 화면 기본 원본 표시
 * - reveal_for_export_with_warning: 외부 전송도 원본 허용 (경고 필수)
 */
export type FileMapMaskingMode =
  | 'mask_always'
  | 'reveal_after_auth'
  | 'reveal_on_trusted_device'
  | 'reveal_for_export_with_warning';

export interface FileMapSettings {
  maskingMode: FileMapMaskingMode;
  showWarning: boolean;
}

const DEFAULT_SETTINGS: FileMapSettings = {
  maskingMode: 'reveal_after_auth',
  showWarning: true,
};

const STORAGE_KEY = 'file_map_settings';

/**
 * 브라우저 설정 (로컬 저장 가능)
 * 주의: 인증값이나 원본 파일명은 저장하지 않음
 */
export function loadSettings(): FileMapSettings {
  if (typeof window === 'undefined') {
    return DEFAULT_SETTINGS;
  }

  try {
    const stored = localStorage?.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      // 검증: 유효한 mode인지 확인
      if (
        parsed.maskingMode &&
        [
          'mask_always',
          'reveal_after_auth',
          'reveal_on_trusted_device',
          'reveal_for_export_with_warning',
        ].includes(parsed.maskingMode)
      ) {
        return parsed as FileMapSettings;
      }
    }
  } catch (error) {
    console.error('Failed to load settings:', error);
  }

  return DEFAULT_SETTINGS;
}

export function saveSettings(settings: FileMapSettings): void {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    localStorage?.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (error) {
    console.error('Failed to save settings:', error);
  }
}

/**
 * 설정별 정책 설명
 */
export function getModeDescription(mode: FileMapMaskingMode): string {
  switch (mode) {
    case 'mask_always':
      return '항상 민감 파일명을 마스킹합니다. 가장 안전합니다.';
    case 'reveal_after_auth':
      return '본인 인증 후 15분 동안 원본 파일명을 볼 수 있습니다. 추천됨.';
    case 'reveal_on_trusted_device':
      return '이 PC에서는 기본적으로 원본 파일명을 표시합니다. 공유/다운로드는 여전히 마스킹.';
    case 'reveal_for_export_with_warning':
      return '⚠️ 공유/다운로드에도 원본을 포함할 수 있습니다. 매우 주의가 필요합니다.';
    default:
      return '';
  }
}

/**
 * 설정별 아이콘
 */
export function getModeIcon(mode: FileMapMaskingMode): string {
  switch (mode) {
    case 'mask_always':
      return '🔒';
    case 'reveal_after_auth':
      return '✓';
    case 'reveal_on_trusted_device':
      return '✓✓';
    case 'reveal_for_export_with_warning':
      return '⚠️';
    default:
      return '';
  }
}

/**
 * 설정과 인증 상태를 바탕으로 원본 표시 여부 결정
 */
export function shouldRevealSensitiveNames(
  mode: FileMapMaskingMode,
  isAuthVerified: boolean
): boolean {
  switch (mode) {
    case 'mask_always':
      return false;
    case 'reveal_after_auth':
      return isAuthVerified;
    case 'reveal_on_trusted_device':
      return true;
    case 'reveal_for_export_with_warning':
      return true;
    default:
      return false;
  }
}

/**
 * 공유/다운로드/외부 전송용 데이터는 항상 안전하게 마스킹
 */
export function shouldAlwaysMaskForExport(
  mode: FileMapMaskingMode
): boolean {
  return mode !== 'reveal_for_export_with_warning';
}
