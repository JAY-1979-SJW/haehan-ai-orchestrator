'use client';

interface FileObject {
  name: string;
  path: string;
  size: number;
  [key: string]: any;
}

interface ReportContentProps {
  reportData?: {
    title: string;
    content: string;
    files: FileObject[];
    [key: string]: any;
  };
  revealReportData?: {
    large_files?: FileObject[];
    old_files?: FileObject[];
    suspicious_duplicates?: FileObject[];
    suspicious_temp?: FileObject[];
    [key: string]: any;
  };
  isRevealing: boolean;
}

export function ReportContent({
  reportData,
  revealReportData,
  isRevealing,
}: ReportContentProps) {
  if (!reportData) {
    return (
      <div className="text-center py-8 text-gray-500">
        <p>로드할 리포트가 없습니다.</p>
      </div>
    );
  }

  return (
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
                  if (isRevealing && revealReportData?.large_files) {
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
  );
}
