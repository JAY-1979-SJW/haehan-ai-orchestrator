"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { UniversalChat, type ChatPreset, type ExtraCard } from "@/components/chat/UniversalChat";
import { gongmuApi, type Draft, type Site } from "./api";
import { SiteMapExploreCard } from "@/components/sitemap/SiteMapExploreCard";
import { GongmuDraftCard } from "./GongmuDraftCard";

interface Props {
  /** 지금 화면에서 고른 현장 — "이 현장"이라고 하면 이 현장이다 */
  site: Site | null;
  onClose: () => void;
  /** 초안을 확정해 업무 메모가 바뀌었을 때 화면을 다시 읽게 한다 */
  onDecided: () => void;
}

/** 에이전트 지침 — 허용 API 만, 읽기와 초안만, 확정은 사람. 이 지침이 없으면 에이전트가 call_api 대신 Python 을 시도하다 막힌다. */
function buildHint(site: Site | null): string {
  const lines = [
    "[공무 AI 업무 지침] 이 화면은 건설업 공무 업무판이다(현장·계약·법정/실무 업무·서류 체크).",
    "- 앱 도구 mcp__haehan-orchestrator__call_api 의 endpoint 'gongmu.*' 만 사용한다(먼저 list_api_endpoints 로 확인 가능). Python·Bash·브라우저로 읽거나 쓰지 않는다(권한 없음).",
    "- 읽기: gongmu.sites(현장) · gongmu.tasks(기한순 업무, grade=overdue/soon/unknown) · gongmu.task(근거 문구·필요 서류 준비 현황·메모).",
    "- 쓰기는 gongmu.draft(승인 대기 초안)뿐이다. kind 는 progress_billing·hq_report·subcontract_review·safety_checklist·missing_docs 중 하나. 업무 메모에 남기고 싶으면 task_id 를 넣는다. 만든 뒤 답변 끝에 응답의 id 로 [[gongmu-draft:<id>]] 를 그대로 적고 '아래 카드에서 확인 후 확정해 주세요'라고 안내한다.",
    "- 업무 상태 변경·서류 체크·확정·취소·가져오기·외부 사이트 신고/제출은 할 수 없으니 시도하지 않는다(사람이 화면에서 한다).",
    "- 금액·기한 기준과 법령 조문은 참고용이다. 단정하지 말고 '국가법령정보센터 원문 확인 필요'를 함께 안내한다. 없는 수치(공정률·손익 등)는 지어내지 말고 사용자에게 묻는다.",
    "- 협력업체 확인(업체 상태·등록업종)은 KISCON 지도 업무(www.kiscon.net)를 sitemap.run 으로 실행한다. 사업자번호 뒷자리는 사이트가 가려서 보여 주므로 업체명(+대표자)으로 찾고 동명 업체가 여럿이면 후보를 보여 준다. 법령 근거 문구는 확정된 사실로 말하지 말고 '국가법령정보센터 원문 확인 필요'를 함께 안내한다.",
    "- 결과는 한국어로 짧게 정리한다(표가 도움이 되면 표).",
  ];
  if (site) lines.push(`[현재 선택한 현장] id=${site.id}, 이름='${site.name}', 지위=${site.role === "prime" ? "원도급" : "하도급"} — 사용자가 '이 현장'이라고 하면 이 현장이다.`);
  return lines.join("\n");
}

const PRESETS: ChatPreset[] = [
  { label: "이번 주 할 일 요약", prompt: "기한이 지났거나 임박한 공무 업무를 현장별로 표로 정리해줘 (업무·기한·상태·필요 서류 중 빠진 것)." },
  { label: "서류 누락 요약", prompt: "이 현장의 진행 중인 업무에서 아직 준비되지 않은 서류를 모아 '서류 누락 요약' 초안으로 만들어줘." },
  { label: "기성 청구 내역서 초안", prompt: "이 현장의 기성 청구 내역서 초안을 만들어줘. 기성 기간·금액: " },
  { label: "본사 보고서 초안", prompt: "이번 달 본사 정기 보고서(공정률·손익 현황) 초안을 만들어줘. 공정률·손익 수치: " },
  { label: "하도급 계약 검토표", prompt: "하도급 계약 검토 체크리스트 초안을 만들어줘. 대상 계약(협력업체·금액): " },
  { label: "안전서류 점검표", prompt: "이 현장 착공 단계의 안전서류 작성 점검표 초안을 만들어줘." },
];

