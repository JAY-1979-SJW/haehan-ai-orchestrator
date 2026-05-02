'use client';

import { useState } from 'react';
import { FileMapPreflight } from './FileMapPreflight';
import { FileMapExecute } from './FileMapExecute';
import { FileMapExecuteResult } from './FileMapExecuteResult';
import { FileMapAuditLog } from './FileMapAuditLog';
import { type ExecuteMoveResult } from '@/lib/fileMapExecutor';

type FlowStep = 'preflight' | 'execute' | 'result' | 'audit';

interface PreflightReport {
  preflight_id: string;
  total: number;
  ok_count: number;
  conflict_count: number;
  skipped_count: number;
  blocked_count: number;
  items: Array<{
    operation_id: string;
    source_path: string;
    target_path: string;
    category: string;
    status: string;
    reason: string;
  }>;
}

interface FileMapExecuteFlowProps {
  plans?: Array<{
    operation_id: string;
    path: string;
    category: string;
    file_size_bytes: number;
    file_name: string;
  }>;
}

export function FileMapExecuteFlow({ plans = [] }: FileMapExecuteFlowProps) {
  const [step, setStep] = useState<FlowStep>('preflight');
  const [preflight, setPreflight] = useState<PreflightReport | null>(null);
  const [result, setResult] = useState<ExecuteMoveResult | null>(null);

  const handlePreflightComplete = (report: PreflightReport) => {
    setPreflight(report);
    setStep('execute');
  };

  const handleExecuteComplete = (executeResult: ExecuteMoveResult) => {
    setResult(executeResult);
    setStep('result');
  };

  const getStepColor = (stepName: FlowStep) => {
    if (stepName === step) return 'border-blue-600 bg-blue-50 text-blue-900';
    if (
      (stepName === 'execute' && step !== 'preflight') ||
      (stepName === 'result' && (step === 'result' || step === 'audit')) ||
      (stepName === 'audit' && step === 'audit')
    ) {
      return 'border-green-600 bg-green-50 text-green-900';
    }
    return 'border-gray-300 bg-gray-100 text-gray-600';
  };

  return (
    <div className="space-y-6">
      {/* 진행 상황 표시 */}
      <div className="grid grid-cols-4 gap-2">
        {(['preflight', 'execute', 'result', 'audit'] as const).map((s) => (
          <button
            key={s}
            onClick={() => {
              if (s === 'execute' && preflight) setStep('execute');
              else if (s === 'result' && result) setStep('result');
              else if (s === 'audit' && result) setStep('audit');
              else if (s === 'preflight') setStep('preflight');
            }}
            className={`p-3 rounded-lg border-2 text-sm font-medium transition-all ${getStepColor(s)}`}
          >
            {s === 'preflight' && '1️⃣ 사전검사'}
            {s === 'execute' && '2️⃣ 실행'}
            {s === 'result' && '3️⃣ 결과'}
            {s === 'audit' && '4️⃣ 감사로그'}
          </button>
        ))}
      </div>

      {/* 단계별 콘텐츠 */}
      {step === 'preflight' && (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">1️⃣ 사전검사</h3>
          <FileMapPreflight plans={plans} onPreflightComplete={handlePreflightComplete} />
        </div>
      )}

      {step === 'execute' && preflight && (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">2️⃣ 파일 이동 실행</h3>
          <FileMapExecute
            preflightId={preflight.preflight_id}
            packageId={`pkg-${Date.now()}`}
            okCount={preflight.ok_count}
            onExecuteComplete={handleExecuteComplete}
          />
          <button
            onClick={() => setStep('preflight')}
            className="text-sm text-gray-600 hover:text-gray-900 underline"
          >
            ← 이전 단계로
          </button>
        </div>
      )}

      {step === 'result' && result && (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">3️⃣ 실행 결과</h3>
          <FileMapExecuteResult result={result} />
          <div className="flex gap-2">
            <button
              onClick={() => result.ok && setStep('audit')}
              disabled={!result.ok}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 text-sm"
            >
              감사로그 확인 →
            </button>
            <button
              onClick={() => setStep('preflight')}
              className="px-4 py-2 text-gray-600 hover:text-gray-900 border border-gray-300 rounded-lg text-sm"
            >
              처음부터
            </button>
          </div>
        </div>
      )}

      {step === 'audit' && result && (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">4️⃣ 감사로그</h3>
          <FileMapAuditLog runId={result.runId} />
          <button
            onClick={() => setStep('preflight')}
            className="w-full px-4 py-2 text-gray-600 hover:text-gray-900 border border-gray-300 rounded-lg text-sm"
          >
            처음부터 다시
          </button>
        </div>
      )}
    </div>
  );
}
