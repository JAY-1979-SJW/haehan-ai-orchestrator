'use client';

export function ReportPolicyNotice() {
  return (
    <div className="mt-6 p-3 bg-blue-50 rounded border border-blue-200 text-sm text-blue-900">
      <p className="font-semibold mb-1">📋 민감정보 정책</p>
      <ul className="list-disc list-inside text-xs space-y-1">
        <li>기본 화면은 민감 파일명을 마스킹합니다</li>
        <li>인증 후 일시적으로(15분) 원본 파일명을 볼 수 있습니다</li>
        <li>공유/다운로드용 데이터는 항상 마스킹됩니다</li>
        <li>비밀번호나 인증 정보는 저장되지 않습니다</li>
      </ul>
    </div>
  );
}
