'use client';

import { useState } from 'react';
import {
  getModeDescription,
  getModeIcon,
  type FileMapMaskingMode,
} from '@/lib/fileMapSettings';

interface ReportMaskingSettingsProps {
  settings?: {
    maskingMode: FileMapMaskingMode;
    [key: string]: any;
  };
  onSaveSetting: (mode: FileMapMaskingMode) => void;
}

export function ReportMaskingSettings({
  settings,
  onSaveSetting,
}: ReportMaskingSettingsProps) {
  const [showSettings, setShowSettings] = useState(false);

  if (!settings) {
    return null;
  }

  return (
    <div className="mt-6 p-4 bg-gray-50 rounded border border-gray-200">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-sm">⚙️ 민감 파일명 표시 설정</h3>
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="text-xs text-blue-600 hover:underline"
        >
          {showSettings ? '닫기' : '설정 변경'}
        </button>
      </div>

      {/* 현재 설정 */}
      <div className="mb-3 text-xs text-gray-600">
        <span className="inline-block px-2 py-1 bg-white rounded border border-gray-300">
          {getModeIcon(settings.maskingMode)} {
            settings.maskingMode === 'mask_always'
              ? '항상 마스킹'
              : settings.maskingMode === 'reveal_after_auth'
              ? '인증 후 원본 표시'
              : settings.maskingMode === 'reveal_on_trusted_device'
              ? '이 PC에서는 원본 표시'
              : '공유/외부전송도 원본 허용'
          }
        </span>
      </div>

      {/* 설정 옵션 */}
      {showSettings && (
        <div className="space-y-2 text-xs">
          {(
            [
              'mask_always',
              'reveal_after_auth',
              'reveal_on_trusted_device',
            ] as const
          ).map((mode) => (
            <button
              key={mode}
              onClick={() => onSaveSetting(mode)}
              className={`w-full text-left px-3 py-2 rounded transition-colors ${
                settings.maskingMode === mode
                  ? 'bg-blue-100 border border-blue-300'
                  : 'bg-white border border-gray-300 hover:bg-gray-100'
              }`}
            >
              <span className="font-medium">{getModeIcon(mode)} {
                mode === 'mask_always'
                  ? '항상 마스킹'
                  : mode === 'reveal_after_auth'
                  ? '인증 후 원본 표시 (추천)'
                  : '이 PC에서는 원본 표시'
              }</span>
              <p className="text-gray-600 mt-1">{getModeDescription(mode)}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
