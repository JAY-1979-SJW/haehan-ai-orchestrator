Status: LOCKED
Baseline ID: MARKET-RESEARCH-MODULE-BASELINE-01

# Market Research Module Baseline

This baseline locks keyword-driven market research as an internal module of the
current app. It must not be treated as a separate public domain or standalone
service until productization requirements are explicitly approved.

## Scope

The module covers research workflows that start from a user-selected topic,
expand it into related keywords, collect public/search metadata, classify the
results, and produce local analysis reports.

Current implemented surface:

- YouTube Research: keyword/topic search, repeated exposure analysis, ranking
  observation, topic classification, and optional visible transcript summary.

Planned compatible surfaces:

- SmartStore market research
- Naver Shopping and commerce keyword research
- Google Search/Ads free planning signals
- competitor content and product-page comparison

## Operating Model

- The module runs inside the current app under `Market Research` /
  `YouTube Research`.
- It reuses existing Google, YouTube, Naver, and SmartStore routers instead of
  creating a separate domain.
- Public read/search work is allowed when it stays read-only.
- Login, paid tools, campaign setup, product changes, playlist changes, saves,
  publishing, uploads, and account changes remain approval-gated or user-direct.
- Reports are stored as repo-local artifacts under `data/`.
- Full raw transcripts, cookies, sessions, passwords, API keys, bearer tokens,
  and Authorization headers must not be printed or stored.

## YouTube Research Workflow

1. User selects a topic such as `smartstore`, `purchase_agency`,
   `shopping_mall`, `commerce_marketing`, or `ai_work_automation`.
2. The topic expands into a keyword set.
3. Each keyword is searched through the official YouTube Data API when an
   approved API key is available, otherwise through public YouTube search DOM
   read-only collection.
4. Results are deduplicated by video ID.
5. The analyzer scores repeated keyword exposure, observed rank, public
   popularity signals, and optional transcript-summary signals.
6. Results are classified by topic and written to
   `data/google_youtube_topic_analysis_latest.json`.

YouTube has no stable public global ranking for arbitrary topics. The module
therefore records observed search positions per keyword and repeated exposure
across keyword sets.

## Data Availability Rule

The module must separate official data from inferred signals.

Officially available YouTube signals include public search results for a
supplied query, public metadata, public counts when available, and caption
availability hints. The module must not claim access to absolute YouTube search
volume, keyword click-through rate, viewer watch history, impressions,
retention, traffic sources, or private audience behavior for videos we do not
own.

Opportunity scores and topic ranks are directional public-signal estimates,
not official YouTube demand measurements.

Full transcript text may be stored only for user-provided, owned, licensed, or
officially authorized caption files after an explicit rights-confirmation gate.
Full text storage from third-party browser-visible transcripts, hidden caption
endpoints, or unofficial transcript APIs remains blocked.

## Domain Split Rule

Do not create a separate external domain for this capability by default.

A separate domain may be proposed only when all of these are true:

- multiple external users must access it directly;
- project/user-level storage, permissions, and retention are required;
- usage limits, billing, or quota controls are required;
- a dashboard and support workflow are required outside the current app;
- the user explicitly approves the productization plan.

Until then, the accepted implementation target is:

```text
current app
  Market Research
    YouTube Research
    Keyword Topic Analysis
    Competitor Content Analysis
```

## Acceptance Rule

A market research feature is accepted only when:

- the topic or keyword source is documented;
- the collection method is classified as official API, public read-only browser
  collection, or user-provided data;
- state-changing actions are blocked or approval-gated;
- result classification and scoring are deterministic enough for tests;
- at least one focused test covers the workflow or policy boundary;
- the required quality gate passes.
