"use client";

import { useEffect, useState, useCallback } from "react";

type CandidateTopic = {
  keyword: string;
  question_title: string;
  question_description: string;
  search_volume: number;
  cafe_freq: number;
  competition: string;
};

type PostedItem = {
  title: string;
  topic: string;
  tags: string[];
  log_no: string;
  posted_at: string;
};

type Package = {
  id: string;
  created_at: string;
  topic: string;
  status: string;
  blog: {
    title: string;
    body: string;
    tags: string[];
    seo: { ok?: boolean; warnings?: string[]; ai_ratio?: number };
  };
  youtube: { ok?: boolean; script?: string };
  shorts: { ok?: boolean; scripts?: string };
  instagram: { ok?: boolean; caption?: string };
  publish_log: Array<{ at: string; ok?: boolean; channel?: string; action?: string; log_no?: string }>;
};

type State = {
  ok: boolean;
  candidate_topics: CandidateTopic[];
  recent_posted: PostedItem[];
  blog_analytics_summary: unknown;
  packages: Package[];
};

type Neighbor = {
  nickname: string;
  blog_title: string;
  blog_id: string;
  group: string;
  is_mutual: boolean;
  new_post_alert: boolean;
  last_post: string;
  added_at: string;
};

type NeighborsState = {
  ok: boolean;
  cached: boolean;
  generated_at?: string;
  total: number;
  active: number;
  dormant: number;
  neighbors: Neighbor[];
};

async function postJson(url: string, body: unknown) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

