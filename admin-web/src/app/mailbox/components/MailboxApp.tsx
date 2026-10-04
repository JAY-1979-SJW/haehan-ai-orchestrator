"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { mailboxApi, type Account, type Folder, type MessageDetail, type MessageList as MessageListData, type MessageRow } from "../lib/api";
import { buildDraft, EMPTY_DRAFT, type ComposeDraft } from "../lib/format";
import { draftApi, type Draft } from "../lib/draftApi";
import { ComposeDialog } from "./ComposeDialog";
import { FolderTree } from "./FolderTree";
import { MailAiPanel } from "./MailAiPanel";
import { MessageList, type MailFilter } from "./MessageList";
import { MessageView } from "./MessageView";
import { NewMailToast, type NewMailToastData } from "./NewMailToast";
import { useNewMailWatch, type NewMailEvent } from "../lib/useNewMailWatch";

const ALERT_KEY = "mailbox.newMailAlert";
const NOTIFY_KEY = "mailbox.browserNotify";

function readPref(key: string, fallback: boolean): boolean {
  try {
    const v = window.localStorage.getItem(key);
    return v === null ? fallback : v === "1";
  } catch {
    return fallback;
  }
}

function writePref(key: string, on: boolean) {
  try {
    window.localStorage.setItem(key, on ? "1" : "0");
  } catch {
    /* 저장이 막혀도 화면은 동작한다 */
  }
}

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

interface Confirm {
  title: string;
  message: string;
  action: string;
  onConfirm: () => void;
}

/**
 * 네이버 메일함 — 목차(폴더) · 목록 · 읽기 3단. 메일을 열어도 읽음 표시는 바뀌지 않는다(읽기 창의 버튼으로만 바꾼다).
 * 삭제·이동·읽음 표시는 화면에 먼저 반영하고(낙관적 갱신) 서버 재조회는 뒤에서 한다 — 실패하면 되돌린다.
 * 기준서: docs/specs/2026-10-01_naver_mailbox_tab.md (10절)
 */
