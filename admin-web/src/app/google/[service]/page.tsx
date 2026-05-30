"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { PageShell } from "@/components/ui/PageShell";

// ── 앱별 설정 ─────────────────────────────────────────────────────────────────
const SERVICE_CONFIG: Record<string, {
  name: string; icon: string; url: string; color: string; bg: string; border: string;
  quickGroups: { label: string; actions: { label: string; prompt: string }[] }[];
}> = {
  gmail: {
    name: "Gmail", icon: "✉️", url: "https://mail.google.com/",
    color: "#DC2626", bg: "#FEF2F2", border: "#FECACA",
    quickGroups: [
      { label: "조회", actions: [
        { label: "받은편지함", prompt: "Gmail 받은편지함 최근 메일을 보여줘" },
        { label: "중요 메일",  prompt: "Gmail 중요 표시된 메일을 조회해줘" },
        { label: "미읽음 메일", prompt: "Gmail 읽지 않은 메일을 확인해줘" },
        { label: "보낸편지함", prompt: "Gmail 보낸편지함을 조회해줘" },
      ]},
      { label: "실행", actions: [
        { label: "메일 작성",  prompt: "Gmail에서 메일 작성 화면을 열어줘" },
        { label: "메일 검색",  prompt: "Gmail에서 메일을 검색해줘" },
        { label: "Gmail 열기", prompt: "Gmail을 열어줘" },
      ]},
    ],
  },
  calendar: {
    name: "캘린더", icon: "📅", url: "https://calendar.google.com/",
    color: "#1D4ED8", bg: "#EFF6FF", border: "#BFDBFE",
    quickGroups: [
      { label: "조회", actions: [
        { label: "오늘 일정",   prompt: "Google 캘린더에서 오늘 일정을 보여줘" },
        { label: "이번 주 일정", prompt: "Google 캘린더에서 이번 주 일정을 보여줘" },
        { label: "이번 달 일정", prompt: "Google 캘린더에서 이번 달 일정을 보여줘" },
      ]},
      { label: "실행", actions: [
        { label: "일정 추가",   prompt: "Google 캘린더에 일정을 추가해줘" },
        { label: "캘린더 열기", prompt: "Google 캘린더를 열어줘" },
      ]},
    ],
  },
  drive: {
    name: "Drive", icon: "📁", url: "https://drive.google.com/",
    color: "#F97316", bg: "#FFF7ED", border: "#FED7AA",
    quickGroups: [
      { label: "조회", actions: [
        { label: "최근 파일",  prompt: "Google Drive 최근 파일을 보여줘" },
        { label: "공유 파일",  prompt: "Google Drive 공유된 파일을 조회해줘" },
        { label: "내 드라이브", prompt: "Google Drive 내 드라이브를 조회해줘" },
      ]},
      { label: "실행", actions: [
        { label: "파일 업로드", prompt: "Google Drive에 파일을 업로드해줘" },
        { label: "Drive 열기", prompt: "Google Drive를 열어줘" },
      ]},
    ],
  },
  sheets: {
    name: "Sheets", icon: "📊", url: "https://sheets.google.com/",
    color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0",
    quickGroups: [
      { label: "조회", actions: [
        { label: "최근 시트",  prompt: "Google Sheets 최근 파일을 보여줘" },
        { label: "공유 시트",  prompt: "Google Sheets 공유된 파일을 조회해줘" },
      ]},
      { label: "실행", actions: [
        { label: "새 시트 생성", prompt: "Google Sheets 새 스프레드시트를 생성해줘" },
        { label: "셀 업데이트",  prompt: "Google Sheets 셀 데이터를 업데이트해줘" },
        { label: "Sheets 열기", prompt: "Google Sheets를 열어줘" },
      ]},
    ],
  },
  docs: {
    name: "Docs", icon: "📄", url: "https://docs.google.com/",
    color: "#1D4ED8", bg: "#EFF6FF", border: "#BFDBFE",
    quickGroups: [
      { label: "조회", actions: [
        { label: "최근 문서", prompt: "Google Docs 최근 문서를 보여줘" },
        { label: "공유 문서", prompt: "Google Docs 공유된 문서를 조회해줘" },
      ]},
      { label: "실행", actions: [
        { label: "새 문서 생성", prompt: "Google Docs 새 문서를 생성해줘" },
        { label: "Docs 열기",   prompt: "Google Docs를 열어줘" },
      ]},
    ],
  },
  youtube_studio: {
    name: "YouTube Studio", icon: "🎬", url: "https://studio.youtube.com/",
    color: "#DC2626", bg: "#FEF2F2", border: "#FECACA",
    quickGroups: [
      { label: "조회", actions: [
        { label: "채널 현황",  prompt: "YouTube Studio 채널 현황을 보여줘" },
        { label: "영상 목록",  prompt: "YouTube Studio 최근 영상 목록을 조회해줘" },
        { label: "댓글 확인",  prompt: "YouTube Studio 최근 댓글을 확인해줘" },
      ]},
      { label: "실행", actions: [
        { label: "영상 업로드", prompt: "YouTube Studio에서 영상을 업로드해줘" },
        { label: "Studio 열기", prompt: "YouTube Studio를 열어줘" },
      ]},
    ],
  },
  analytics: {
    name: "Analytics", icon: "📈", url: "https://analytics.google.com/",
    color: "#F97316", bg: "#FFF7ED", border: "#FED7AA",
    quickGroups: [
      { label: "조회", actions: [
        { label: "오늘 트래픽",  prompt: "Google Analytics 오늘 트래픽을 보여줘" },
        { label: "이번 주 분석", prompt: "Google Analytics 이번 주 방문자 분석을 해줘" },
        { label: "유입 경로",    prompt: "Google Analytics 유입 경로를 분석해줘" },
        { label: "전환율 확인",  prompt: "Google Analytics 전환율을 확인해줘" },
      ]},
      { label: "실행", actions: [
        { label: "Analytics 열기", prompt: "Google Analytics를 열어줘" },
      ]},
    ],
  },
  search_console: {
    name: "Search Console", icon: "🔍", url: "https://search.google.com/search-console/",
    color: "#7C3AED", bg: "#F5F3FF", border: "#DDD6FE",
    quickGroups: [
      { label: "조회", actions: [
        { label: "검색 실적",   prompt: "Search Console 검색 실적을 보여줘" },
        { label: "색인 현황",   prompt: "Search Console 색인 현황을 확인해줘" },
        { label: "오류 확인",   prompt: "Search Console 크롤링 오류를 확인해줘" },
      ]},
      { label: "실행", actions: [
        { label: "색인 요청",        prompt: "Search Console에서 URL 색인을 요청해줘" },
        { label: "Search Console 열기", prompt: "Search Console을 열어줘" },
      ]},
    ],
  },
  gcp: {
    name: "GCP Console", icon: "☁️", url: "https://console.cloud.google.com/?project=haehan-ai",
    color: "#0891B2", bg: "#ECFEFF", border: "#A5F3FC",
    quickGroups: [
      { label: "조회", actions: [
        { label: "Cloud Run 현황", prompt: "GCP Cloud Run 서비스 현황을 보여줘" },
        { label: "빌링 확인",      prompt: "GCP 빌링·비용 현황을 확인해줘" },
        { label: "로그 조회",      prompt: "GCP Cloud Logging에서 최근 로그를 조회해줘" },
      ]},
      { label: "실행", actions: [
        { label: "GCP Console 열기", prompt: "GCP Console haehan-ai 프로젝트를 열어줘" },
      ]},
    ],
  },
  ads: {
    name: "Google Ads", icon: "📢", url: "https://ads.google.com/",
    color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0",
    quickGroups: [
      { label: "조회", actions: [
        { label: "캠페인 현황", prompt: "Google Ads 캠페인 현황을 보여줘" },
        { label: "예산 확인",   prompt: "Google Ads 예산 현황을 확인해줘" },
        { label: "성과 분석",   prompt: "Google Ads 광고 성과를 분석해줘" },
      ]},
      { label: "실행", actions: [
        { label: "캠페인 수정", prompt: "Google Ads 캠페인을 수정해줘" },
        { label: "Ads 열기",   prompt: "Google Ads를 열어줘" },
      ]},
    ],
  },
};

