'use client';

export function ApprovalPolicyNotice() {
  return (
    <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-900">
      <p className="font-semibold mb-2">🔐 보안 정책</p>
      <ul className="list-disc list-inside space-y-1 text-xs">
        <li>민감문서는 기본 제외되며, 수동으로만 처리 가능</li>
        <li>중복 파일은 자동 삭제하지 않으며, 수동 확인 필요</li>
        <li>이 화면은 요청서만 표시합니다</li>
        <li>실제 파일 이동은 다음 단계에서 별도 승인 필요</li>
      </ul>
    </div>
  );
}
