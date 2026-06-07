"use client";
/** /google — 구글 허브 (셸: 상태·핸들러 보유, ServiceGrid + GoogleChat 조립) */
import { useState, useCallback, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { PageShell } from "@/components/ui/PageShell";
import { API_BASE } from "@/lib/assistant/api";
import { type Service, type ChatMsg, CATALOG } from "./googleCatalog";
import { ServiceGrid } from "./ServiceGrid";
import { GoogleChat } from "./GoogleChat";

// openKey → URL slug 매핑
const SERVICE_SLUG: Record<string, string> = {
  gmail_open: "gmail", calendar_create_event: "calendar", calendar_open: "calendar",
  drive_open: "drive", drive_upload_share_file: "drive",
  docs_open: "docs", docs_create_edit_document: "docs",
  sheets_open: "sheets", sheets_update_cells: "sheets",
  youtube_studio_open: "youtube_studio", youtube_studio_upload_video: "youtube_studio",
  youtube_open: "youtube",
  analytics_open: "analytics",
  ads_open: "ads", ads_campaign_budget_change: "ads",
  search_console_open: "search_console", search_console_submit_indexing: "search_console",
  cloud_console_open: "gcp", cloud_run_deploy_service: "gcp",
  firebase_console_open: "firebase",
  ai_studio_open: "ai_studio",
  gemini_open: "gemini",
  keep_open: "keep", keep_create_note: "keep",
  tasks_open: "tasks", tasks_create_task: "tasks",
  meet_open: "meet", meet_create_meeting: "meet",
  chat_open: "chat", chat_send_message: "chat",
  contacts_open: "contacts", contacts_create_update: "contacts",
  slides_open: "slides", slides_create_presentation: "slides",
  forms_open: "forms", forms_create_publish: "forms",
  photos_open: "photos", photos_upload_share: "photos",
  apps_script_open: "apps_script", apps_script_deploy: "apps_script",
  looker_studio_open: "looker",
  merchant_center_open: "merchant", merchant_center_product_update: "merchant",
  business_profile_open: "business", business_profile_post_or_update: "business",
  tag_manager_open: "tag_manager", tag_manager_publish_version: "tag_manager",
  adsense_open: "adsense",
  google_account_open: "account",
  colab_open: "colab",
  play_console_open: "play",
};

export function GoogleClient() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [msgs, setMsgs] = useState<ChatMsg[]>([{
    role: "system",
    html: "카드를 클릭하면 서비스 설명이 여기에 표시됩니다.<br>또는 직접 명령어를 입력하세요.",
  }]);
  const [chatInput, setChatInput] = useState("");
  const [chatRunning, setChatRunning] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const addMsg = useCallback((role: ChatMsg["role"], html: string) => {
    setMsgs((prev) => [...prev, { role, html }]);
  }, []);

  const handleCardClick = (s: Service) => {
    const slug = SERVICE_SLUG[s.openKey] ?? s.openKey.replace(/_open$/, "").replace(/_/g, "_");
    router.push(`/google/${slug}`);
  };

  const openSite = async (e: React.MouseEvent, s: Service) => {
    e.stopPropagation();
    addMsg("ai", `<span style="color:#6B7280">⏳ ${s.name} 여는 중…</span>`);
    try {
      const tok = typeof window !== "undefined" ? localStorage.getItem("haehan_ai_token") : null;
      const r = await fetch(`${API_BASE}/api/v1/google/tools/open`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: JSON.stringify({ url: s.url }),
      });
      const d = await r.json();
      if (r.ok && d.ok) {
        addMsg("ai", `<span style="color:#16A34A;font-weight:600">✓ ${s.name}</span> 을(를) 로그인된 브라우저에서 열었습니다.`);
      } else {
        window.open(s.url, "_blank", "noopener,noreferrer");
        addMsg("ai", `<span style="color:#C2410C">${s.name}</span> — 브라우저 미연결로 새 창에서 열었습니다.`);
      }
    } catch {
      window.open(s.url, "_blank", "noopener,noreferrer");
      addMsg("ai", `<span style="color:#C2410C">${s.name}</span> — 새 창에서 열었습니다.`);
    }
  };

  const requestAction = async (e: React.MouseEvent, s: Service) => {
    e.stopPropagation();
    if (!s.doKey || !s.doLabel) return;
    addMsg("user", `${s.name} → ${s.doLabel}`);
    try {
      const r = await fetch(`${API_BASE}/api/v1/google/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ host: s.url, action_key: s.doKey }),
      });
      const d = await r.json();
      addMsg("ai", d.ok
        ? `<span style="color:#16A34A;font-weight:600">✅ ${s.doLabel} 완료</span> ${d.message || ""}`
        : `<span style="color:#C2410C;font-weight:600">🔒 승인 필요</span> ${d.reason || d.detail || ""}`
      );
    } catch {
      addMsg("ai", `<span style="color:#DC2626">서버 미연결</span> — 사이트를 직접 이용하세요.`);
    }
  };

  const sendChat = async () => {
    const msg = chatInput.trim();
    if (!msg || chatRunning) return;
    setChatInput("");
    setChatRunning(true);
    addMsg("user", msg);
    try {
      const r = await fetch(`${API_BASE}/api/v1/google/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
      const d = await r.json();
      addMsg("ai", d.reply || "명령을 처리했습니다.");
    } catch {
      addMsg("ai", `<span style="color:#DC2626">서버 미연결</span> — 직접 사이트를 이용하세요.`);
    } finally {
      setChatRunning(false);
    }
  };

  return (
    <PageShell title="구글 허브" description={`${CATALOG.length}개 Google 서비스`} chatDomain="google">
      <div className="flex flex-col lg:flex-row gap-4 h-full" style={{ minHeight: "calc(100vh - 120px)" }}>
        <ServiceGrid query={query} setQuery={setQuery} onCardClick={handleCardClick} onOpen={openSite} onAction={requestAction} />
        <GoogleChat msgs={msgs} chatInput={chatInput} setChatInput={setChatInput} chatRunning={chatRunning} onSend={sendChat} endRef={chatEndRef} />
      </div>
    </PageShell>
  );
}
