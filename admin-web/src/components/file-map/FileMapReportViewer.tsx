'use client';

import { useState, useEffect } from 'react';

interface RevealSessionState {
  auth_verified: boolean;
  reveal_sensitive_names: boolean;
  expires_at: number | null;
}

export interface FileMapReportViewerProps {
  reportData?: {
    title: string;
    content: string;
    files: Array<{
      name: string;
      path: string;
      size: number;
    }>;
  };
}

export function FileMapReportViewer({ reportData }: FileMapReportViewerProps) {
  const [session, setSession] = useState<RevealSessionState>({
    auth_verified: false,
    reveal_sensitive_names: false,
    expires_at: null,
  });

  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);

  // 자동 재마스킹 타이머 (15분)
  const REVEAL_DURATION_MS = 15 * 60 * 1000;

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
        setSession((prev) => ({
          ...prev,
          reveal_sensitive_names: false,
          auth_verified: false,
          expires_at: null,
        }));
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [session.auth_verified, session.expires_at]);

  const handleMockAuth = () => {
    const now = Date.now();
    setSession({
      auth_verified: true,
      reveal_sensitive_names: true,
      expires_at: now + REVEAL_DURATION_MS,
    });
  };

  const handleRevealToggle = () => {
    if (!session.auth_verified) {
      return; // 인증 없으면 원본보기 비활성화
    }

    setSession((prev) => ({
      ...prev,
      reveal_sensitive_names: !prev.reveal_sensitive_names,
    }));
  };

  const handleRemask = () => {
    setSession((prev) => ({
      ...prev,
      reveal_sensitive_names: false,
      auth_verified: false,
      expires_at: null,
    }));
  };

  const formatTimeRemaining = (ms: number | null): string => {
    if (!ms || ms <= 0) return '만료';
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const isMasked =
    !session.auth_verified || !session.reveal_sensitive_names;

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
          {reportData.files && reportData.files.length > 0 && (
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
                    {reportData.files.map((file, idx) => (
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
                    ))}
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
    </div>
  );
}
