'use client';

interface ApprovalHeaderProps {
  requestId: string;
}

export function ApprovalHeader({ requestId }: ApprovalHeaderProps) {
  return (
    <>
      {/* 안내 문구 */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-900">
        <p className="font-semibold mb-2">📋 실행 승인 요청서</p>
        <p className="mb-2">
          이 화면은 <strong>실행 승인 요청서</strong>입니다. 실제 파일은 아직 변경되지 않았습니다.
        </p>
        <p>민감문서와 중복 검토 후보는 기본 실행 대상에서 제외됩니다.</p>
      </div>

      {/* 요청 ID 및 상태 */}
      <div className="p-4 bg-white border rounded-lg">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-gray-600">요청 ID</span>
          <code className="text-xs bg-gray-100 px-2 py-1 rounded font-mono">
            {requestId}
          </code>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full font-medium">
            📋 요청 검토 중
          </span>
          <span className="px-3 py-1 bg-gray-100 text-gray-800 text-sm rounded-full font-medium">
            🔒 실행 비활성화
          </span>
        </div>
      </div>
    </>
  );
}
