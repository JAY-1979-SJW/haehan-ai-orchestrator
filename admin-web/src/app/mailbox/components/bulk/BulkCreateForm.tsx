"use client";

import { useState } from "react";
import { bulkApi, estimate, type BulkAuthorization, type BulkKind, type BulkRecipient } from "../../lib/bulkApi";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const field = "w-full rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-[13px] text-[#111827]";
const label = "mb-1 block text-[12px] font-medium text-[#374151]";

/** 붙여넣은 줄("이메일, 이름, 업체명")을 수신자로 바꾼다. 형식 검사는 서버가 한다(틀린 주소가 있으면 만들기가 거부된다). */
function parsePasted(text: string): BulkRecipient[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [email = "", name = "", company = ""] = line.split(/[,\t]/).map((s) => s.trim());
      return { email, name, company };
    });
}

/**
 * 새 대량 발송(승인서) 만들기. 만든 뒤에는 수정할 수 없고(범위 고정), 시험 발송 → 승인 순서로 진행한다.
 * 기준서: docs/specs/2026-10-02_mail_bulk_sequential.md §2
 */
export function BulkCreateForm({ account, onCreated, onCancel }: { account: string; onCreated: (a: BulkAuthorization) => void; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<BulkKind>("transaction");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [pasted, setPasted] = useState("");
  const [importPath, setImportPath] = useState("");
  const [importNote, setImportNote] = useState("");
  const [attach, setAttach] = useState("");
  const [perDay, setPerDay] = useState(200);
  const [interval, setIntervalSec] = useState(30);
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("18:00");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const recipients = parsePasted(pasted);
  const est = estimate(recipients.length, perDay, interval);

  async function doImport() {
    setError("");
    setImportNote("");
    try {
      const r = await bulkApi.importFile(importPath.trim());
      setPasted(r.recipients.map((x) => [x.email, x.name, x.company].join(", ")).join("\n"));
      const s = r.stats;
      setImportNote(`사용 ${s.usable}명 · 잘못된 주소 ${s.invalid} · 중복 ${s.duplicate} · 수신거부 ${s.opted_out} (전체 ${s.rows}줄)`);
    } catch (e) {
      setError(errText(e));
    }
  }

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const created = await bulkApi.create({
        account,
        name,
        kind,
        subject,
        body,
        recipients,
        attachment_paths: attach.split(/\r?\n/).map((s) => s.trim()).filter(Boolean),
        interval_sec: interval,
        max_per_day: perDay,
        allowed_start: start,
        allowed_end: end,
      });
      onCreated(created);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
      <h2 className="text-[15px] font-semibold text-[#111827]">새 대량 발송 만들기</h2>
      <p className="text-[12px] text-[#6B7280]">
        만든 뒤에는 수신자·제목·본문을 수정할 수 없습니다(바꾸려면 새로 만듭니다). 수신자마다 따로 한 통씩, 간격을 두고 차례로 보냅니다.
      </p>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div>
          <label className={label}>이름(관리용)</label>
          <input className={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 10월 단말기 임대 안내" />
        </div>
        <div>
          <label className={label}>메일 성격</label>
          <select className={field} value={kind} onChange={(e) => setKind(e.target.value as BulkKind)}>
            <option value="transaction">거래·업무 안내</option>
            <option value="promo">홍보·광고</option>
          </select>
        </div>
      </div>
      {kind === "promo" && (
        <p className="rounded-lg bg-[#FFFBEB] px-3 py-2 text-[12px] text-[#92400E]">
          홍보·광고 메일은 제목이 <b>(광고)</b> 로 시작하고 본문에 <b>수신거부</b> 안내 문구가 있어야 만들 수 있습니다(정보통신망법).
        </p>
      )}

      <div>
        <label className={label}>제목</label>
        <input className={field} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="예: {업체명} 단말기 임대 안내" />
      </div>
      <div>
        <label className={label}>본문 — <code>{"{이름}"}</code> <code>{"{업체명}"}</code> 은 수신자별로 바뀝니다</label>
        <textarea className={`${field} h-40 resize-y`} value={body} onChange={(e) => setBody(e.target.value)} />
      </div>

      <div>
        <label className={label}>수신자 — 한 줄에 한 명: 이메일, 이름, 업체명</label>
        <textarea className={`${field} h-32 resize-y font-mono`} value={pasted} onChange={(e) => setPasted(e.target.value)} placeholder={"a@example.com, 김대리, 해한건설\nb@example.com, 이과장, 해한전기"} />
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <input className={`${field} max-w-md`} value={importPath} onChange={(e) => setImportPath(e.target.value)} placeholder="엑셀·CSV 주소록 경로(문서·다운로드·바탕화면 폴더 안)" />
          <button type="button" disabled={!importPath.trim()} onClick={() => void doImport()} className="rounded-lg border border-[#E5E7EB] bg-white px-3 py-1.5 text-[12px] disabled:opacity-40">
            파일에서 가져오기
          </button>
          <span className="text-[12px] text-[#6B7280]">{importNote || `현재 ${recipients.length}명`}</span>
        </div>
      </div>

      <div>
        <label className={label}>첨부 파일 경로(선택, 한 줄에 하나, 최대 5개) — 승인 뒤 파일이 바뀌면 발송이 멈춥니다</label>
        <textarea className={`${field} h-16 resize-y font-mono`} value={attach} onChange={(e) => setAttach(e.target.value)} />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div>
          <label className={label}>하루 상한(통)</label>
          <input type="number" min={1} className={field} value={perDay} onChange={(e) => setPerDay(Number(e.target.value))} />
        </div>
        <div>
          <label className={label}>건당 간격(초)</label>
          <input type="number" min={5} className={field} value={interval} onChange={(e) => setIntervalSec(Number(e.target.value))} />
        </div>
        <div>
          <label className={label}>허용 시작</label>
          <input type="time" className={field} value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div>
          <label className={label}>허용 종료</label>
          <input type="time" className={field} value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </div>
      {recipients.length > 0 && (
        <p className="text-[12px] text-[#374151]">
          예상: {recipients.length}명 ÷ 하루 {perDay}통 = <b>{est.days}일</b>, 하루 약 <b>{est.minutesPerDay}분</b> 소요(간격 ±20%). 허용 시간대 밖에는 보내지 않고 다음 날 이어서 보냅니다.
        </p>
      )}

      {error && <p role="alert" className="rounded-lg bg-[#FEF2F2] px-3 py-2 text-[12px] text-[#B91C1C]">{error}</p>}
      <div className="flex gap-2">
        <button type="button" disabled={busy || !subject.trim() || !body.trim() || recipients.length === 0} onClick={() => void submit()} className="rounded-lg bg-[#F97316] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-40">
          {busy ? "만드는 중…" : "승인서 만들기"}
        </button>
        <button type="button" onClick={onCancel} className="rounded-lg border border-[#E5E7EB] bg-white px-4 py-2 text-[13px]">취소</button>
      </div>
    </div>
  );
}
