/**
 * 외부 웹 업무 현황 페이지
 *
 * 네이버·구글 등 외부 웹 업무의 실행 위치, 인증 방식, 승인 필요 여부,
 * 현재 상태(준비됨/OAuth 필요/로컬 에이전트 필요/사용자 직접/HOLD)를 표시한다.
 *
 * 실제 실행 버튼은 분류에 따라:
 *   - SERVER_READONLY_ALLOWED  → 조회 실행 가능 (enabled)
 *   - WEB_TASK_REGISTRY        → "실행 요청" (승인 필요, disabled until approval)
 *   - OFFICIAL_API_OR_OAUTH_REQUIRED → "OAuth 설정 필요" (disabled)
 *   - LOCAL_AGENT_REQUIRED     → "로컬 에이전트 필요" (disabled)
 *   - USER_DIRECT_REQUIRED     → "사용자 직접 조작 필요" (disabled)
 *   - QUARANTINE_OR_HOLD       → "차단됨" (disabled)
 */
"use client";

import React from "react";
import { PageShell } from "@/components/ui/PageShell";

import { type Classification, type ExternalWorkEntry, EXTERNAL_WORKS, CLASSIFICATION_STYLES, RISK_STYLES } from "./externalTasksData";
function ActionButton({ entry }: { entry: ExternalWorkEntry }) {
  const cls = entry.classification;
  if (cls === "SERVER_READONLY_ALLOWED") {
    return (
      <button
        className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700"
        disabled
        title="API 연결 후 활성화"
      >
        조회
      </button>
    );
  }
  if (cls === "WEB_TASK_REGISTRY") {
    return (
      <button
        className="px-3 py-1 text-sm bg-blue-600 text-white rounded opacity-60 cursor-not-allowed"
        disabled
        title="승인 게이트 통과 후 실행"
      >
        실행 요청 (승인 필요)
      </button>
    );
  }
  if (cls === "OFFICIAL_API_OR_OAUTH_REQUIRED") {
    return (
      <button
        className="px-3 py-1 text-sm bg-yellow-500 text-white rounded opacity-60 cursor-not-allowed"
        disabled
        title="OAuth/API 설정 필요"
      >
        OAuth 설정 필요
      </button>
    );
  }
  if (cls === "LOCAL_AGENT_REQUIRED") {
    return (
      <button
        className="px-3 py-1 text-sm bg-orange-500 text-white rounded opacity-60 cursor-not-allowed"
        disabled
        title="로컬 에이전트에서 실행"
      >
        로컬 에이전트 필요
      </button>
    );
  }
  if (cls === "USER_DIRECT_REQUIRED") {
    return (
      <button
        className="px-3 py-1 text-sm bg-purple-500 text-white rounded opacity-60 cursor-not-allowed"
        disabled
        title="사용자가 직접 실행해야 함"
      >
        사용자 직접 조작 필요
      </button>
    );
  }
  return (
    <button
      className="px-3 py-1 text-sm bg-red-400 text-white rounded opacity-60 cursor-not-allowed"
      disabled
      title="차단됨"
    >
      차단됨
    </button>
  );
}

function ExternalWorkRow({ entry }: { entry: ExternalWorkEntry }) {
  const style = CLASSIFICATION_STYLES[entry.classification];
  return (
    <tr className="border-b hover:bg-gray-50">
      <td className="px-4 py-3 font-mono text-xs text-gray-600">{entry.work_key}</td>
      <td className="px-4 py-3 text-sm">{entry.description}</td>
      <td className="px-4 py-3">
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${style.badge}`}>
          {style.label}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-gray-500">{entry.execution_location}</td>
      <td className={`px-4 py-3 text-xs font-medium ${RISK_STYLES[entry.risk_level] ?? ""}`}>
        {entry.risk_level}
      </td>
      <td className="px-4 py-3 text-xs text-gray-500">{entry.auth_method}</td>
      <td className="px-4 py-3">
        {entry.requires_approval ? (
          <span className="text-xs text-red-600 font-medium">승인 필요</span>
        ) : (
          <span className="text-xs text-green-600">불필요</span>
        )}
      </td>
      <td className="px-4 py-3">
        <ActionButton entry={entry} />
      </td>
    </tr>
  );
}

export default function ExternalTasksPage() {
  const providers = ["naver", "google"];

  return (
    <PageShell title="외부 업무 현황" description="외부 웹 업무 · 승인 분류" chatDomain="ops">
      <div className="space-y-6">
      {/* 분류 범례 */}
      <div className="mb-6 flex flex-wrap gap-2">
        {Object.entries(CLASSIFICATION_STYLES).map(([key, val]) => (
          <span key={key} className={`px-2 py-1 rounded text-xs font-medium ${val.badge}`}>
            {val.label}
          </span>
        ))}
      </div>

      {providers.map((provider) => {
        const items = EXTERNAL_WORKS.filter((e) => e.provider === provider);
        return (
          <div key={provider} className="mb-8">
            <h2 className="text-lg font-semibold text-gray-800 mb-3 capitalize">
              {provider === "naver" ? "네이버 (Naver)" : "구글 (Google)"}
            </h2>
            <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
              <table className="min-w-full bg-white">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">작업키</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">설명</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">상태</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">실행 위치</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">위험도</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">인증</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">승인</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">액션</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((entry) => (
                    <ExternalWorkRow key={entry.work_key} entry={entry} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}

      <div className="mt-4 p-4 bg-gray-50 rounded-lg border text-xs text-gray-500">
        <strong>안전 경계:</strong> 이 페이지에서 실제 외부 API 호출·게시·메일발송·파일수정은 수행하지 않습니다.
        실행 가능한 항목도 승인 게이트를 통과해야 최종 실행됩니다.
        서버에서 Google/Naver 계정 로그인을 자동 실행하지 않습니다.
      </div>
      </div>
    </PageShell>
  );
}
