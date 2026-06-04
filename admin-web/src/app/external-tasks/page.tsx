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

type Classification =
  | "SERVER_READONLY_ALLOWED"
  | "WEB_TASK_REGISTRY"
  | "OFFICIAL_API_OR_OAUTH_REQUIRED"
  | "LOCAL_AGENT_REQUIRED"
  | "USER_DIRECT_REQUIRED"
  | "QUARANTINE_OR_HOLD";

interface ExternalWorkEntry {
  work_key: string;
  provider: string;
  work_type: string;
  description: string;
  classification: Classification;
  execution_location: string;
  risk_level: string;
  requires_approval: boolean;
  requires_auth: boolean;
  auth_method: string;
  registered_in_web_task: boolean;
  notes: string;
}

// 정적 분류 목록 — 실제 API 연동 전 정책 표시용
const EXTERNAL_WORKS: ExternalWorkEntry[] = [
  // ── Naver read-only (서버 실행 가능) ─────────────────────────────────
  {
    work_key: "naver/blog_search",
    provider: "naver",
    work_type: "blog_search",
    description: "네이버 블로그 검색 결과 조회 (조회 전용)",
    classification: "SERVER_READONLY_ALLOWED",
    execution_location: "SERVER",
    risk_level: "low",
    requires_approval: false,
    requires_auth: false,
    auth_method: "none",
    registered_in_web_task: false,
    notes: "/api/v1/external/naver/blog-search",
  },
  {
    work_key: "naver/shopping_search",
    provider: "naver",
    work_type: "shopping_search",
    description: "네이버 쇼핑 검색 결과 조회 (조회 전용)",
    classification: "SERVER_READONLY_ALLOWED",
    execution_location: "SERVER",
    risk_level: "low",
    requires_approval: false,
    requires_auth: false,
    auth_method: "none",
    registered_in_web_task: false,
    notes: "/api/v1/external/naver/shopping-search",
  },
  {
    work_key: "naver/search_status",
    provider: "naver",
    work_type: "search_status",
    description: "네이버 검색 수집 상태 조회 (조회 전용)",
    classification: "SERVER_READONLY_ALLOWED",
    execution_location: "SERVER",
    risk_level: "low",
    requires_approval: false,
    requires_auth: false,
    auth_method: "none",
    registered_in_web_task: false,
    notes: "/api/v1/external/naver/status",
  },
  // ── Naver web task 등록됨 ─────────────────────────────────────────────
  {
    work_key: "naver/app_register",
    provider: "naver",
    work_type: "app_register",
    description: "네이버 개발자 센터 앱 등록 (승인 필요)",
    classification: "WEB_TASK_REGISTRY",
    execution_location: "LOCAL_AGENT",
    risk_level: "high",
    requires_approval: true,
    requires_auth: true,
    auth_method: "browser_session",
    registered_in_web_task: true,
    notes: "web_task_registry 등록됨. 로컬 에이전트 + 사전 로그인 필요.",
  },
  // ── Naver 로컬 에이전트 필요 ─────────────────────────────────────────
  {
    work_key: "naver/blog_write",
    provider: "naver",
    work_type: "blog_write",
    description: "네이버 블로그 글 작성/게시 (로컬 에이전트 필요)",
    classification: "LOCAL_AGENT_REQUIRED",
    execution_location: "LOCAL_AGENT",
    risk_level: "high",
    requires_approval: true,
    requires_auth: true,
    auth_method: "browser_session",
    registered_in_web_task: false,
    notes: "서버 직접 실행 불가. 로컬 에이전트 + 사용자 승인 필요.",
  },
  {
    work_key: "naver/cafe_post",
    provider: "naver",
    work_type: "cafe_post",
    description: "네이버 카페 게시글 작성/게시 (로컬 에이전트 필요)",
    classification: "LOCAL_AGENT_REQUIRED",
    execution_location: "LOCAL_AGENT",
    risk_level: "high",
    requires_approval: true,
    requires_auth: true,
    auth_method: "browser_session",
    registered_in_web_task: false,
    notes: "서버 직접 실행 불가.",
  },
  {
    work_key: "naver/mail_send",
    provider: "naver",
    work_type: "mail_send",
    description: "네이버 메일 발송 (사용자 직접 확인 필요)",
    classification: "USER_DIRECT_REQUIRED",
    execution_location: "USER_DIRECT",
    risk_level: "high",
    requires_approval: true,
    requires_auth: true,
    auth_method: "browser_session",
    registered_in_web_task: false,
    notes: "발송은 사용자가 직접 확인 후 실행.",
  },
  // ── Google web task 등록됨 ────────────────────────────────────────────
  {
    work_key: "google/oauth_submit",
    provider: "google",
    work_type: "oauth_submit",
    description: "Google Cloud Console OAuth 클라이언트 등록 (승인 필요)",
    classification: "WEB_TASK_REGISTRY",
    execution_location: "LOCAL_AGENT",
    risk_level: "high",
    requires_approval: true,
    requires_auth: true,
    auth_method: "browser_session",
    registered_in_web_task: true,
    notes: "web_task_registry 등록됨. 사전 로그인 필요.",
  },
  // ── Google 공식 API/OAuth 필요 ────────────────────────────────────────
  {
    work_key: "google/gmail_read",
    provider: "google",
    work_type: "gmail_read",
    description: "Gmail 수신함 조회 (공식 Gmail API + OAuth2)",
    classification: "OFFICIAL_API_OR_OAUTH_REQUIRED",
    execution_location: "OFFICIAL_API",
    risk_level: "medium",
    requires_approval: false,
    requires_auth: true,
    auth_method: "oauth",
    registered_in_web_task: false,
    notes: "credentials.json + token.json 설정 완료 시 활성화. /api/v1/inbox/email/fetch",
  },
  {
    work_key: "google/calendar_read",
    provider: "google",
    work_type: "calendar_read",
    description: "Google Calendar 일정 조회 (공식 API + OAuth2)",
    classification: "OFFICIAL_API_OR_OAUTH_REQUIRED",
    execution_location: "OFFICIAL_API",
    risk_level: "medium",
    requires_approval: false,
    requires_auth: true,
    auth_method: "oauth",
    registered_in_web_task: false,
    notes: "공식 API client 미구현. FUTURE_INTEGRATION.",
  },
  {
    work_key: "google/drive_read",
    provider: "google",
    work_type: "drive_read",
    description: "Google Drive 파일 조회 (공식 Drive API + OAuth2)",
    classification: "OFFICIAL_API_OR_OAUTH_REQUIRED",
    execution_location: "OFFICIAL_API",
    risk_level: "medium",
    requires_approval: false,
    requires_auth: true,
    auth_method: "oauth",
    registered_in_web_task: false,
    notes: "공식 Drive API client 미구현. FUTURE_INTEGRATION.",
  },
  {
    work_key: "google/browser_login",
    provider: "google",
    work_type: "browser_login",
    description: "Google 계정 브라우저 로그인 자동화 — 차단됨",
    classification: "QUARANTINE_OR_HOLD",
    execution_location: "USER_DIRECT",
    risk_level: "high",
    requires_approval: true,
    requires_auth: true,
    auth_method: "user_direct",
    registered_in_web_task: false,
    notes: "서버 브라우저 Google 로그인 자동화 금지. execution_location_guard 차단.",
  },
];

// ── 분류별 배지 스타일 ───────────────────────────────────────────────────────

const CLASSIFICATION_STYLES: Record<Classification, { badge: string; label: string }> = {
  SERVER_READONLY_ALLOWED: {
    badge: "bg-green-100 text-green-800",
    label: "조회 가능",
  },
  WEB_TASK_REGISTRY: {
    badge: "bg-blue-100 text-blue-800",
    label: "실행 요청 가능 (승인 필요)",
  },
  OFFICIAL_API_OR_OAUTH_REQUIRED: {
    badge: "bg-yellow-100 text-yellow-800",
    label: "OAuth/API 설정 필요",
  },
  LOCAL_AGENT_REQUIRED: {
    badge: "bg-orange-100 text-orange-800",
    label: "로컬 에이전트 필요",
  },
  USER_DIRECT_REQUIRED: {
    badge: "bg-purple-100 text-purple-800",
    label: "사용자 직접 조작 필요",
  },
  QUARANTINE_OR_HOLD: {
    badge: "bg-red-100 text-red-800",
    label: "차단됨",
  },
};

const RISK_STYLES: Record<string, string> = {
  low: "text-green-700",
  medium: "text-yellow-700",
  high: "text-red-700",
};

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
