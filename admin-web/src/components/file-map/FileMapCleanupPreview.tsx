'use client';

import { useState, useEffect } from 'react';
import {
  loadSettings,
  type FileMapMaskingMode,
} from '@/lib/fileMapSettings';

interface PreviewItem {
  current_path: string;
  suggested_path: string;
  category: string;
  risk: 'low' | 'medium' | 'high';
  masked: boolean;
  action_type: 'move_preview';
  file_size_bytes?: number;
  modified_time?: string;
}

interface PreviewData {
  ok: boolean;
  execution_enabled: boolean;
  preview_only: boolean;
  total_items: number;
  mode?: FileMapMaskingMode;
  auth_verified?: boolean;
  masked?: boolean;
  items: PreviewItem[];
  error?: string;
}

function getRiskBadgeColor(risk: 'low' | 'medium' | 'high'): string {
  switch (risk) {
    case 'high':
      return 'bg-red-100 text-red-800';
    case 'medium':
      return 'bg-yellow-100 text-yellow-800';
    case 'low':
      return 'bg-green-100 text-green-800';
  }
}

function getRiskLabel(risk: 'low' | 'medium' | 'high'): string {
  switch (risk) {
    case 'high':
      return '위험(민감)';
    case 'medium':
      return '검토필요(중복)';
    case 'low':
      return '안전';
  }
}

function getCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    archive: '보관',
    documents: '업무문서',
    spreadsheets: '엑셀/정산',
    cad: 'CAD/도면',
    images: '이미지/스캔',
    sensitive: '민감문서',
    duplicates: '중복검토',
    hold: '분류보류',
  };
  return labels[category] || category;
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

export function FileMapCleanupPreview() {
  const [data, setData] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<any>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  useEffect(() => {
    const loaded = loadSettings();
    setSettings(loaded);
  }, []);

  useEffect(() => {
    const fetchPreview = async () => {
      if (!settings) return;

      try {
        setLoading(true);
        const response = await fetch(
          `/api/file-map/cleanup-preview?mode=${settings.maskingMode}`
        );
        const json: PreviewData = await response.json();

        if (json.ok) {
          setData(json);
        } else {
          setError(json.error || 'Unknown error');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load cleanup preview');
      } finally {
        setLoading(false);
      }
    };

    fetchPreview();
  }, [settings]);

  if (loading) {
    return (
      <div className="p-6 text-center text-gray-600">
        <div className="animate-spin inline-block w-5 h-5 border-2 border-gray-300 border-t-blue-500 rounded-full mr-2" />
        미리보기를 로드 중입니다...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
        <p className="font-semibold mb-1">⚠️ 미리보기 로드 실패</p>
        <p>{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-6 text-center text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
        <p>미리보기 데이터가 없습니다.</p>
      </div>
    );
  }

  // 카테고리별 통계
  const categoryCounts = data.items.reduce(
    (acc, item) => {
      acc[item.category] = (acc[item.category] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  // 위험도별 통계
  const riskCounts = data.items.reduce(
    (acc, item) => {
      acc[item.risk] = (acc[item.risk] || 0) + 1;
      return acc;
    },
    { low: 0, medium: 0, high: 0 }
  );

  // 필터링된 항목
  const filteredItems = selectedCategory
    ? data.items.filter((item) => item.category === selectedCategory)
    : data.items;

  return (
    <div className="cleanup-preview space-y-4">
      {/* 안내 문구 */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-900">
        <p className="font-semibold mb-1">🔍 정리 미리보기</p>
        <p>
          이 화면은 <strong>미리보기만 제공</strong>합니다. 실제 파일은 아직 변경되지 않았습니다.
        </p>
      </div>

      {/* 마스킹 상태 */}
      <div className="flex items-center gap-2">
        {data.preview_only && (
          <span className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full font-medium">
            👁️ 미리보기 모드
          </span>
        )}
        {data.masked ? (
          <span className="px-3 py-1 bg-yellow-100 text-yellow-800 text-sm rounded-full font-medium">
            🔒 민감정보 마스킹
          </span>
        ) : (
          <span className="px-3 py-1 bg-green-100 text-green-800 text-sm rounded-full font-medium">
            👁️ 원본 표시
          </span>
        )}
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-blue-600">{data.total_items}</div>
          <div className="text-xs text-gray-600 mt-1">총 파일</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-green-600">{riskCounts.low}</div>
          <div className="text-xs text-gray-600 mt-1">안전</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-yellow-600">{riskCounts.medium}</div>
          <div className="text-xs text-gray-600 mt-1">검토필요</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-red-600">{riskCounts.high}</div>
          <div className="text-xs text-gray-600 mt-1">민감</div>
        </div>
      </div>

      {/* 카테고리 필터 */}
      <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
        <h3 className="font-semibold mb-3 text-sm">카테고리 필터</h3>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedCategory(null)}
            className={`px-3 py-1 text-sm rounded-full transition-colors ${
              selectedCategory === null
                ? 'bg-blue-600 text-white'
                : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-100'
            }`}
          >
            전체 ({data.total_items})
          </button>
          {Object.entries(categoryCounts).map(([cat, count]) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1 text-sm rounded-full transition-colors ${
                selectedCategory === cat
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-100'
              }`}
            >
              {getCategoryLabel(cat)} ({count})
            </button>
          ))}
        </div>
      </div>

      {/* 파일 목록 테이블 */}
      <div className="p-4 bg-white border rounded-lg overflow-x-auto">
        <h3 className="font-semibold mb-3 text-sm">미리보기 항목 ({filteredItems.length}개)</h3>
        {filteredItems.length === 0 ? (
          <p className="text-gray-600 text-sm py-4">선택된 카테고리에 항목이 없습니다.</p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-gray-100 border-b">
                <th className="text-left px-3 py-2 font-medium">현재 경로</th>
                <th className="text-left px-3 py-2 font-medium">제안 경로</th>
                <th className="text-left px-3 py-2 font-medium">카테고리</th>
                <th className="text-left px-3 py-2 font-medium">위험도</th>
                <th className="text-right px-3 py-2 font-medium">크기</th>
                <th className="text-left px-3 py-2 font-medium">수정시간</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((item, idx) => (
                <tr key={idx} className="border-b hover:bg-gray-50">
                  <td className="px-3 py-2 text-xs truncate font-mono text-gray-700 max-w-xs">
                    {item.current_path}
                  </td>
                  <td className="px-3 py-2 text-xs truncate text-blue-600 max-w-xs">
                    {item.suggested_path}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <span className="px-2 py-1 bg-gray-100 text-gray-700 rounded">
                      {getCategoryLabel(item.category)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${getRiskBadgeColor(item.risk)}`}>
                      {getRiskLabel(item.risk)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-right">
                    {formatFileSize(item.file_size_bytes)}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-600">
                    {item.modified_time ? item.modified_time.slice(0, 10) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 안내 문구 */}
      <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-900">
        <p className="font-semibold mb-2">⚠️ 주의사항</p>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li>이 화면은 <strong>미리보기만 제공</strong>합니다</li>
          <li>표시된 파일은 아직 <strong>변경되지 않았습니다</strong></li>
          <li>위험도 &quot;민감&quot;은 보안이 필요한 파일입니다</li>
          <li>위험도 &quot;검토필요&quot;는 중복 파일로 확인이 필요합니다</li>
          <li>실제 이동은 <strong>수동으로만 가능</strong>합니다</li>
        </ul>
      </div>
    </div>
  );
}