export default function MarketingOpsClient() {
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState<string | null>(null);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, string>>({});
  const [neighbors, setNeighbors] = useState<NeighborsState | null>(null);
  const [neighborsLoading, setNeighborsLoading] = useState(false);
  const [neighborFilter, setNeighborFilter] = useState<"all" | "active" | "dormant">("all");

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/naver/marketing-ops/state", { cache: "no-store" });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error || "조회 실패");
        return;
      }
      setState(data);
      setError(null);
    } catch {
      setError("백엔드 서버에 연결할 수 없습니다.");
    }
  }, []);

  const loadNeighbors = useCallback(async () => {
    const res = await fetch("/api/naver/marketing-ops/neighbors", { cache: "no-store" });
    const data = await res.json();
    setNeighbors(data);
  }, []);

  const refreshNeighbors = async () => {
    setNeighborsLoading(true);
    try {
      const data = await postJson("/api/naver/marketing-ops/neighbors/refresh", {});
      if (!data.ok) {
        alert(`이웃 목록 조회 실패: ${data.error || "알 수 없는 오류"}`);
      }
      await loadNeighbors();
    } finally {
      setNeighborsLoading(false);
    }
  };

  useEffect(() => {
    load();
    loadNeighbors();
  }, [load, loadNeighbors]);

  const isDormant = (n: Neighbor) => {
    if (!n.last_post || n.last_post === "-") return true;
    const [y, m, d] = n.last_post.replace(/\.$/, "").split(".").map(Number);
    if (!y) return true;
    const last = new Date(2000 + y, (m || 1) - 1, d || 1);
    return (Date.now() - last.getTime()) / 86400000 > 90;
  };

  const filteredNeighbors = (neighbors?.neighbors || []).filter((n) => {
    if (neighborFilter === "active") return !isDormant(n);
    if (neighborFilter === "dormant") return isDormant(n);
    return true;
  });

  const handleGenerate = async (topic: CandidateTopic) => {
    setGenerating(topic.question_title);
    try {
      const data = await postJson("/api/naver/marketing-ops/generate-package", {
        topic: topic.question_title,
        keyword: topic.keyword,
        source_description: topic.question_description,
      });
      if (!data.ok) {
        alert(`생성 실패: ${data.error || "알 수 없는 오류"}`);
      }
      await load();
    } finally {
      setGenerating(null);
    }
  };

  const handlePublishBlog = async (pkg: Package) => {
    if (!confirm(`"${pkg.blog.title}" — 실제로 네이버 블로그에 공개 발행합니다. 진행할까요?`)) return;
    setPublishing(pkg.id);
    try {
      const data = await postJson("/api/naver/marketing-ops/publish-blog", {
        package_id: pkg.id,
        confirmed: true,
      });
      if (!data.ok) {
        alert(`발행 실패: ${data.result?.error || data.error || "알 수 없는 오류"}`);
      } else {
        alert("발행 완료");
      }
      await load();
    } finally {
      setPublishing(null);
    }
  };

  const handleApproveChannel = async (pkg: Package, channel: string) => {
    const data = await postJson("/api/naver/marketing-ops/approve-channel", {
      package_id: pkg.id,
      channel,
    });
    alert(data.message || (data.ok ? "승인됨" : "실패"));
    await load();
  };

  const toggle = (pkgId: string, section: string) => {
    const key = `${pkgId}:${section}`;
    setExpanded((prev) => ({ ...prev, [key]: prev[key] ? "" : "open" }));
  };
  const isOpen = (pkgId: string, section: string) => !!expanded[`${pkgId}:${section}`];

  if (error) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        {error}
      </div>
    );
  }
  if (!state) {
    return <div className="text-sm text-gray-400">불러오는 중…</div>;
  }

  return (
    <div className="space-y-8">
      {/* 오늘의 후보 주제 */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-gray-700">🔥 실측 데이터 기반 후보 주제</h2>
        <div className="grid gap-2">
          {state.candidate_topics.length === 0 && (
            <p className="text-sm text-gray-400">후보 주제가 없습니다 — 리서치 파이프라인을 먼저 실행하세요.</p>
          )}
          {state.candidate_topics.map((t) => (
            <div
              key={t.question_title}
              className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-3"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-gray-800">{t.question_title}</p>
                <p className="mt-0.5 text-xs text-gray-400">
                  {t.keyword} · 월검색 {t.search_volume.toLocaleString()} · 경쟁 {t.competition}
                </p>
              </div>
              <button
                onClick={() => handleGenerate(t)}
                disabled={generating === t.question_title}
                className="ml-3 shrink-0 rounded-md bg-[#1a3a5c] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
              >
                {generating === t.question_title ? "생성 중…" : "콘텐츠 생성"}
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* 생성된 패키지 */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-gray-700">📦 콘텐츠 패키지 (미리보기 → 승인 → 게시)</h2>
        <div className="space-y-4">
          {state.packages.length === 0 && (
            <p className="text-sm text-gray-400">아직 생성된 패키지가 없습니다.</p>
          )}
          {state.packages.map((pkg) => (
            <div key={pkg.id} className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-gray-800">{pkg.blog.title}</p>
                  <p className="mt-0.5 text-xs text-gray-400">
                    {pkg.topic} · {new Date(pkg.created_at).toLocaleString("ko-KR")} ·{" "}
                    <span
                      className={
                        pkg.status === "published"
                          ? "text-emerald-600"
                          : pkg.status === "publish_failed"
                            ? "text-red-500"
                            : "text-amber-600"
                      }
                    >
                      {pkg.status}
                    </span>
                  </p>
                </div>
                <button
                  onClick={() => handlePublishBlog(pkg)}
                  disabled={publishing === pkg.id || pkg.status === "published"}
                  className="shrink-0 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
                >
                  {publishing === pkg.id ? "발행 중…" : pkg.status === "published" ? "발행됨" : "블로그 승인·발행"}
                </button>
              </div>

              {pkg.blog.seo && (
                <p className="mt-2 text-xs text-gray-500">
                  SEO: {pkg.blog.seo.ok ? "✅ 통과" : `⚠ ${(pkg.blog.seo.warnings || []).join(" / ")}`} · AI비중{" "}
                  {Math.round((pkg.blog.seo.ai_ratio || 0) * 100)}%
                </p>
              )}

              <div className="mt-3 flex flex-wrap gap-2">
                {(["blog", "youtube", "shorts", "instagram"] as const).map((sec) => (
                  <button
                    key={sec}
                    onClick={() => toggle(pkg.id, sec)}
                    className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                  >
                    {sec === "blog" ? "블로그 본문" : sec === "youtube" ? "유튜브 대본" : sec === "shorts" ? "쇼츠 3편" : "인스타 캡션"}
                    {isOpen(pkg.id, sec) ? " ▲" : " ▼"}
                  </button>
                ))}
              </div>

              {isOpen(pkg.id, "blog") && (
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">
                  {pkg.blog.body}
                </pre>
              )}
              {isOpen(pkg.id, "youtube") && (
                <div>
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">
                    {pkg.youtube.script || "생성 실패"}
                  </pre>
                  <button
                    onClick={() => handleApproveChannel(pkg, "youtube")}
                    className="mt-1 rounded bg-gray-100 px-2 py-1 text-xs text-gray-600 hover:bg-gray-200"
                  >
                    검토 완료 표시 (수동 게시)
                  </button>
                </div>
              )}
              {isOpen(pkg.id, "shorts") && (
                <div>
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">
                    {pkg.shorts.scripts || "생성 실패"}
                  </pre>
                  <button
                    onClick={() => handleApproveChannel(pkg, "shorts")}
                    className="mt-1 rounded bg-gray-100 px-2 py-1 text-xs text-gray-600 hover:bg-gray-200"
                  >
                    검토 완료 표시 (수동 게시)
                  </button>
                </div>
              )}
              {isOpen(pkg.id, "instagram") && (
                <div>
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">
                    {pkg.instagram.caption || "생성 실패"}
                  </pre>
                  <button
                    onClick={() => handleApproveChannel(pkg, "instagram")}
                    className="mt-1 rounded bg-gray-100 px-2 py-1 text-xs text-gray-600 hover:bg-gray-200"
                  >
                    검토 완료 표시 (수동 게시)
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* 최근 발행 이력 */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-gray-700">📝 최근 발행 이력</h2>
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left">제목</th>
                <th className="px-3 py-2 text-left">태그</th>
                <th className="px-3 py-2 text-left">발행일</th>
              </tr>
            </thead>
            <tbody>
              {state.recent_posted.map((p) => (
                <tr key={p.log_no} className="border-t border-gray-100">
                  <td className="px-3 py-2 text-gray-700">
                    <a
                      href={`https://blog.naver.com/skyjwsin/${p.log_no}`}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:underline"
                    >
                      {p.title}
                    </a>
                  </td>
                  <td className="px-3 py-2 text-gray-500">{(p.tags || []).join(", ")}</td>
                  <td className="px-3 py-2 text-gray-400">
                    {p.posted_at ? new Date(p.posted_at).toLocaleDateString("ko-KR") : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 블로그 이웃 */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700">
            🧑‍🤝‍🧑 블로그 이웃
            {neighbors && neighbors.total > 0 && (
              <span className="ml-2 font-normal text-gray-400">
                전체 {neighbors.total} · 활성 {neighbors.active} · 휴면 {neighbors.dormant}
                {neighbors.generated_at && (
                  <> · {new Date(neighbors.generated_at).toLocaleString("ko-KR")} 기준</>
                )}
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            <div className="flex rounded-md border border-gray-200 text-xs">
              {(["all", "active", "dormant"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setNeighborFilter(f)}
                  className={`px-2 py-1 ${neighborFilter === f ? "bg-[#1a3a5c] text-white" : "text-gray-600"}`}
                >
                  {f === "all" ? "전체" : f === "active" ? "활성" : "휴면(90일+)"}
                </button>
              ))}
            </div>
            <button
              onClick={refreshNeighbors}
              disabled={neighborsLoading}
              className="rounded-md bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50"
            >
              {neighborsLoading ? "조회 중… (최대 20초)" : "새로고침"}
            </button>
          </div>
        </div>

        {!neighbors?.cached && !neighborsLoading && (
          <p className="text-sm text-gray-400">아직 조회된 이웃 목록이 없습니다 — 새로고침을 눌러주세요.</p>
        )}

        {filteredNeighbors.length > 0 && (
          <div className="max-h-96 overflow-y-auto rounded-lg border border-gray-200 bg-white">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-gray-50 text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left">별명</th>
                  <th className="px-3 py-2 text-left">블로그</th>
                  <th className="px-3 py-2 text-left">그룹</th>
                  <th className="px-3 py-2 text-left">관계</th>
                  <th className="px-3 py-2 text-left">최근 글</th>
                  <th className="px-3 py-2 text-left">이웃 추가일</th>
                </tr>
              </thead>
              <tbody>
                {filteredNeighbors.map((n) => (
                  <tr key={`${n.blog_id}-${n.added_at}`} className="border-t border-gray-100">
                    <td className="px-3 py-2 text-gray-700">{n.nickname}</td>
                    <td className="px-3 py-2 text-gray-500">
                      <a
                        href={`https://blog.naver.com/${n.blog_id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:underline"
                      >
                        {n.blog_title}
                      </a>
                    </td>
                    <td className="px-3 py-2 text-gray-400">{n.group}</td>
                    <td className="px-3 py-2">
                      <span
                        className={
                          n.is_mutual ? "rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700" : "text-gray-400"
                        }
                      >
                        {n.is_mutual ? "서로이웃" : "이웃"}
                      </span>
                    </td>
                    <td className={`px-3 py-2 ${isDormant(n) ? "text-red-400" : "text-gray-500"}`}>
                      {n.last_post || "-"}
                    </td>
                    <td className="px-3 py-2 text-gray-400">{n.added_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
