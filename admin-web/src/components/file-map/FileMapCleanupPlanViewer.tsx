'use client';

import { useState, useEffect } from 'react';
import {
  loadSettings,
  type FileMapMaskingMode,
} from '@/lib/fileMapSettings';

interface CleanupCategory {
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

interface CleanupPlanData {
  ok: boolean;
  masked: boolean;
  mode?: FileMapMaskingMode;
  execution_enabled: boolean;
  summary?: {
    total_files: number;
    archive_candidates: number;
    document_candidates: number;
    spreadsheet_candidates: number;
    cad_candidates: number;
    image_candidates: number;
    sensitive_candidates: number;
    duplicate_review_candidates: number;
    hold_candidates: number;
  };
  suggested_structure?: string;
  categories?: Record<string, CleanupCategory>;
  error?: string;
}

export function FileMapCleanupPlanViewer() {
  const [data, setData] = useState<CleanupPlanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<any>(null);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  // 설정 로드
  useEffect(() => {
    const loaded = loadSettings();
    setSettings(loaded);
  }, []);

  // 정리 계획 로드
  useEffect(() => {
    const fetchPlan = async () => {
      if (!settings) return;

      try {
        setLoading(true);
        const response = await fetch(
          `/api/file-map/cleanup-plan?mode=${settings.maskingMode}`
        );
        const json: CleanupPlanData = await response.json();

        if (json.ok) {
          setData(json);
        } else {
          setError(json.error || 'Unknown error');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load cleanup plan');
      } finally {
        setLoading(false);
      }
    };

    fetchPlan();
  }, [settings]);

  if (loading) {
    return (
      <div className="p-6 text-center text-gray-600">
        <div className="animate-spin inline-block w-5 h-5 border-2 border-gray-300 border-t-blue-500 rounded-full mr-2" />
        정리 계획을 로드 중입니다...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
        <p className="font-semibold mb-1">⚠️ 정리 계획 로드 실패</p>
        <p>{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-6 text-center text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
        <p>정리 계획이 없습니다.</p>
      </div>
    );
  }

  const summary = data.summary || {
    total_files: 0,
    archive_candidates: 0,
    document_candidates: 0,
    spreadsheet_candidates: 0,
    cad_candidates: 0,
    image_candidates: 0,
    sensitive_candidates: 0,
    duplicate_review_candidates: 0,
    hold_candidates: 0,
  };

  return (
    <div className="cleanup-plan-viewer space-y-4">
      {/* 안내 문구 */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-900">
        <p className="font-semibold mb-1">📋 정리 계획표</p>
        <p>
          이 화면은 <strong>정리 계획표</strong>입니다. 실제 파일 이동, 삭제, 이름변경은 수행하지 않습니다.
        </p>
      </div>

      {/* 마스킹 상태 */}
      <div className="flex items-center gap-2">
        {data.masked ? (
          <span className="px-3 py-1 bg-yellow-100 text-yellow-800 text-sm rounded-full font-medium">
            🔒 민감정보 마스킹 중
          </span>
        ) : (
          <span className="px-3 py-1 bg-green-100 text-green-800 text-sm rounded-full font-medium">
            👁️ 원본 표시 중
          </span>
        )}
        <span className="text-xs text-gray-600">
          (실행 비활성화됨)
        </span>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-blue-600">{summary.total_files}</div>
          <div className="text-xs text-gray-600 mt-1">총 파일</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-orange-600">{summary.archive_candidates}</div>
          <div className="text-xs text-gray-600 mt-1">보관 후보</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-purple-600">{summary.document_candidates}</div>
          <div className="text-xs text-gray-600 mt-1">업무문서</div>
        </div>
        <div className="p-3 bg-white border rounded-lg">
          <div className="text-2xl font-bold text-red-600">{summary.sensitive_candidates}</div>
          <div className="text-xs text-gray-600 mt-1">민감문서</div>
        </div>
      </div>

      {/* 제안 폴더 구조 */}
      <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
        <h3 className="font-semibold mb-3">제안 폴더 구조</h3>
        <pre className="text-xs overflow-x-auto bg-white p-3 rounded border text-gray-700">
          {data.suggested_structure}
        </pre>
        <p className="text-xs text-gray-600 mt-2">
          ⚠️ 실제 폴더는 생성되지 않습니다. 이것은 제안입니다.
        </p>
      </div>

      {/* 카테고리별 상세 */}
      {data.categories && Object.entries(data.categories).map(([key, category]) => (
        <div key={key} className="border rounded-lg overflow-hidden">
          <button
            onClick={() => setExpandedCategory(expandedCategory === key ? null : key)}
            className="w-full px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left font-medium text-sm flex items-center justify-between"
          >
            <span>
              {category.name} ({category.count}개)
            </span>
            <span>{expandedCategory === key ? '▼' : '▶'}</span>
          </button>

          {expandedCategory === key && (
            <div className="p-4 bg-white">
              <p className="text-sm text-gray-700 mb-3">{category.reason}</p>
              <p className="text-xs text-gray-600 mb-3">
                제안 경로: <code className="bg-gray-100 px-2 py-1 rounded">{category.suggested_path}</code>
              </p>

              {category.samples.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold mb-2">샘플 파일 (상위 {category.samples.length}개)</h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="bg-gray-100 border-b">
                          <th className="text-left px-2 py-2 font-medium">파일명</th>
                          <th className="text-left px-2 py-2 font-medium">경로</th>
                          <th className="text-right px-2 py-2 font-medium">크기</th>
                          <th className="text-left px-2 py-2 font-medium">수정시간</th>
                        </tr>
                      </thead>
                      <tbody>
                        {category.samples.map((sample, idx) => (
                          <tr key={idx} className="border-b hover:bg-gray-50">
                            <td className="px-2 py-1 font-mono text-xs truncate">
                              {sample.masked_name}
                            </td>
                            <td className="px-2 py-1 text-gray-600 text-xs truncate">
                              ...{sample.file_path.slice(-30)}
                            </td>
                            <td className="text-right px-2 py-1 text-xs">
                              {sample.size_bytes > 0 ? `${(sample.size_bytes / 1024 / 1024).toFixed(1)}MB` : '-'}
                            </td>
                            <td className="px-2 py-1 text-xs">
                              {sample.modified_time.slice(0, 10)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      {/* 실행 불가능 안내 */}
      <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-900">
        <p className="font-semibold mb-1">ℹ️ 실행 방법</p>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li>이 화면은 <strong>계획만 제공</strong>합니다</li>
          <li>실제 파일 이동은 <strong>수동으로만 가능</strong>합니다</li>
          <li>중복 파일은 반드시 <strong>확인 후</strong> 삭제하세요</li>
          <li>민감문서는 <strong>보안 저장소</strong>로 이동을 권장합니다</li>
        </ul>
      </div>
    </div>
  );
}
