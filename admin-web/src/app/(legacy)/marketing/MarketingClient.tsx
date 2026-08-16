"use client";

import { useState } from "react";

type CafePost = {
  title?: string;
  board?: string;
  view_count?: number;
  comment_count?: number;
  date?: string;
};

type YoutubeBenchmark = {
  title?: string;
  channel?: string;
  views?: number;
  note?: string;
};

type Competitor = {
  name?: string;
  url?: string | null;
  found_via?: string;
  assessment?: string;
};

type Strategy = {
  target?: { track_a?: string; track_b?: string };
  pricing?: { free?: string; individual?: string; b2b?: string };
  positioning?: string;
  distribution?: string[];
};

type ContentPlanItem = { track?: string; title?: string; status?: string };

type MarketingData = {
  generated_note?: string;
  cafe_top_posts?: CafePost[];
  cafe_keyword_posts?: CafePost[];
  youtube_benchmarks?: YoutubeBenchmark[];
  competitors?: Competitor[];
  strategy?: Strategy;
  content_plan?: ContentPlanItem[];
};

type Props = {
  data: MarketingData | null;
  error?: string;
};

const TABS = ["전략 요약", "콘텐츠 소재", "홍보 문구"] as const;
type Tab = (typeof TABS)[number];

export default function MarketingClient({ data, error }: Props) {
  const [tab, setTab] = useState<Tab>("전략 요약");

  if (error || !data) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        {error || "자료가 없습니다. scripts/marketing_summary_build.py 를 먼저 실행하세요."}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {data.generated_note && (
        <p className="text-xs text-gray-400">{data.generated_note}</p>
      )}
      <div className="flex gap-2 border-b border-gray-200">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium ${
              tab === t
                ? "border-b-2 border-orange-500 text-orange-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "전략 요약" && <StrategyTab data={data} />}
      {tab === "콘텐츠 소재" && <ContentTab data={data} />}
      {tab === "홍보 문구" && <CopyTab data={data} />}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-2 text-sm font-semibold text-gray-900">{title}</h3>
      {children}
    </div>
  );
}

function StrategyTab({ data }: { data: MarketingData }) {
  const s = data.strategy || {};
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Card title="타겟">
        <ul className="space-y-1 text-sm text-gray-700">
          <li><b>트랙 A(제품 데모)</b> — {s.target?.track_a}</li>
          <li><b>트랙 B(교육 콘텐츠)</b> — {s.target?.track_b}</li>
        </ul>
      </Card>
      <Card title="가격 구조">
        <ul className="space-y-1 text-sm text-gray-700">
          <li><b>무료</b> — {s.pricing?.free}</li>
          <li><b>개인 구독</b> — {s.pricing?.individual}</li>
          <li><b>B2B</b> — {s.pricing?.b2b}</li>
        </ul>
      </Card>
      <Card title="포지셔닝">
        <p className="text-sm text-gray-700">{s.positioning}</p>
      </Card>
      <Card title="배포 채널">
        <ul className="list-disc space-y-1 pl-4 text-sm text-gray-700">
          {(s.distribution || []).map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>
      </Card>
      <div className="md:col-span-2">
        <Card title="경쟁사">
          <div className="space-y-3">
            {(data.competitors || []).map((c, i) => (
              <div key={i} className="border-t border-gray-100 pt-2 first:border-t-0 first:pt-0">
                <p className="text-sm font-medium text-gray-900">
                  {c.name}
                  {c.url && (
                    <a href={c.url} target="_blank" rel="noreferrer" className="ml-2 text-xs text-orange-600 underline">
                      링크
                    </a>
                  )}
                </p>
                <p className="text-xs text-gray-400">발견 경로: {c.found_via}</p>
                <p className="mt-1 text-sm text-gray-700">{c.assessment}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function PostTable({ rows }: { rows: CafePost[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-gray-400">
            <th className="pb-2">제목</th>
            <th className="pb-2">게시판</th>
            <th className="pb-2 text-right">조회수</th>
            <th className="pb-2 text-right">댓글</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-gray-100">
              <td className="py-1.5 pr-2">{r.title}</td>
              <td className="py-1.5 pr-2 text-gray-400">{r.board}</td>
              <td className="py-1.5 text-right">{r.view_count?.toLocaleString()}</td>
              <td className="py-1.5 text-right">{r.comment_count?.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ContentTab({ data }: { data: MarketingData }) {
  return (
    <div className="space-y-4">
      <Card title="콘텐츠 우선순위">
        <ul className="space-y-1 text-sm text-gray-700">
          {(data.content_plan || []).map((c, i) => (
            <li key={i}>
              <span className="mr-2 rounded bg-orange-100 px-1.5 py-0.5 text-xs font-medium text-orange-700">
                트랙 {c.track}
              </span>
              {c.title} — <span className="text-gray-400">{c.status}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="건설공무 카페 — 키워드(적산/물량산출/AI/내역서) 최고 조회수">
        <PostTable rows={data.cafe_keyword_posts || []} />
      </Card>
      <Card title="건설공무 카페 — 전체 최고 조회수">
        <PostTable rows={data.cafe_top_posts || []} />
      </Card>
      <Card title="YouTube 벤치마크">
        <div className="space-y-2">
          {(data.youtube_benchmarks || []).map((v, i) => (
            <div key={i} className="border-t border-gray-100 pt-2 text-sm first:border-t-0 first:pt-0">
              <p className="font-medium text-gray-900">
                {v.title} <span className="text-gray-400">— {v.channel}</span>
              </p>
              <p className="text-xs text-gray-500">
                조회수 {v.views?.toLocaleString()} · {v.note}
              </p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function CopyTab({ data }: { data: MarketingData }) {
  const topPost = data.cafe_keyword_posts?.[0];
  const draft = `안녕하세요, 건설 공무 실무 하다 보면 ${topPost?.title ?? "내역서·물량산출"} 때문에 시간 잡아먹히는 일 많으시죠?

저도 그거 때문에 고생하다가, GPT로 직접 자동화 도구를 만들어봤습니다.
도면 물량산출부터 내역서 연동까지 되는데, 하루 3건은 무료로 써보실 수 있어요.

써보시고 필요하면 댓글로 물어봐주세요. 다들 칼퇴하세요!`;

  return (
    <div className="space-y-4">
      <Card title="카페 게시용 초안 (자발적 정보공유 톤 — conpublicai 사례 참고)">
        <textarea
          readOnly
          value={draft}
          rows={10}
          className="w-full rounded border border-gray-200 p-3 text-sm text-gray-700"
        />
        <p className="mt-2 text-xs text-gray-400">
          주의: 카페 규정상 광고성 게시는 배척 리스크. 정보공유 톤 유지, 유료 광고는 별도 검토.
        </p>
      </Card>
    </div>
  );
}
