"use client";

import { useMemo, useState } from "react";

type MarketResearchData = {
  created_at?: string;
  status?: string;
  topic?: string;
  keywords?: string[];
  unique_video_count?: number;
  markdown_report?: string;
  public_signal_model?: {
    not_officially_available?: string[];
  };
  top_videos?: Array<{
    video_id?: string;
    url?: string;
    title?: string;
    channel_title?: string;
    coverage_count?: number;
    best_observed_rank?: number;
    topic_classification?: { primary_topic?: string };
    signal_quality?: { level?: string; confidence_score?: number };
    comment_summary?: { status?: string; comment_count_observed?: number };
    transcript_summary?: { status?: string };
    scores?: { topic_opportunity_score?: number; comment_signal_score?: number };
  }>;
  topic_clusters?: Array<{
    topic?: string;
    video_count?: number;
    average_opportunity_score?: number;
  }>;
  top_channels?: Array<{
    channel_title?: string;
    video_count?: number;
    best_score?: number;
  }>;
};

type Props = {
  data: MarketResearchData | null;
  markdown: string;
  error?: string;
};

const topicOptions = [
  { value: "smartstore", label: "SmartStore" },
  { value: "purchase_agency", label: "Purchase Agency" },
  { value: "shopping_mall", label: "Shopping Mall" },
  { value: "commerce_marketing", label: "Commerce Marketing" },
  { value: "ai_work_automation", label: "AI Work Automation" },
];

