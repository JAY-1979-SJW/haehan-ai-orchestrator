'use client';

interface ExecutionHeaderProps {
  packageId: string;
}

export function ExecutionHeader({ packageId }: ExecutionHeaderProps) {
  return (
    <>
      {/* 안내 문구 */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-900">
        <p className="font-semibold mb-2">📦 실행 패키지 생성</p>
        <p className="mb-2">
          이 화면은 <strong>실행 패키지 생성 단계</strong>입니다. 아직 실제 파일 이동, 삭제, 이름변경, 폴더 생성은 수행하지 않습니다.
        </p>
        <p>민감문서, 중복 검토 후보, 고위험 파일은 기본 실행 패키지에서 제외됩니다.</p>
      </div>

      {/* 패키지 정보 */}
      <div className="p-4 bg-white border rounded-lg">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="font-medium text-sm">패키지 ID</div>
            <code className="text-xs bg-gray-100 px-2 py-1 rounded font-mono">
              {packageId}
            </code>
          </div>
          <div className="flex items-center gap-2">
            <span className="px-3 py-1 bg-purple-100 text-purple-800 text-sm rounded-full font-medium">
              📦 패키지 준비
            </span>
            <span className="px-3 py-1 bg-gray-100 text-gray-800 text-sm rounded-full font-medium">
              🔒 실행 비활성화
            </span>
          </div>
        </div>
      </div>
    </>
  );
}
