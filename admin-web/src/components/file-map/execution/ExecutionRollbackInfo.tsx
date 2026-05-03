'use client';

export function ExecutionRollbackInfo() {
  return (
    <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
      <h3 className="font-semibold text-sm mb-2">💾 롤백 참고정보</h3>
      <ul className="list-disc list-inside space-y-1 text-xs text-gray-700">
        <li>모든 파일 이동 작업은 기록되며, 원본 경로 정보가 보존됩니다</li>
        <li>실행 후 문제가 발생한 경우 원본 경로로 복원 가능합니다</li>
        <li>이동된 파일의 메타데이터(수정 시간 등)는 유지됩니다</li>
        <li>중복/삭제 작업은 포함되지 않습니다</li>
      </ul>
    </div>
  );
}