// 설정 없는 앱은 기본 빠른 버튼 제공
function getConfig(service: string) {
  const cfg = SERVICE_CONFIG[service];
  if (cfg) return cfg;

  // CATALOG에서 매핑
  const nameMap: Record<string, { name: string; icon: string; url: string }> = {
    meet:        { name: "Meet",        icon: "🎥", url: "https://meet.google.com/" },
    chat:        { name: "Chat",        icon: "💬", url: "https://chat.google.com/" },
    contacts:    { name: "연락처",      icon: "👥", url: "https://contacts.google.com/" },
    slides:      { name: "Slides",      icon: "🎞️", url: "https://slides.google.com/" },
    forms:       { name: "Forms",       icon: "📋", url: "https://forms.google.com/" },
    keep:        { name: "Keep",        icon: "🗒️", url: "https://keep.google.com/" },
    tasks:       { name: "Tasks",       icon: "✅", url: "https://tasks.google.com/" },
    photos:      { name: "Photos",      icon: "🖼️", url: "https://photos.google.com/" },
    youtube:     { name: "YouTube",     icon: "▶️", url: "https://www.youtube.com/" },
    firebase:    { name: "Firebase",    icon: "🔥", url: "https://console.firebase.google.com/" },
    ai_studio:   { name: "AI Studio",   icon: "✨", url: "https://aistudio.google.com/" },
    gemini:      { name: "Gemini",      icon: "🤖", url: "https://gemini.google.com/" },
    colab:       { name: "Colab",       icon: "🔬", url: "https://colab.research.google.com/" },
    play:        { name: "Play Console",icon: "🎮", url: "https://play.google.com/console/" },
    apps_script: { name: "Apps Script", icon: "⚙️", url: "https://script.google.com/" },
    looker:      { name: "Looker Studio",icon: "📉", url: "https://lookerstudio.google.com/" },
    merchant:    { name: "Merchant Center",icon: "🛒", url: "https://merchants.google.com/" },
    business:    { name: "Business Profile",icon: "🏪", url: "https://business.google.com/" },
    tag_manager: { name: "Tag Manager", icon: "🏷️", url: "https://tagmanager.google.com/" },
    adsense:     { name: "AdSense",     icon: "💰", url: "https://adsense.google.com/" },
    account:     { name: "내 계정",     icon: "👤", url: "https://myaccount.google.com/" },
  };

  const info = nameMap[service] ?? { name: service, icon: "🔗", url: "https://google.com" };
  return {
    ...info,
    color: "#374151", bg: "#F9FAFB", border: "#E5E7EB",
    quickGroups: [
      { label: "실행", actions: [
        { label: `${info.name} 열기`, prompt: `${info.name}을(를) 열어줘` },
        { label: "현황 조회",         prompt: `${info.name} 현황을 보여줘` },
      ]},
    ],
  };
}