export default function MarketResearchClient({ data, markdown, error }: Props) {
  const [topic, setTopic] = useState("smartstore");
  const [perKeywordLimit, setPerKeywordLimit] = useState(10);
  const [comments, setComments] = useState(100);
  const [commentPages, setCommentPages] = useState(5);
  const [collectTranscripts, setCollectTranscripts] = useState(false);
  const [transcriptVideos, setTranscriptVideos] = useState(5);
  const [running, setRunning] = useState(false);
  const [runStatus, setRunStatus] = useState<string>("");

  const command = useMemo(() => {
    const parts = [
      "python scripts\\cdp_client.py google youtube research-run",
      `--topic=${topic}`,
      "--auto-keywords",
      `--per-keyword-limit=${perKeywordLimit}`,
      "--collect-comments=true",
      `--max-comments=${comments}`,
      `--max-comment-pages=${commentPages}`,
      `--collect-transcripts=${collectTranscripts ? "true" : "false"}`,
      `--max-transcript-videos=${transcriptVideos}`,
    ];
    return parts.join(" ");
  }, [topic, perKeywordLimit, comments, commentPages, collectTranscripts, transcriptVideos]);

  const videos = data?.top_videos ?? [];
  const clusters = data?.topic_clusters ?? [];
  const channels = data?.top_channels ?? [];

  async function runResearch() {
    setRunning(true);
    setRunStatus("Running market research...");
    try {
      const response = await fetch("/api/market-research/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          perKeywordLimit,
          comments,
          commentPages,
          collectTranscripts,
          transcriptVideos,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        setRunStatus(`Failed: ${payload.reason || payload.error || "unknown_error"}`);
        return;
      }
      setRunStatus("Completed. Reloading latest report...");
      window.location.reload();
    } catch (err) {
      setRunStatus(`Failed: ${err instanceof Error ? err.message : "unknown_error"}`);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-5">
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Status" value={data?.status ?? "No data"} />
        <Metric label="Videos" value={String(data?.unique_video_count ?? 0)} />
        <Metric label="Keywords" value={String(data?.keywords?.length ?? 0)} />
        <Metric label="Updated" value={formatDate(data?.created_at)} />
      </section>

      {error && (
        <section className="border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </section>
      )}

      <section className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <div className="border border-[#E5E7EB] bg-white p-4">
          <h2 className="text-sm font-semibold text-[#111827]">Run Preset</h2>
          <div className="mt-4 space-y-3">
            <label className="block text-xs font-medium text-[#4B5563]">
              Topic
              <select
                className="mt-1 h-9 w-full border border-[#D1D5DB] bg-white px-2 text-sm text-[#111827]"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
              >
                {topicOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <NumberField label="Videos per keyword" value={perKeywordLimit} min={1} max={25} onChange={setPerKeywordLimit} />
            <NumberField label="Comments per page" value={comments} min={1} max={100} onChange={setComments} />
            <NumberField label="Comment pages" value={commentPages} min={1} max={50} onChange={setCommentPages} />

            <label className="flex items-center gap-2 text-sm text-[#374151]">
              <input
                type="checkbox"
                checked={collectTranscripts}
                onChange={(event) => setCollectTranscripts(event.target.checked)}
              />
              Visible transcript summaries
            </label>

            <NumberField label="Transcript videos" value={transcriptVideos} min={0} max={20} onChange={setTranscriptVideos} />
          </div>
        </div>

        <div className="border border-[#E5E7EB] bg-white p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-[#111827]">Command</h2>
            <span className="text-xs text-[#6B7280]">Run from repository root</span>
          </div>
          <pre className="mt-3 overflow-auto bg-[#111827] p-3 text-xs leading-5 text-white">{command}</pre>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={runResearch}
              disabled={running}
              className="h-9 border border-[#F97316] bg-[#F97316] px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {running ? "Running" : "Run"}
            </button>
            <span className="text-xs text-[#6B7280]">{runStatus || "Execution is capped by the internal API gate."}</span>
          </div>
          <div className="mt-3 border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            The run endpoint accepts only allowlisted topics and bounded numeric limits. Raw transcript storage and state-changing YouTube actions remain blocked.
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <div className="border border-[#E5E7EB] bg-white">
          <div className="border-b border-[#E5E7EB] px-4 py-3">
            <h2 className="text-sm font-semibold text-[#111827]">Top Videos</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-collapse text-left text-sm">
              <thead className="bg-[#F9FAFB] text-xs text-[#6B7280]">
                <tr>
                  <th className="px-4 py-2">Score</th>
                  <th className="px-4 py-2">Title</th>
                  <th className="px-4 py-2">Topic</th>
                  <th className="px-4 py-2">Rank</th>
                  <th className="px-4 py-2">Comments</th>
                  <th className="px-4 py-2">Transcript</th>
                  <th className="px-4 py-2">Signal</th>
                </tr>
              </thead>
              <tbody>
                {videos.map((video) => (
                  <tr key={video.video_id ?? video.url} className="border-t border-[#F3F4F6]">
                    <td className="px-4 py-3 font-semibold text-[#111827]">{video.scores?.topic_opportunity_score ?? "-"}</td>
                    <td className="px-4 py-3">
                      <a className="font-medium text-[#111827] no-underline hover:text-[#F97316]" href={video.url} target="_blank" rel="noreferrer">
                        {video.title ?? "-"}
                      </a>
                      <div className="mt-1 text-xs text-[#6B7280]">{video.channel_title ?? "-"}</div>
                    </td>
                    <td className="px-4 py-3 text-[#374151]">{video.topic_classification?.primary_topic ?? "-"}</td>
                    <td className="px-4 py-3 text-[#374151]">{video.best_observed_rank ?? "-"}</td>
                    <td className="px-4 py-3 text-[#374151]">
                      {video.comment_summary?.status ?? "skipped"}
                      <div className="text-xs text-[#6B7280]">{video.comment_summary?.comment_count_observed ?? 0} observed</div>
                    </td>
                    <td className="px-4 py-3 text-[#374151]">{video.transcript_summary?.status ?? "skipped"}</td>
                    <td className="px-4 py-3 text-[#374151]">
                      {video.signal_quality?.level ?? "-"}
                      <div className="text-xs text-[#6B7280]">{video.signal_quality?.confidence_score ?? 0}</div>
                    </td>
                  </tr>
                ))}
                {videos.length === 0 && (
                  <tr>
                    <td className="px-4 py-8 text-center text-sm text-[#6B7280]" colSpan={7}>
                      No market research report has been generated yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="space-y-4">
          <Panel title="Topic Clusters">
            {clusters.slice(0, 10).map((cluster) => (
              <Row key={cluster.topic} label={cluster.topic ?? "-"} value={`${cluster.video_count ?? 0} / ${cluster.average_opportunity_score ?? 0}`} />
            ))}
          </Panel>

          <Panel title="Channels">
            {channels.slice(0, 10).map((channel) => (
              <Row key={channel.channel_title} label={channel.channel_title ?? "-"} value={`${channel.video_count ?? 0} / ${channel.best_score ?? 0}`} />
            ))}
          </Panel>

          <Panel title="Boundary">
            {(data?.public_signal_model?.not_officially_available ?? []).slice(0, 5).map((item) => (
              <div key={item} className="border-b border-[#F3F4F6] py-2 text-xs text-[#4B5563] last:border-0">
                {item}
              </div>
            ))}
          </Panel>
        </aside>
      </section>

      <section className="border border-[#E5E7EB] bg-white p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[#111827]">Markdown Report</h2>
          <span className="text-xs text-[#6B7280]">{data?.markdown_report ?? "-"}</span>
        </div>
        <pre className="mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap bg-[#F9FAFB] p-3 text-xs leading-5 text-[#374151]">
          {markdown || "No Markdown report available."}
        </pre>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-[#E5E7EB] bg-white px-4 py-3">
      <div className="text-xs font-medium text-[#6B7280]">{label}</div>
      <div className="mt-1 truncate text-lg font-semibold text-[#111827]">{value}</div>
    </div>
  );
}

function NumberField({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (value: number) => void }) {
  return (
    <label className="block text-xs font-medium text-[#4B5563]">
      {label}
      <input
        className="mt-1 h-9 w-full border border-[#D1D5DB] px-2 text-sm text-[#111827]"
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border border-[#E5E7EB] bg-white p-4">
      <h2 className="text-sm font-semibold text-[#111827]">{title}</h2>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#F3F4F6] py-2 text-xs last:border-0">
      <span className="min-w-0 truncate text-[#374151]">{label}</span>
      <span className="shrink-0 font-medium text-[#111827]">{value}</span>
    </div>
  );
}

function formatDate(value?: string) {
  if (!value) return "-";
  return value.replace("T", " ").replace("+00:00", " UTC");
}