/** 답변 끝의 [[gongmu-draft:<id>]] 를 공무 초안 승인 카드로 바꾼다(공용 채팅에 주입). */
function cardsFor(onDecided: () => void): ExtraCard[] {
  return [
    { mark: /\[\[gongmu-draft:([0-9a-f]{32})\]\]/g, render: (id) => <GongmuDraftCard draftId={id} onDecided={onDecided} /> },
    { mark: /\[\[sitemap-explore:([0-9a-f]{32})\]\]/g, render: (id) => <SiteMapExploreCard requestId={id} /> },
  ];
}

export function GongmuAiPanel({ site, onClose, onDecided }: Props) {
  const [tab, setTab] = useState<"chat" | "drafts">("chat");
  const [drafts, setDrafts] = useState<Draft[]>([]);

  const loadDrafts = useCallback(() => {
    gongmuApi.drafts("pending").then(setDrafts).catch(() => setDrafts([]));
  }, []);

  useEffect(() => {
    loadDrafts();
  }, [loadDrafts]);

  const hint = useMemo(() => buildHint(site), [site]);
  const decided = useCallback(() => {
    loadDrafts();
    onDecided();
  }, [loadDrafts, onDecided]);
  const cards = useMemo(() => cardsFor(decided), [decided]);

  const tabBtn = (key: "chat" | "drafts", label: string) => (
    <button
      type="button"
      onClick={() => {
        setTab(key);
        if (key === "drafts") loadDrafts();
      }}
      className="rounded-full px-3 py-[3px] text-[12px]"
      style={{
        background: tab === key ? "#FFF7ED" : "#F3F4F6",
        color: tab === key ? "#C2410C" : "#6B7280",
        border: tab === key ? "1px solid #FED7AA" : "1px solid transparent",
        fontWeight: tab === key ? 600 : 400,
      }}
    >
      {label}
    </button>
  );

  return (
    <aside aria-label="공무 AI 업무 창" className="flex h-[560px] min-h-0 w-full flex-col overflow-hidden rounded-xl border border-[#E5E7EB] bg-white">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[#F3F4F6] px-3 py-2">
        <div className="flex items-center gap-1">
          {tabBtn("chat", "AI 대화")}
          {tabBtn("drafts", `승인 대기 ${drafts.length}`)}
        </div>
        <button type="button" onClick={onClose} aria-label="AI 창 닫기" className="px-1 text-[18px] leading-none text-[#9CA3AF] hover:text-[#374151]">×</button>
      </div>
      <div className="shrink-0 bg-amber-50 px-3 py-1 text-[11px] text-amber-900">
        대화에 쓰인 계약 금액·협력업체 정보는 AI 대화 기록에 남습니다. 인증서·비밀번호는 입력하지 마세요. 확정·상태 변경은 사람이 합니다.
      </div>
      {/* 대화는 탭을 바꿔도 사라지지 않게 숨기기만 한다 */}
      <div className={`min-h-0 flex-1 ${tab === "chat" ? "flex" : "hidden"}`}>
        <UniversalChat domain="gongmu" agentHint={hint} presets={PRESETS} extraCards={cards} title="공무 업무 지시 — 무엇을 할지 자세히 적어 주세요" className="h-full min-h-0 w-full flex-1 rounded-none border-0" />
      </div>
      <div className={`min-h-0 flex-1 overflow-y-auto p-3 ${tab === "drafts" ? "block" : "hidden"}`}>
        {drafts.length === 0 && <p className="py-8 text-center text-[12px] text-[#9CA3AF]">승인 대기 중인 공무 초안이 없습니다.<br />AI 대화에서 “기성 청구 내역서 초안 만들어줘”라고 지시해 보세요.</p>}
        {drafts.map((d) => (
          <GongmuDraftCard key={d.id} draftId={d.id} onDecided={decided} />
        ))}
      </div>
    </aside>
  );
}
