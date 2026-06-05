"use client";
/** 커뮤니티 레이더 — 텔레그램 알림 설정 (자체완결) */
import { useState, useEffect, useCallback } from "react";
import { authHeader, J } from "../communityShared";

type Notify = { enabled?: boolean; token_set?: boolean; token_masked?: string; chat_id?: string };

export function TelegramNotify() {
  const [notify, setNotify] = useState<Notify | null>(null);
  const [tgToken, setTgToken] = useState("");
  const [msg, setMsg] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/proxy/api/v1/community/notify/config", { headers: authHeader() });
      setNotify(await r.json());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function setup() {
    if (!tgToken.trim()) return;
    setMsg("연결 중…");
    try {
      const r = await fetch("/api/proxy/api/v1/community/notify/telegram", {
        method: "POST", headers: { ...J, ...authHeader() }, body: JSON.stringify({ token: tgToken.trim() }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "설정 실패");
      setTgToken("");
      setMsg(d.detected ? `✅ 연결됨 (chat_id 감지: ${d.chat_id})` : "⚠️ 토큰 저장됨 — 텔레그램에서 봇에게 메시지를 한 번 보낸 뒤 다시 [연결]을 누르세요");
      await load();
    } catch (e) { setMsg("오류: " + String(e)); }
  }
  async function test() {
    setMsg("테스트 발송 중…");
    try {
      const r = await fetch("/api/proxy/api/v1/community/notify/test", { method: "POST", headers: authHeader() });
      const d = await r.json();
      setMsg(r.ok ? "✅ 테스트 발송 성공 — 텔레그램을 확인하세요" : "발송 실패: " + (d.detail || ""));
    } catch (e) { setMsg("오류: " + String(e)); }
  }
  async function toggle(enabled: boolean) {
    await fetch("/api/proxy/api/v1/community/notify/toggle", {
      method: "POST", headers: { ...J, ...authHeader() }, body: JSON.stringify({ enabled }),
    });
    await load();
  }

  return (
    <div className="border border-[#E5E7EB] rounded-2xl bg-white p-4 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-bold text-[#111827]">📨 텔레그램 알림</p>
        {notify?.token_set && notify?.chat_id && (
          <label className="flex items-center gap-1.5 text-xs text-[#6B7280] cursor-pointer">
            <input type="checkbox" checked={!!notify.enabled} onChange={(e) => toggle(e.target.checked)} />
            자동 발송 {notify.enabled ? "켜짐" : "꺼짐"}
          </label>
        )}
      </div>
      {notify?.token_set && notify?.chat_id ? (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-[#16A34A]">✅ 연결됨 (chat {notify.chat_id})</span>
          <button onClick={test} className="px-2.5 py-1 rounded-lg border border-[#E5E7EB] text-xs text-[#6B7280] hover:bg-[#F9FAFB]">테스트 발송</button>
          <button onClick={() => { setTgToken(""); setNotify({ ...notify, token_set: false }); }} className="text-xs text-[#9CA3AF] hover:text-[#DC2626]">토큰 변경</button>
        </div>
      ) : (
        <div className="space-y-1.5">
          <p className="text-[11px] text-[#9CA3AF]">① 텔레그램 @BotFather 에서 봇 생성 → 토큰 복사 ② 만든 봇에게 아무 메시지 전송 ③ 아래에 토큰 붙여넣고 [연결]</p>
          <div className="flex gap-2">
            <input value={tgToken} onChange={(e) => setTgToken(e.target.value)} placeholder="봇 토큰 (예: 123456:ABC-...)"
              className="flex-1 border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm outline-none focus:border-[#F97316]" />
            <button onClick={setup} disabled={!tgToken.trim()}
              className="px-4 py-2 rounded-xl bg-[#229ED9] text-white text-sm font-semibold hover:bg-[#1c8ec2] disabled:opacity-40">연결</button>
          </div>
        </div>
      )}
      {msg && <p className="text-xs text-[#6B7280]">{msg}</p>}
    </div>
  );
}
