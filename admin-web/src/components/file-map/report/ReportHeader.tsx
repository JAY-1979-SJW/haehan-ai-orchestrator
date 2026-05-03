'use client';

import { useState } from 'react';

interface ReportHeaderProps {
  isMasked: boolean;
  isAuthVerified: boolean;
  timeRemaining: number | null;
  isAuthLoading: boolean;
  onRevealToggle: () => void;
  onRemask: () => void;
  onMockAuth: () => void;
}

export function ReportHeader({
  isMasked,
  isAuthVerified,
  timeRemaining,
  isAuthLoading,
  onRevealToggle,
  onRemask,
  onMockAuth,
}: ReportHeaderProps) {
  const formatTimeRemaining = (ms: number | null): string => {
    if (!ms || ms <= 0) return '만료';
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  return (
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
            isAuthVerified
              ? 'bg-blue-100 text-blue-800'
              : 'bg-gray-100 text-gray-800'
          }`}
        >
          {isAuthVerified ? '✓ 인증됨' : '○ 미인증'}
        </span>
      </div>

      {/* 제어 버튼 */}
      <div className="flex gap-2">
        {/* 원본보기 버튼 */}
        <button
          onClick={onRevealToggle}
          disabled={!isAuthVerified}
          className={`px-4 py-2 rounded font-medium transition-colors ${
            isAuthVerified
              ? isMasked
                ? 'bg-blue-500 hover:bg-blue-600 text-white cursor-pointer'
                : 'bg-orange-500 hover:bg-orange-600 text-white cursor-pointer'
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
          }`}
        >
          {isMasked ? '원본보기' : '마스킹'}
        </button>

        {/* 다시 마스킹 버튼 */}
        {isAuthVerified && (
          <button
            onClick={onRemask}
            className="px-4 py-2 rounded font-medium bg-red-500 hover:bg-red-600 text-white transition-colors"
          >
            다시 마스킹
          </button>
        )}

        {/* Mock 인증 버튼 (개발/테스트용) */}
        {!isAuthVerified && (
          <button
            onClick={onMockAuth}
            disabled={isAuthLoading}
            className="px-4 py-2 rounded font-medium bg-purple-500 hover:bg-purple-600 text-white transition-colors text-sm disabled:opacity-50"
          >
            {isAuthLoading ? '인증 중...' : '테스트: 인증하기 (Mock)'}
          </button>
        )}
      </div>
    </div>
  );
}
