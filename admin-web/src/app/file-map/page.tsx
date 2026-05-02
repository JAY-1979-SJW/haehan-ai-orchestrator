'use client';

import { useEffect, useState } from 'react';
import { FileMapReportViewer, FileMapCleanupPlanViewer, FileMapCleanupPreview, FileMapApprovalRequest, FileMapExecutionPackage, FileMapExecuteFlow } from '@/components/file-map';
import { PageShell } from '@/components/ui';

interface ApiResponse {
  ok: boolean;
  report?: any;
  error?: string;
  storage_info?: any;
}

export default function FileMapPage() {
  const [activeTab, setActiveTab] = useState<'report' | 'cleanup' | 'cleanup-preview' | 'approval-request' | 'execution-package' | 'execute-flow'>('report');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchReport = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/file-map/report?mode=reveal_after_auth');
        const json: ApiResponse = await response.json();

        if (json.ok && json.report) {
          // API에서 받은 마스킹된 데이터를 UI용 형식으로 변환
          const report = json.report;
          const files = [
            ...(report.large_files || []),
            ...(report.old_files || []),
            ...(report.suspicious_duplicates || []),
            ...(report.suspicious_temp || []),
          ].slice(0, 10);

          const reportData = {
            title: 'LOCAL-FILE-MAP: 파일 지도 리포트',
            content: `# LOCAL-FILE-MAP: 파일 지도 리포트

**생성 시간**: ${new Date().toLocaleString('ko-KR')}
**마스킹 상태**: ✓ 기본 마스킹 적용

## 스캔 대상

| 항목 | 값 |
|-----|-----|
| **스캔 루트** | ${report.scan_root || '(정보 없음)'} |
| **총 파일 수** | ${report.total_files || 0} 개 |
| **스캔 시간** | ${report.scan_timestamp ? new Date(report.scan_timestamp).toLocaleString('ko-KR') : '(정보 없음)'} |

## 주요 발견사항

- **대용량 파일**: ${report.large_files?.length || 0} 개
- **오래된 파일**: ${report.old_files?.length || 0} 개
- **중복 의심**: ${report.suspicious_duplicates?.length || 0} 개
- **임시 의심**: ${report.suspicious_temp?.length || 0} 개

---

**정책**: 기본 화면은 민감 파일명을 마스킹합니다. 인증 후 일시적으로 원본을 볼 수 있습니다.
**최종 수정**: 2026-05-02`,
            files,
          };

          setData(reportData);
        } else {
          setError(json.error || 'Unknown error');
        }
      } catch (err) {
        console.error('Failed to fetch report:', err);
        setError(err instanceof Error ? err.message : 'Failed to load report');
      } finally {
        setLoading(false);
      }
    };

    fetchReport();
  }, []);

  return (
    <PageShell title="파일 지도" description="로컬 파일 지도 스캔 및 정리 계획">
      <div className="max-w-4xl">
        {/* 탭 네비게이션 */}
        <div className="mb-4 border-b border-gray-200">
          <div className="flex gap-4">
            <button
              onClick={() => setActiveTab('report')}
              className={`px-4 py-2 font-medium transition-colors ${
                activeTab === 'report'
                  ? 'border-b-2 border-blue-600 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              파일 지도 리포트
            </button>
            <button
              onClick={() => setActiveTab('cleanup')}
              className={`px-4 py-2 font-medium transition-colors ${
                activeTab === 'cleanup'
                  ? 'border-b-2 border-blue-600 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              정리 계획표
            </button>
            <button
              onClick={() => setActiveTab('cleanup-preview')}
              className={`px-4 py-2 font-medium transition-colors ${
                activeTab === 'cleanup-preview'
                  ? 'border-b-2 border-blue-600 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              정리 미리보기
            </button>
            <button
              onClick={() => setActiveTab('approval-request')}
              className={`px-4 py-2 font-medium transition-colors ${
                activeTab === 'approval-request'
                  ? 'border-b-2 border-blue-600 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              실행 승인 요청서
            </button>
            <button
              onClick={() => setActiveTab('execution-package')}
              className={`px-4 py-2 font-medium transition-colors ${
                activeTab === 'execution-package'
                  ? 'border-b-2 border-blue-600 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              실행 패키지
            </button>
            <button
              onClick={() => setActiveTab('execute-flow')}
              className={`px-4 py-2 font-medium transition-colors ${
                activeTab === 'execute-flow'
                  ? 'border-b-2 border-blue-600 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              사전검사 · 실행
            </button>
          </div>
        </div>

        {/* 파일 지도 리포트 탭 */}
        {activeTab === 'report' && (
          <>
            {loading && (
              <div className="p-6 text-center text-gray-600">
                <div className="animate-spin inline-block w-5 h-5 border-2 border-gray-300 border-t-blue-500 rounded-full mr-2" />
                데이터를 로드 중입니다...
              </div>
            )}

            {error && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
                <p className="font-semibold mb-1">⚠️ 데이터 로드 실패</p>
                <p>{error}</p>
                <p className="text-xs mt-2 text-gray-600">
                  파일 지도 스캔 데이터가 없습니다. 로컬 에이전트에서 파일 지도 스캔을 실행해주세요.
                </p>
              </div>
            )}

            {!loading && !error && data && (
              <FileMapReportViewer reportData={data} />
            )}

            {!loading && !error && !data && (
              <div className="p-6 text-center text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
                <p>데이터가 없습니다.</p>
              </div>
            )}
          </>
        )}

        {/* 정리 계획표 탭 */}
        {activeTab === 'cleanup' && (
          <FileMapCleanupPlanViewer />
        )}

        {/* 정리 미리보기 탭 */}
        {activeTab === 'cleanup-preview' && (
          <FileMapCleanupPreview />
        )}

        {/* 실행 승인 요청서 탭 */}
        {activeTab === 'approval-request' && (
          <FileMapApprovalRequest />
        )}

        {/* 실행 패키지 탭 */}
        {activeTab === 'execution-package' && (
          <FileMapExecutionPackage />
        )}

        {/* 사전검사 · 실행 탭 */}
        {activeTab === 'execute-flow' && (
          <FileMapExecuteFlow />
        )}
      </div>
    </PageShell>
  );
}