// ── 채팅 타입 ────────────────────────────────────────────────────────────────
type ChatMsg = { role: "user" | "ai"; text: string };

// ── 페이지 ────────────────────────────────────────────────────────────────────
export default function GoogleServicePage() {
  const params  = useParams();
  const router  = useRouter();
  const service = typeof params?.service === "string" ? params.service : "";
  const cfg     = getConfig(service);

  const [msgs, setMsgs]         = useState<ChatMsg[]>([]);
  const [input, setInput]       = useState("");
  const [running, setRunning]   = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const send = useCallback(async (text: string) => {
    if (!text.trim() || running) return;
    setMsgs((p) => [...p, { role: "user", text }]);
    setInput("");
    setRunning(true);
    try {
      const r = await fetch("/api/google/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: `[${cfg.name}] ${text}` }),
      });
      const d = await r.json();
      setMsgs((p) => [...p, { role: "ai", text: d.reply ?? "처리 완료" }]);
    } catch {
      setMsgs((p) => [...p, { role: "ai", text: "서버 연결 오류" }]);
    } finally {
      setRunning(false);
    }
  }, [running, cfg.name]);

  return (
    <PageShell title={`${cfg.icon} ${cfg.name}`} description="Google 앱 AI 에이전트" chatDomain="google">
      <div className="flex flex-col h-full w-full gap-4" style={{ minHeight: "calc(100vh - 120px)" }}>

        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl border"
              style={{ background: cfg.bg, borderColor: cfg.border }}>
              {cfg.icon}
            </div>
            <div>
              <h1 className="text-base font-bold text-[#111827]">{cfg.name}</h1>
              <a href={cfg.url} target="_blank" rel="noopener noreferrer"
                className="text-xs hover:underline" style={{ color: cfg.color }}>{cfg.url}</a>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a href={cfg.url} target="_blank" rel="noopener noreferrer"
              className="px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors hover:opacity-80"
              style={{ background: cfg.bg, color: cfg.color, borderColor: cfg.border }}>
              사이트 열기 →
            </a>
            <Link href="/google"
              className="px-3 py-1.5 rounded-lg text-xs text-[#6B7280] border border-[#E5E7EB] hover:border-[#374151] transition-colors">
              ← 허브
            </Link>
          </div>
        </div>

        {/* 빠른 버튼 패널 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-4 space-y-3">
          <p className="text-xs font-bold text-[#374151]">⚡ 빠른 작업</p>
          {cfg.quickGroups.map((g) => (
            <div key={g.label}>
              <p className="text-[10px] font-semibold uppercase tracking-wider mb-1.5"
                style={{ color: cfg.color }}>{g.label}</p>
              <div className="flex flex-wrap gap-2">
                {g.actions.map((a) => (
                  <button key={a.label} disabled={running}
                    onClick={() => send(a.prompt)}
                    className="px-3 py-1.5 rounded-full text-xs font-medium border transition-colors hover:shadow-sm disabled:opacity-40"
                    style={{ background: cfg.bg, borderColor: cfg.border, color: cfg.color }}>
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* 채팅창 */}
        <div className="flex-1 flex flex-col bg-white border border-[#E5E7EB] rounded-2xl overflow-hidden min-h-0">
          {/* 메시지 */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {msgs.length === 0 && (
              <div className="flex items-center justify-center h-full text-center">
                <div>
                  <p className="text-3xl mb-2">{cfg.icon}</p>
                  <p className="text-sm font-medium text-[#6B7280]">{cfg.name} AI 에이전트</p>
                  <p className="text-xs text-[#9CA3AF] mt-1">위 버튼을 클릭하거나 직접 입력하세요</p>
                </div>
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "user" ? (
                  <div className="max-w-[70%] px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm text-white"
                    style={{ background: cfg.color }}>
                    {m.text}
                  </div>
                ) : (
                  <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-tl-sm text-sm text-[#111827] bg-[#F9FAFB] border border-[#E5E7EB] whitespace-pre-wrap">
                    {m.text}
                  </div>
                )}
              </div>
            ))}
            {running && (
              <div className="flex justify-start">
                <div className="px-4 py-2.5 rounded-2xl rounded-tl-sm bg-[#F9FAFB] border border-[#E5E7EB]">
                  <span className="flex gap-1">
                    {[0, 150, 300].map((d) => (
                      <span key={d} className="w-1.5 h-1.5 rounded-full bg-[#9CA3AF] animate-bounce"
                        style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* 입력창 */}
          <div className="shrink-0 px-4 py-3 border-t border-[#E5E7EB] flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }}}
              placeholder={`${cfg.name}에게 지시하세요...`}
              disabled={running}
              className="flex-1 border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 disabled:opacity-50"
              style={{ focusRingColor: cfg.color } as React.CSSProperties}
            />
            <button onClick={() => send(input)} disabled={running || !input.trim()}
              className="px-5 py-2.5 rounded-xl text-white text-sm font-semibold disabled:opacity-40 transition-colors"
              style={{ background: cfg.color }}>
              {running ? "···" : "전송"}
            </button>
          </div>
        </div>

      </div>
    </PageShell>
  );
}
