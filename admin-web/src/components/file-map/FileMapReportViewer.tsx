'use client';

import { useState, useEffect } from 'react';
import {
  loadSettings,
  saveSettings,
  getModeDescription,
  getModeIcon,
  shouldRevealSensitiveNames,
  type FileMapMaskingMode,
} from '@/lib/fileMapSettings';

interface RevealSessionState {
  auth_verified: boolean;
  reveal_sensitive_names: boolean;
  expires_at: number | null;
}

interface FileObject {
  name: string;
  path: string;
  size: number;
  [key: string]: any;
}

export interface FileMapReportViewerProps {
  reportData?: {
    title: string;
    content: string;
    files: FileObject[];
    [key: string]: any;
  };
  revealData?: {
    title?: string;
    content?: string;
    files?: FileObject[];
    [key: string]: any;
  };
}

export function FileMapReportViewer({
  reportData,
  revealData
}: FileMapReportViewerProps) {
  const [session, setSession] = useState<RevealSessionState>({
    auth_verified: false,
    reveal_sensitive_names: false,
    expires_at: null,
  });

  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  const [revealReportData, setRevealReportData] = useState<any>(null);
  const [settings, setSettings] = useState<any>(null);
  const [showSettings, setShowSettings] = useState(false);

  // 자동 재마스킹 타이머 (15분)
  const REVEAL_DURATION_MS = 15 * 60 * 1000;

  // 설정 로드
  useEffect(() => {
    const loaded = loadSettings();
    setSettings(loaded);
  }, []);

  // 시간 남은 것 업데이트
  useEffect(() => {
    if (!session.auth_verified || !session.expires_at) {
      setTimeRemaining(null);
      return;
    }

    const updateTimer = () => {
      const now = Date.now();
      const remaining = Math.max(0, (session.expires_at ?? 0) - now);
      setTimeRemaining(remaining);

      if (remaining === 0) {
        // 시간 만료 시 자동 재마스킹
        handleRemask();
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [session.auth_verified, session.expires_at]);

  const handleMockAuth = async () => {
    try {
      setIsAuthLoading(true);
      const response = await fetch('/api/file-map/auth/mock-verify', {
        method: 'POST',
      });
      const data = await response.json();

      if (data.ok) {
        setSession({
          auth_verified: true,
          reveal_sensitive_names: true,
          expires_at: new Date(data.expires_at).getTime(),
        });
      }
    } catch (error) {
      console.error('Auth failed:', error);
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleRevealToggle = async () => {
    if (!settings) return;

    // 설정에 따라 처리
    switch (settings.maskingMode) {
      case 'mask_always':
        // 항상 마스킹 모드: 불가능
        return;

      case 'reveal_after_auth': {
        // 인증 필요
        if (!session.auth_verified) {
          return;
        }
        // 이미 reveal 중이면 마스킹으로
        if (session.reveal_sensitive_names) {
          setSession((prev) => ({
            ...prev,
            reveal_sensitive_names: false,
          }));
          return;
        }
        // mode별 API 호출
        try {
          const response = await fetch('/api/file-map/report?mode=reveal_after_auth');
          const data = await response.json();
          if (data.ok && data.report) {
            setRevealReportData(data.report);
            setSession((prev) => ({
              ...prev,
              reveal_sensitive_names: true,
            }));
          }
        } catch (error) {
          console.error('Reveal error:', error);
        }
        break;
      }

      case 'reveal_on_trusted_device': {
        // 기기 신뢰 모드: 토글만 함
        setSession((prev) => ({
          ...prev,
          reveal_sensitive_names: !prev.reveal_sensitive_names,
        }));
        break;
      }

      case 'reveal_for_export_with_warning':
        // 외부 전송 원본 모드 (현재 단계에서는 구현 보류)
        break;
    }
  };

  const handleSaveSetting = (mode: FileMapMaskingMode) => {
    const newSettings = { ...settings, maskingMode: mode };
    setSettings(newSettings);
    saveSettings(newSettings);
  };

  const handleRemask = async () => {
    try {
      await fetch('/api/file-map/auth/clear', {
        method: 'POST',
      });
    } catch (error) {
      console.error('Clear failed:', error);
    }

    setSession({
      auth_verified: false,
      reveal_sensitive_names: false,
      expires_at: null,
    });
  };

  const formatTimeRemaining = (ms: number | null): string => {
    if (!ms || ms <= 0) return '만료';
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  // 설정과 인증 상태를 바탕으로 마스킹 여부 결정
  const isMasked = settings
    ? !shouldRevealSensitiveNames(settings.maskingMode, session.auth_verified)
    : true;

  return (
    <div className="file-map-report-viewer p-4 border rounded-lg bg-white">
      {/* 헤더 */}
      <div className="mb-4">
        <h2 className="text-2xl font-bold mb-2">파일 지도 리포트</h2>

        {/* 마스킹 상태 배지 */}
        <div className="flex items-center gap-2 mb-4">
          {isMasked ? (
            <span className="px-3 py-1 bg-yellow-100 text-yellow-800 text-sm rounded-full font-medium">
              🔒 민감정보 마스킹 중
            </span>
          ) : (
            <span className="px-3 py-1 bg-green-100 text-green-800 text-sm rounded-full font-medium">
              👁️ 원본 표시 중 ({formatTimeRemaining(timeRemaining)})
            </span>
          )}

          {/* 인증 상태 배지 */}
          <span
            className={`px-3 py-1 text-sm rounded-full font-medium ${
              session.auth_verified
                ? 'bg-blue-100 text-blue-800'
                : 'bg-gray-100 text-gray-800'
            }`}
          >
            {session.auth_verified ? '✓ 인증됨' : '○ 미인증'}
          </span>
        </div>

        {/* 제어 버튼 */}
        <div className="flex gap-2">
          {/* 원본보기 버튼 */}
          <button
            onClick={handleRevealToggle}
            disabled={!session.auth_verified}
            className={`px-4 py-2 rounded font-medium transition-colors ${
              session.auth_verified
                ? isMasked
                  ? 'bg-blue-500 hover:bg-blue-600 text-white cursor-pointer'
                  : 'bg-orange-500 hover:bg-orange-600 text-white cursor-pointer'
                : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            }`}
          >
            {isMasked ? '원본보기' : '마스킹'}
          </button>

          {/* 다시 마스킹 버튼 */}
          {session.auth_verified && (
            <button
              onClick={handleRemask}
              className="px-4 py-2 rounded font-medium bg-red-500 hover:bg-red-600 text-white transition-colors"
            >
              다시 마스킹
            </button>
          )}

          {/* Mock 인증 버튼 (개발/테스트용) */}
          {!session.auth_verified && (
            <button
              onClick={handleMockAuth}
              className="px-4 py-2 rounded font-medium bg-purple-500 hover:bg-purple-600 text-white transition-colors text-sm"
            >
              테스트: 인증하기 (Mock)
            </button>
          )}
        </div>
      </div>

      <hr className="my-4" />

      {/* 리포트 콘텐츠 */}
      {reportData ? (
        <div className="report-content">
          <h3 className="text-xl font-semibold mb-2">{reportData.title}</h3>

          {/* 마크다운 콘텐츠 */}
          <div className="prose max-w-none mb-4 text-sm whitespace-pre-wrap">
            {reportData.content}
          </div>

          {/* 파일 목록 샘플 */}
          {(revealReportData?.large_files || reportData.files)?.length > 0 && (
            <div className="mt-4">
              <h4 className="font-semibold mb-2">스캔된 파일 샘플</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="bg-gray-100 border-b">
                      <th className="text-left px-3 py-2 font-medium">파일명</th>
                      <th className="text-left px-3 py-2 font-medium">경로</th>
                      <th className="text-right px-3 py-2 font-medium">크기</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(() => {
                      let files: FileObject[] = [];
                      if (session.reveal_sensitive_names && revealReportData?.large_files) {
                        files = [
                          ...(revealReportData.large_files || []),
                          ...(revealReportData.old_files || []),
                          ...(revealReportData.suspicious_duplicates || []),
                          ...(revealReportData.suspicious_temp || []),
                        ].slice(0, 10);
                      } else {
                        files = reportData.files || [];
                      }
                      return files.map((file, idx) => (
                      <tr
                        key={idx}
                        className="border-b hover:bg-gray-50"
                      >
                        <td className="px-3 py-2 font-mono text-xs">
                          {file.name}
                        </td>
                        <td className="px-3 py-2 font-mono text-xs text-gray-600">
                          {file.path}
                        </td>
                        <td className="text-right px-3 py-2 text-xs">
                          {(file.size / 1024).toFixed(1)} KB
                        </td>
                      </tr>
                      ));
                    })()}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-8 text-gray-500">
          <p>로드할 리포트가 없습니다.</p>
        </div>
      )}

      {/* 정책 안내 */}
      <div className="mt-6 p-3 bg-blue-50 rounded border border-blue-200 text-sm text-blue-900">
        <p className="font-semibold mb-1">📋 민감정보 정책</p>
        <ul className="list-disc list-inside text-xs space-y-1">
          <li>기본 화면은 민감 파일명을 마스킹합니다</li>
          <li>인증 후 일시적으로(15분) 원본 파일명을 볼 수 있습니다</li>
          <li>공유/다운로드용 데이터는 항상 마스킹됩니다</li>
          <li>비밀번호나 인증 정보는 저장되지 않습니다</li>
        </ul>
      </div>

      {/* 마스킹 설정 */}
      {settings && (
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
                  onClick={() => handleSaveSetting(mode)}
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
      )}
    </div>
  );
}
