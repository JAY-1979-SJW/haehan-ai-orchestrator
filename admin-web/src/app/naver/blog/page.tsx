"use client";
/** /naver/blog — 네이버 블로그 AI 채팅 + 이벤트 패널 */
import { useEffect, useState, useCallback } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { UniversalChat } from "@/components/chat/UniversalChat";

interface BlogEvent {
  eventId: string;
  eventType: string;
  status: string;
  timestamp: string;
  summary: string;
}

const EVENT_TYPES = ["NAVER_BLOG_WRITE", "NAVER_BLOG_UPLOAD", "NAVER_BLOG_UNSPLASH", "NAVER_BLOG_COMPOSE"];

const STATUS_STYLE: Record<string, string> = {
  ok:        "bg-[#D1FAE5] text-[#065F46]",
  published: "bg-[#DBEAFE] text-[#1E40AF]",
  draft:     "bg-[#F3F4F6] text-[#374151]",
  uploaded:  "bg-[#EDE9FE] text-[#5B21B6]",
  resolved:  "bg-[#FEF3C7] text-[#92400E]",
  warn:      "bg-[#FEF3C7] text-[#92400E]",
  error:     "bg-[#FEE2E2] text-[#991B1B]",
};

const TYPE_LABEL: Record<string, string> = {
  NAVER_BLOG_WRITE:    "글 작성",
  NAVER_BLOG_UPLOAD:   "파일 업로드",
  NAVER_BLOG_UNSPLASH: "이미지 선택",
  NAVER_BLOG_COMPOSE:  "초안 저장",
};

function EventPanel() {
  const [events, setEvents] = useState<BlogEvent[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await fetch("/api/proxy/api/v1/ops/audit-events?limit=30", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json() as { events: BlogEvent[] };
      const filtered = (data.events ?? [])
        .filter((e) => EVENT_TYPES.includes(e.eventType))
        .slice(0, 10);
      setEvents(filtered);
    } catch {
      // 서버 미실행 시 무시
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
    const id = setInterval(fetchEvents, 5000);
    return () => clearInterval(id);
  }, [fetchEvents]);

  if (loading) return <p className="text-xs text-[#9CA3AF] py-2">불러오는 중...</p>;
  if (!events.length) return <p className="text-xs text-[#9CA3AF] py-2">아직 작업 기록이 없습니다.</p>;

  return (
    <ul className="space-y-1.5">
      {events.map((e) => (
        <li key={e.eventId} className="flex items-start gap-2 text-xs">
          <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-semibold ${STATUS_STYLE[e.status] ?? "bg-[#F3F4F6] text-[#374151]"}`}>
            {TYPE_LABEL[e.eventType] ?? e.eventType}
          </span>
          <span className="text-[#374151] flex-1 min-w-0 truncate">{e.summary}</span>
          <span className="shrink-0 text-[#9CA3AF]">{e.timestamp.slice(11, 16)}</span>
        </li>
      ))}
    </ul>
  );
}

export default function BlogPage() {
  return (
    <PageShell title="블로그 AI" description="주제를 말하면 AI가 글을 작성하고 Unsplash 이미지를 자동으로 붙여 네이버 블로그에 올립니다">
      <div className="space-y-3">
        {/* 안내 배너 */}
        <div className="border border-[#BFDBFE] bg-[#EFF6FF] rounded-xl px-4 py-3 flex items-start gap-3">
          <span className="text-[#3B82F6] text-base mt-0.5">✦</span>
          <div>
            <p className="text-xs font-bold text-[#1D4ED8]">AI가 글 작성 + Unsplash 이미지 자동 삽입</p>
            <p className="text-xs text-[#1E40AF] mt-0.5">
              주제만 입력하면 AI가 제목·본문·태그를 생성하고 이미지 3장을 자동으로 선택해 네이버 블로그에 작성합니다.
              임시저장은 자동, <b>발행은 확인 후</b> 진행됩니다.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-3">
          {/* 채팅창 */}
          <UniversalChat
            domain="blog"
            title="블로그 AI"
            className="h-[calc(100vh-260px)] min-h-[400px]"
          />

          {/* 이벤트 패널 */}
          <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 flex flex-col gap-2 h-fit">
            <p className="text-xs font-semibold text-[#111827]">최근 작업 이벤트</p>
            <p className="text-[10px] text-[#9CA3AF]">5초마다 자동 갱신</p>
            <div className="mt-1">
              <EventPanel />
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