export function MailboxApp() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [account, setAccount] = useState("");
  const [folders, setFolders] = useState<Folder[]>([]);
  const [foldersLoading, setFoldersLoading] = useState(false);
  const [folder, setFolder] = useState("INBOX");
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<MailFilter>("all");
  const [query, setQuery] = useState("");
  const [list, setList] = useState<MessageListData | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [checked, setChecked] = useState<number[]>([]);
  const [uid, setUid] = useState<number | null>(null);
  const [detail, setDetail] = useState<MessageDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [compose, setCompose] = useState<ComposeDraft | null>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiDrafts, setAiDrafts] = useState<Draft[]>([]);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [alertOn, setAlertOn] = useState(true);
  const [notifyOn, setNotifyOn] = useState(false);
  const [toast, setToast] = useState<NewMailToastData | null>(null);
  const [newCount, setNewCount] = useState(0);
  const listSeq = useRef(0);
  const detailSeq = useRef(0);
  // 열어 본(또는 마우스를 올려 미리 받은) 메일 — 같은 메일을 다시 열면 서버를 거치지 않고 바로 보여 준다
  const detailCache = useRef<Map<string, MessageDetail>>(new Map());
  const detailInflight = useRef<Map<string, Promise<MessageDetail>>>(new Map());
  const listRef = useRef<MessageListData | null>(null);
  listRef.current = list;

  const currentFolder = folders.find((f) => f.id === folder);
  const inTrash = currentFolder?.kind === "trash";

  useEffect(() => {
    mailboxApi
      .accounts()
      .then((a) => {
        setAccounts(a);
        const ready = a.find((x) => x.ready) ?? a[0];
        if (ready) setAccount(ready.account);
      })
      .catch((e) => setNotice({ kind: "err", text: errText(e) }));
  }, []);

  const loadFolders = useCallback(async (acc: string, silent = false) => {
    if (!acc) return;
    if (!silent) setFoldersLoading(true);
    try {
      setFolders(await mailboxApi.folders(acc));
    } catch (e) {
      if (!silent) setNotice({ kind: "err", text: errText(e) });
    } finally {
      if (!silent) setFoldersLoading(false);
    }
  }, []);

  /** silent=true 면 로딩 표시 없이 조용히 다시 불러온다(삭제·이동 뒤 백그라운드 확인용). */
  const loadList = useCallback(
    async (silent = false) => {
      if (!account) return;
      const seq = ++listSeq.current;
      if (!silent) {
        setListLoading(true);
        setListError(null);
      }
      try {
        const data = await mailboxApi.messages(account, folder, page, filter, query);
        if (seq === listSeq.current) {
          setList(data);
          setChecked((prev) => prev.filter((u) => data.messages.some((m) => m.uid === u)));
        }
      } catch (e) {
        if (seq === listSeq.current && !silent) {
          setList(null);
          setListError(errText(e));
        }
      } finally {
        if (seq === listSeq.current && !silent) setListLoading(false);
      }
    },
    [account, folder, page, filter, query],
  );

  useEffect(() => {
    void loadFolders(account);
  }, [account, loadFolders]);

  useEffect(() => {
    setChecked([]);
    void loadList();
  }, [loadList]);

  /** AI 가 만든 승인 대기 초안 — 배지와 '승인 대기' 탭에 쓴다. */
  const loadDrafts = useCallback(async () => {
    if (!account) return;
    try {
      setAiDrafts(await draftApi.list(account));
    } catch {
      /* 초안 목록을 못 읽어도 메일 화면은 계속 쓸 수 있다 */
    }
  }, [account]);

  useEffect(() => {
    void loadDrafts();
    const timer = setInterval(() => void loadDrafts(), aiOpen ? 5000 : 20000);
    return () => clearInterval(timer);
  }, [loadDrafts, aiOpen]);

  useEffect(() => {
    setAlertOn(readPref(ALERT_KEY, true));
    setNotifyOn(readPref(NOTIFY_KEY, false) && typeof Notification !== "undefined" && Notification.permission === "granted");
  }, []);

  /** 새 메일 도착 — 토스트·목차 안 읽음 수·(받은편지함을 보는 중이면) 목록·탭 제목을 갱신한다. 읽음 표시는 바꾸지 않는다. */
  const handleNewMail = useCallback(
    async (e: NewMailEvent) => {
      setFolders((prev) => prev.map((f) => (f.id === "INBOX" ? { ...f, unseen: e.unseen } : f)));
      if (e.count === 0) return;
      setNewCount((n) => n + e.count);
      let from = "";
      let subject = "";
      try {
        const first = await mailboxApi.messages(account, "INBOX", 1, "all", "");
        const fresh = first.messages.filter((m) => m.uid >= e.sinceUid);
        const top = fresh[0] ?? first.messages[0];
        if (top) {
          from = top.from.name || top.from.address;
          subject = top.subject;
        }
      } catch {
        /* 내용을 못 읽어도 개수는 알린다 */
      }
      setToast({ label: e.label, from, subject });
      if (folder === "INBOX" && page === 1) void loadList(true);
      if (notifyOn && document.visibilityState !== "visible") {
        new Notification(`새 메일 ${e.label}통`, { body: [from, subject].filter(Boolean).join(" — ") });
      }
    },
    [account, folder, page, loadList, notifyOn],
  );

  useNewMailWatch(account, alertOn, (e) => void handleNewMail(e));

  useEffect(() => {
    const base = "메일함";
    document.title = newCount > 0 ? `(${newCount}) ${base}` : base;
    const clear = () => {
      if (document.visibilityState === "visible") setNewCount(0);
    };
    document.addEventListener("visibilitychange", clear);
    return () => {
      document.removeEventListener("visibilitychange", clear);
      document.title = base;
    };
  }, [newCount]);

  async function toggleNotify() {
    if (notifyOn) {
      setNotifyOn(false);
      writePref(NOTIFY_KEY, false);
      return;
    }
    if (typeof Notification === "undefined") return;
    const perm = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    const on = perm === "granted";
    setNotifyOn(on);
    writePref(NOTIFY_KEY, on);
  }

  const detailKey = useCallback((u: number) => `${account}|${folder}|${u}`, [account, folder]);

  /** 메일 상세를 받아 캐시에 넣는다(같은 메일을 동시에 두 번 요청하지 않는다). */
  const fetchDetail = useCallback(
    (u: number): Promise<MessageDetail> => {
      const key = detailKey(u);
      const hit = detailCache.current.get(key);
      if (hit) return Promise.resolve(hit);
      const running = detailInflight.current.get(key);
      if (running) return running;
      const p = mailboxApi
        .message(account, folder, u)
        .then((d) => {
          detailCache.current.set(key, d);
          if (detailCache.current.size > 30) detailCache.current.delete(detailCache.current.keys().next().value as string);
          return d;
        })
        .finally(() => detailInflight.current.delete(key));
      detailInflight.current.set(key, p);
      return p;
    },
    [account, folder, detailKey],
  );

  /** 마우스를 올린 메일을 미리 받아 둔다 — 클릭하면 바로 열린다. 실패는 무시(클릭할 때 다시 시도). */
  const prefetch = useCallback(
    (u: number) => {
      if (!account || detailCache.current.has(detailKey(u))) return;
      fetchDetail(u).catch(() => undefined);
    },
    [account, detailKey, fetchDetail],
  );

  /** 목차에서 폴더 위에 머물면 그 폴더의 첫 페이지를 서버에 미리 받아 두게 한다(1분에 한 번만). */
  const warmedFolders = useRef<Map<string, number>>(new Map());
  const prefetchFolder = useCallback(
    (f: Folder) => {
      if (!account || !f.selectable || f.id === folder || f.total === 0) return;
      const key = `${account}|${f.id}`;
      const last = warmedFolders.current.get(key) ?? 0;
      if (Date.now() - last < 60_000) return;
      warmedFolders.current.set(key, Date.now());
      mailboxApi.messages(account, f.id, 1, "all", "").catch(() => undefined);
    },
    [account, folder],
  );

  // 메일 열기 — 읽음 표시는 바뀌지 않는다
  useEffect(() => {
    if (!account || uid === null) {
      setDetail(null);
      return;
    }
    const seq = ++detailSeq.current;
    const cached = detailCache.current.get(detailKey(uid));
    if (cached) {
      // 읽음 표시는 목록의 최신 값을 따른다(캐시는 본문만 보관)
      const row = listRef.current?.messages.find((m) => m.uid === uid);
      setDetail({ ...cached, seen: row ? row.seen : cached.seen });
      setDetailLoading(false);
      setDetailError(null);
      return;
    }
    setDetail(null); // 이전 메일이 남아 있으면 클릭이 먹통처럼 보인다 — 즉시 비우고 제목 등은 목록 정보로 보여 준다
    setDetailLoading(true);
    setDetailError(null);
    fetchDetail(uid)
      .then((d) => seq === detailSeq.current && setDetail(d))
      .catch((e) => {
        if (seq === detailSeq.current) {
          setDetail(null);
          setDetailError(errText(e));
        }
      })
      .finally(() => seq === detailSeq.current && setDetailLoading(false));
  }, [account, uid, detailKey, fetchDetail]);

  function selectFolder(id: string) {
    setFolder(id);
    setPage(1);
    setUid(null);
    setList(null);
    setChecked([]);
  }

  // ── 낙관적 갱신 도우미 ──────────────────────────────────────────────
  const rowsOf = (uids: number[]): MessageRow[] => (list?.messages ?? []).filter((m) => uids.includes(m.uid));

  /** 폴더별 전체/안 읽은 수를 로컬에서 먼저 고친다(서버 재조회 전). */
  function adjustFolders(source: string, dest: string | null, rows: MessageRow[]) {
    const unseen = rows.filter((r) => !r.seen).length;
    setFolders((prev) =>
      prev.map((f) => {
        if (f.id === source) return { ...f, total: Math.max(0, f.total - rows.length), unseen: Math.max(0, f.unseen - unseen) };
        if (dest && f.id === dest) return { ...f, total: f.total + rows.length, unseen: f.unseen + unseen };
        return f;
      }),
    );
  }

  /** 화면에서 먼저 행을 지우고 서버 작업은 뒤에서 — 실패하면 원래대로 되돌리고 알린다. */
  async function removeRows(uids: number[], dest: string | null, run: () => Promise<unknown>, okText: string) {
    const rows = rowsOf(uids);
    uids.forEach((u) => detailCache.current.delete(detailKey(u))); // 옮기거나 지운 메일은 캐시에서도 뺀다
    const before = { list, folders, uid, checked };
    setList((prev) => (prev ? { ...prev, total: Math.max(0, prev.total - uids.length), messages: prev.messages.filter((m) => !uids.includes(m.uid)) } : prev));
    adjustFolders(folder, dest, rows);
    setChecked([]);
    if (uid !== null && uids.includes(uid)) setUid(null);
    setNotice({ kind: "ok", text: okText });
    try {
      await run();
      void loadList(true);
      void loadFolders(account, true);
    } catch (e) {
      setList(before.list);
      setFolders(before.folders);
      setChecked(before.checked);
      setUid(before.uid);
      setNotice({ kind: "err", text: errText(e) });
    }
  }

  const targets = (): number[] => (checked.length ? checked : uid !== null ? [uid] : []);

  function trashSelected(uids = targets()) {
    if (!uids.length) return;
    void removeRows(uids, null, () => mailboxApi.trash(account, folder, uids), `${uids.length}통을 휴지통으로 옮겼습니다.`);
  }

  function moveSelected(dest: Folder, uids = targets()) {
    if (!uids.length) return;
    void removeRows(uids, dest.id, () => mailboxApi.move(account, folder, uids, dest.id), `${uids.length}통을 '${dest.name}'(으)로 옮겼습니다.`);
  }

  function purgeSelected() {
    const uids = checked;
    if (!uids.length) return;
    setConfirm({
      title: "영구 삭제",
      message: `선택한 ${uids.length}통을 영구 삭제합니다. 되돌릴 수 없습니다.`,
      action: "영구 삭제",
      onConfirm: () => void removeRows(uids, null, () => mailboxApi.purge(account, folder, uids), `${uids.length}통을 영구 삭제했습니다.`),
    });
  }

  function emptyFolder(f: Folder) {
    setConfirm({
      title: `${f.name} 비우기`,
      message: `'${f.name}'의 메일 ${f.total}통을 모두 영구 삭제합니다. 되돌릴 수 없습니다.`,
      action: "모두 삭제",
      onConfirm: async () => {
        const before = folders;
        setFolders((prev) => prev.map((x) => (x.id === f.id ? { ...x, total: 0, unseen: 0 } : x)));
        if (f.id === folder) {
          setList((prev) => (prev ? { ...prev, total: 0, messages: [] } : prev));
          setUid(null);
          setChecked([]);
        }
        setNotice({ kind: "ok", text: `${f.name}을(를) 비웠습니다.` });
        try {
          await mailboxApi.emptyFolder(account, f.id);
          void loadFolders(account, true);
          if (f.id === folder) void loadList(true);
        } catch (e) {
          setFolders(before);
          setNotice({ kind: "err", text: errText(e) });
          void loadList(true);
        }
      },
    });
  }

  async function setSeenFor(uids: number[], seen: boolean) {
    if (!uids.length) return;
    const rows = rowsOf(uids).filter((r) => r.seen !== seen);
    const delta = rows.length * (seen ? -1 : 1);
    const before = { list, folders, detail };
    setList((prev) => (prev ? { ...prev, messages: prev.messages.map((m) => (uids.includes(m.uid) ? { ...m, seen } : m)) } : prev));
    setFolders((prev) => prev.map((f) => (f.id === folder ? { ...f, unseen: Math.max(0, f.unseen + delta) } : f)));
    if (detail && uids.includes(detail.uid)) setDetail({ ...detail, seen });
    try {
      await mailboxApi.setSeen(account, folder, uids, seen);
      void loadFolders(account, true);
    } catch (e) {
      setList(before.list);
      setFolders(before.folders);
      setDetail(before.detail);
      setNotice({ kind: "err", text: errText(e) });
    }
  }

  function openCompose(mode: "reply" | "replyAll" | "forward") {
    if (detail) setCompose(buildDraft(mode, detail, `${account}@naver.com`));
  }

  const showView = uid !== null;

  return (
    <div className="flex h-[calc(100dvh-132px)] min-h-[520px] flex-col gap-2">
      {toast && (
        <NewMailToast
          data={toast}
          onClose={() => setToast(null)}
          onOpen={() => { setToast(null); selectFolder("INBOX"); setNewCount(0); }}
        />
      )}
      <div className="flex shrink-0 items-center gap-3">
        <label className="flex items-center gap-2 text-[12px] text-[#6B7280]">
          계정
          <select value={account} onChange={(e) => { setAccount(e.target.value); selectFolder("INBOX"); }} className="rounded-lg border border-[#E5E7EB] bg-white px-2 py-1 text-[13px] text-[#111827]">
            {accounts.map((a) => (
              <option key={a.account} value={a.account} disabled={!a.ready}>
                {a.account}@naver.com{a.ready ? "" : " (앱 비밀번호 없음)"}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => setAiOpen((v) => !v)}
          aria-pressed={aiOpen}
          className="hidden shrink-0 items-center gap-1 rounded-lg border px-3 py-1 text-[12px] lg:flex"
          style={{ background: aiOpen ? "#FFF7ED" : "#FFFFFF", borderColor: aiOpen ? "#FED7AA" : "#E5E7EB", color: aiOpen ? "#C2410C" : "#374151", fontWeight: aiOpen ? 600 : 400 }}
        >
          🤖 AI 업무 창
          {aiDrafts.length > 0 && <span className="rounded-full bg-[#F97316] px-[7px] py-px text-[10px] font-bold text-white">{aiDrafts.length}</span>}
        </button>
        <Link href="/mailbox/bulk" className="hidden shrink-0 rounded-lg border border-[#E5E7EB] bg-white px-3 py-1 text-[12px] text-[#374151] lg:block">
          📨 대량 발송
        </Link>
        <label className="hidden shrink-0 items-center gap-1 text-[12px] text-[#6B7280] lg:flex">
          <input type="checkbox" checked={alertOn} onChange={(e) => { setAlertOn(e.target.checked); writePref(ALERT_KEY, e.target.checked); }} />
          새 메일 알림
        </label>
        {alertOn && (
          <label className="hidden shrink-0 items-center gap-1 text-[12px] text-[#6B7280] lg:flex">
            <input type="checkbox" checked={notifyOn} onChange={() => void toggleNotify()} />
            브라우저 알림
          </label>
        )}
        {notice && (
          <div role="status" className="min-w-0 flex-1 truncate rounded-lg px-3 py-1 text-[12px]" style={{ background: notice.kind === "ok" ? "#ECFDF5" : "#FEF2F2", color: notice.kind === "ok" ? "#047857" : "#B91C1C" }}>
            {notice.text}
            <button type="button" className="ml-2 underline" onClick={() => setNotice(null)}>닫기</button>
          </div>
        )}
      </div>

      <div className="flex min-h-0 flex-1 gap-2">
      <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 overflow-hidden rounded-xl border border-[#E5E7EB] bg-white lg:grid-cols-[210px_minmax(300px,380px)_1fr]">
        <div className="hidden min-h-0 border-r border-[#F3F4F6] lg:block">
          <FolderTree folders={folders} current={folder} onSelect={selectFolder} onCompose={() => setCompose({ ...EMPTY_DRAFT })} onEmpty={emptyFolder} onHover={prefetchFolder} loading={foldersLoading} />
        </div>
        <div className={`min-h-0 border-r border-[#F3F4F6] ${showView ? "hidden lg:block" : ""}`}>
          <MessageList
            data={list}
            loading={listLoading}
            error={listError}
            selectedUid={uid}
            checked={checked}
            filter={filter}
            query={query}
            folder={currentFolder}
            folders={folders}
            onSelect={setUid}
            onHover={prefetch}
            onCheck={(u, on) => setChecked((prev) => (on ? [...prev, u] : prev.filter((x) => x !== u)))}
            onCheckAll={(on) => setChecked(on ? (list?.messages ?? []).map((m) => m.uid) : [])}
            onFilter={(f) => { setFilter(f); setPage(1); }}
            onSearch={(q) => { setQuery(q); setPage(1); }}
            onPage={setPage}
            onRefresh={() => { void loadList(); void loadFolders(account); }}
            onTrash={() => trashSelected(checked)}
            onMove={(dest) => moveSelected(dest, checked)}
            onSeen={(seen) => void setSeenFor(checked, seen)}
            onPurge={purgeSelected}
            onEmpty={() => currentFolder && emptyFolder(currentFolder)}
          />
        </div>
        <div className={`min-h-0 ${showView ? "" : "hidden lg:block"}`}>
          {showView && (
            <button type="button" onClick={() => setUid(null)} className="w-full border-b border-[#F3F4F6] px-4 py-2 text-left text-[12px] text-[#6B7280] lg:hidden">← 목록으로</button>
          )}
          <MessageView
            account={account}
            pending={uid !== null ? (list?.messages.find((m) => m.uid === uid) ?? null) : null}
            detail={detail}
            loading={detailLoading}
            error={detailError}
            inTrash={inTrash}
            folders={folders}
            onMove={(dest) => detail && moveSelected(dest, [detail.uid])}
            onReply={() => openCompose("reply")}
            onReplyAll={() => openCompose("replyAll")}
            onForward={() => openCompose("forward")}
            onTrash={() => detail && trashSelected([detail.uid])}
            onToggleSeen={() => detail && void setSeenFor([detail.uid], !detail.seen)}
          />
        </div>
      </div>

      {aiOpen && (
        <div className="hidden min-h-0 w-[380px] shrink-0 lg:block xl:w-[420px]">
          <MailAiPanel account={account} openMail={detail} drafts={aiDrafts} onClose={() => setAiOpen(false)} onDraftsChanged={() => void loadDrafts()} />
        </div>
      )}
      </div>

      {compose && (
        <ComposeDialog
          account={account}
          initial={compose}
          onClose={() => setCompose(null)}
          onSent={(recipients) => {
            setCompose(null);
            setNotice({ kind: "ok", text: `메일을 보냈습니다 (${recipients.join(", ")})` });
            void loadFolders(account, true);
            void loadList(true);
          }}
        />
      )}

      <Modal
        open={confirm !== null}
        title={confirm?.title ?? ""}
        onClose={() => setConfirm(null)}
        footer={
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setConfirm(null)} className="rounded-xl border border-[#E5E7EB] px-4 py-[7px] text-[13px] text-[#374151] hover:bg-[#F9FAFB]">취소</button>
            <button
              type="button"
              onClick={() => {
                const run = confirm?.onConfirm;
                setConfirm(null);
                run?.();
              }}
              className="rounded-xl bg-[#B91C1C] px-4 py-[7px] text-[13px] font-semibold text-white hover:bg-[#991B1B]"
            >
              {confirm?.action}
            </button>
          </div>
        }
      >
        {confirm?.message}
      </Modal>
    </div>
  );
}
