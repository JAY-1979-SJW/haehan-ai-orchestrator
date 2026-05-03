'use client';

export function ExecutionSecurityPolicy() {
  return (
    <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-900">
      <p className="font-semibold mb-2">🔐 보안 및 정책</p>
      <ul className="list-disc list-inside space-y-1 text-xs">
        <li>민감문서, 중복 검토 후보, 고위험 파일은 기본 실행 패키지에서 제외됩니다</li>
        <li>이 화면은 패키지 생성 단계만 제공합니다</li>
        <li>삭제 작업은 패키지에 포함되지 않습니다</li>
        <li>실제 파일 이동은 별도 최종 승인 단계에서만 가능합니다</li>
      </ul>
    </div>
  );
}
