'use client';

import { useState, useEffect } from 'react';
import { loadRollbackManifest, formatRollbackInfo, type RollbackManifest } from '@/lib/fileMapRollback';
import { type ExecuteMoveResult } from '@/lib/fileMapExecutor';

interface FileMapExecuteResultProps {
  result: ExecuteMoveResult;
}

export function FileMapExecuteResult({ result }: FileMapExecuteResultProps) {
  const [manifest, setManifest] = useState<RollbackManifest | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (result.ok && result.runId) {
      setLoading(true);
      loadRollbackManifest(result.runId).then((m) => {
        setManifest(m);
        setLoading(false);
      });
    }
  }, [result]);

  if (!result.ok) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
        <p className="font-semibold mb-2">실행 실패</p>
        <p>{result.error}</p>
      </div>
    );
  }

  const getResultColor = (count: number) => (count > 0 ? 'text-green-600' : 'text-gray-400');

  return (
    <div className="space-y-6">
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <p className="text-sm text-blue-800">
          ✓ 실행이 완료되었습니다. 이동된 파일을 확인하세요.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="p-4 bg-green-50 rounded-lg border border-green-200">
          <div className={`text-2xl font-bold ${getResultColor(result.successCount || 0)}`}>
            {result.successCount || 0}
          </div>
          <div className="text-sm text-green-800">성공</div>
        </div>
        <div className="p-4 bg-red-50 rounded-lg border border-red-200">
          <div className={`text-2xl font-bold ${getResultColor(result.failedCount || 0)}`}>
            {result.failedCount || 0}
          </div>
          <div className="text-sm text-red-800">실패</div>
        </div>
        <div className="p-4 bg-yellow-50 rounded-lg border border-yellow-200">
          <div className={`text-2xl font-bold ${getResultColor(result.conflictCount || 0)}`}>
            {result.conflictCount || 0}
          </div>
          <div className="text-sm text-yellow-800">충돌</div>
        </div>
        <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
          <div className={`text-2xl font-bold ${getResultColor(result.skippedCount || 0)}`}>
            {result.skippedCount || 0}
          </div>
          <div className="text-sm text-gray-800">스킵</div>
        </div>
      </div>

      {result.succeeded && result.succeeded.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-semibold text-sm">성공한 파일</h4>
          <div className="max-h-48 overflow-y-auto border border-green-200 rounded-lg bg-green-50">
            <div className="divide-y">
              {result.succeeded.slice(0, 10).map((item) => (
                <div key={item.operationId} className="p-3 text-sm text-green-800">
                  <div className="font-mono text-xs truncate">
                    {item.sourcePath.split('\\').pop()}
                  </div>
                  <div className="text-xs opacity-75 mt-1">
                    {(item.fileSizeBytes / 1024 / 1024).toFixed(2)} MB
                  </div>
                </div>
              ))}
            </div>
          </div>
          {result.succeeded.length > 10 && (
            <p className="text-xs text-green-600 text-center">
              외 {result.succeeded.length - 10}개 파일...
            </p>
          )}
        </div>
      )}

      {result.failed && result.failed.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-semibold text-sm">실패한 파일</h4>
          <div className="max-h-48 overflow-y-auto border border-red-200 rounded-lg bg-red-50">
            <div className="divide-y">
              {result.failed.map((item) => (
                <div key={item.operationId} className="p-3 text-sm text-red-800">
                  <div className="font-mono text-xs truncate">
                    {item.sourcePath.split('\\').pop()}
                  </div>
                  <div className="text-xs opacity-75 mt-1">{item.error}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {manifest && (
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm">
          <pre className="whitespace-pre-wrap text-xs text-blue-800 font-mono">
            {formatRollbackInfo(manifest)}
          </pre>
        </div>
      )}

      {loading && (
        <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg text-center text-sm text-gray-600">
          롤백 정보를 로드 중...
        </div>
      )}
    </div>
  );
}
