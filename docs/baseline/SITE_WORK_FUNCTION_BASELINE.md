Status: LOCKED
Baseline ID: SITE-WORK-FUNCTION-BASELINE-01

# Site Work Function Baseline

This baseline defines when a site module is considered usable for real user
work. It locks the current distinction between read-only navigation, prepared
work, approval-gated execution, and blocked or user-direct operations.

## Scope

The baseline covers the currently developed site work modules:

- `google`
- `naver`
- `smartstore`
- `hiworks`
- `gabia`
- `youtube`
- internal `market_research`
- shared `sites` SSO/subdomain runtime

All work must run from the local browser/local agent path. Server-side
Playwright execution, cookie export, session export, raw token output, password
output, OTP automation, and Authorization header disclosure are forbidden.

## Completion Tiers

Every user-facing work item must be classified into one of these tiers:

- `read`: open, observe, list, inspect, scan, or report only.
- `prepare`: fill-safe draft, plan, catalog, validation, or pre-final input.
- `approval`: execution is possible only after explicit user approval and a
  confirm phrase or equivalent approval record.
- `user_direct`: login, payment, OTP, 2FA, credential issue, or other operation
  that must be completed directly by the user.
- `blocked`: the module must refuse to create an executable task.

For one-time or infrequent sites, login may use an occasional-site login
handoff without developing a full site module. This handoff opens only the
approved entry URL in the local-agent browser, requires the user to enter
credentials directly, allows only read-only session checks, and must not perform
state-changing work.

A work item is not complete if it has only a file or class but no router entry,
no gate policy, or no test/audit coverage.

## Required Runtime Rules

- Login sessions must be user-present and must reuse the same local browser
  profile for subdomain navigation.
- Read-only site navigation must use `web_open_url_readonly` or an equivalent
  local-agent read-only adapter.
- State-changing actions must be approval-gated.
- Dry-run and prepare flows must never send, submit, save, upload, purchase,
  deploy, publish, delete, or change settings.
- Logs and reports must mask secrets and must not print raw cookies, sessions,
  passwords, OTPs, API keys, bearer tokens, or Authorization headers.

## Locked Current Functional Inventory

## Site Work Matrix

This matrix is the operating target. New site work must be added here first,
then implemented through a router, gate, test, and audit.

### Google Work Matrix

| Area | User Work | Tier | Current Verification |
| --- | --- | --- | --- |
| Google Home | open/search surface observation | read | catalog + SSO read check |
| Google Account | account page reachability, login state hint | read/user_direct | user-present only |
| Gmail | read inbox, search, compose draft, prepare send | read/prepare/approval | implemented; send gated |
| Drive | list/search, prepare upload/share | read/prepare/approval | partial; upload/share gated |
| Calendar | view today/week, prepare event | read/prepare/approval | partial; create gated |
| Docs | recent/open/search, prepare document work | read/prepare/approval | partial; edit/delete gated |
| Sheets | recent/open/search, prepare cell update | read/prepare/approval | partial; update gated |
| YouTube | open/read public and Studio surfaces | read | catalog + SSO read check |
| YouTube Studio | prepare video upload/metadata | prepare/approval | safe pre-final input for upload |
| Search Console | inspect URL, submit sitemap/index request | read/prepare/approval | safe pre-final input |
| AI Studio | open, prepare API key request handoff | read/approval | no key creation without approval |
| Gemini | open, prompt handoff | read/approval | approval handoff only |
| Google Cloud | open/read Console/IAM/Billing/Run/Compute/Storage/BigQuery/GKE/SQL/PubSub/Secret Manager/Logging/Monitoring/Vertex | read/approval | read-only local browser tasks; cloud changes gated |
| Marketing/Ads | Analytics, Tag Manager, Ads, Merchant Center, AdSense, Looker Studio | read/approval | catalog-first; publish/budget/share gated |

### Naver Work Matrix

| Area | User Work | Tier | Current Verification |
| --- | --- | --- | --- |
| Naver Home/Login | login entry and session check | read/user_direct | user-present only |
| Naver Mail | inbox/read/compose/send | read/prepare/approval | implemented; live blocked if session missing |
| Blog | write draft, publish | prepare/approval | implemented; publish gated |
| Cafe | list cafes/posts, read post, prepare/publish post | read/prepare/approval | implemented; publish gated |
| Calendar | list events, prepare/save event | read/prepare/approval | implemented; save gated |
| MYBOX | list/search/upload | read/prepare/approval | implemented; upload gated |
| Pay | orders/points only | read | payments remain user_direct/blocked |
| Talk | list/send message | read/prepare/approval | implemented; send gated |
| Place | list places/reviews | read | read-only |
| SmartStore Alias | delegate to SmartStore module | read/prepare/approval | routed |
| Company SEO | plan/assets/ownership/exposure/submit-plan/monitor | read/prepare/approval | submit gated |
| Developers | entrypoints/app plan | read/prepare/approval | credential issue gated/user_direct |
| Shopping | competitor monitoring | read | public/OpenAPI-style comparison only |
| Excel Report | build local report | read/prepare | local file write gate |

### SmartStore Work Matrix

| Area | User Work | Tier | Current Verification |
| --- | --- | --- | --- |
| Dashboard/Product | open dashboard, product list | read | implemented/partial live |
| Product Register | validate data, prepare general/group/bulk product | prepare | complete baseline |
| Product Save | save general/group/bulk product | approval | gated by `SMARTSTORE_APPROVED_SUBMIT` |
| Orders | fetch new orders | read | partial |
| Inventory | check low stock | read | partial |
| Analytics | collect today stats | read | partial |
| SEO | optimize listing | planned | todo |
| AI Review Reply | prepare/send reply | planned/approval | todo |
| Competitor | keyword competitor tracking | planned | todo |
| CSV Import | import product CSV | planned/approval | todo |

### Hiworks Work Matrix

| Area | User Work | Tier | Current Verification |
| --- | --- | --- | --- |
| Dashboard/Apps | open dashboard and list apps | read | implemented |
| Mail | open mail, inspect actions, compose page | read/prepare | implemented |
| Sales Mail | prepare sales mail queue, dry-run batch plan | prepare | implemented |
| Service Scan | scan visible controls by service | read | implemented |
| Section Prepare | fill safe values before final action | prepare | implemented |
| Section Submit | execute approved button only | approval | gated by `HIWORKS_APPROVED_SUBMIT` |
| Unknown Buttons | unknown/ambiguous controls | blocked/approval | remain gated |

### Gabia Work Matrix

| Area | User Work | Tier | Current Verification |
| --- | --- | --- | --- |
| Status | show policy/read scope | read | router connected |
| DNS Read | show DNS read policy | read | router connected |
| DNS Change/Delete | create/update/delete record | approval | approval required; no auto-execute |
| Domain Info | show domain account-read policy | read | local-agent login required |
| Domain Assist | validate/suggest domain draft | prepare/user_direct | draft only |
| Hosting/Mail Setting | setting change | approval | approval required |
| Login/Payment/Credential | login, OTP, 2FA, payment, credential issue | user_direct/blocked | user must perform directly |

### YouTube Work Matrix

| Area | User Work | Tier | Current Verification |
| --- | --- | --- | --- |
| Research Search | search videos and collect public metadata | read | official YouTube Data API or public YouTube search DOM read-only; no clicks, inputs, cookie export, hidden endpoints, or challenge bypass |
| Market Research Topic Analysis | expand a topic such as SmartStore into keyword searches, classify repeated exposure, and score observed results | read/prepare | implemented inside current app; see `MARKET_RESEARCH_MODULE_BASELINE` |
| Video Info | collect title, description, channel, date, stats, caption hint | read | official YouTube Data API only |
| Comments | collect public top-level comments | read | official YouTube Data API only |
| Transcript Plan | decide compliant transcript collection path | read/prepare | server Web OAuth or user-provided captions only |
| Transcript Analysis | analyze user-provided transcript/caption file | read/prepare | local extractive analysis |
| Context Report | analyze video metadata, comments, and optional transcript | read/prepare | local extractive analysis |
| Strategy Scorecard | apply reference video/comment/transcript signals to my production and management scores | read/prepare | local scoring model |
| Recording | prepare recording plan | prepare | implemented |
| Recording Execute | run recording | approval | gated by `YOUTUBE_APPROVED_RECORD` |
| Upload | prepare upload metadata | prepare | implemented |
| Upload Execute | dry-run or live upload | approval | defaults dry-run; live requires approval |
| Upload Verify | verify upload result artifact | read | implemented |
| Comment Draft | prepare comment/reply text for owned channel work | prepare | no post without final approval |
| Comment Post/Reply | post comment or reply to a comment | approval | gated final confirmation |
| Comment Moderation | list/review/hide/report/delete comments | read/approval | destructive actions gated |
| Channel Operations | manage uploaded videos, metadata, comments, and reports | read/prepare/approval | owner OAuth required for execution |

## Work Acceptance Rule

A site task is accepted only when all of the following are true:

- The work appears in the site work matrix.
- The command is routed through `scripts/browser/cdp/cdp_client.py` or a documented local
  module entrypoint.
- The task has an explicit tier: `read`, `prepare`, `approval`, `user_direct`,
  or `blocked`.
- The task has a gate or explicit reason why it is read-only/user-direct.
- The task has at least one test or audit assertion.
- Live evidence is recorded for claims about logged-in page reachability.

Claims about actual business completion must be downgraded to WARN when the
site login session is missing or when only catalog/dry-run evidence exists.

### Google

- Router command: `python scripts/browser/cdp/cdp_client.py google ...`
- Required actions: 96
- Required read actions: 50
- Required approval actions: 46
- Required live-input supported approval actions: 46
- Required boundaries:
  - Gmail is implemented.
  - Drive, Calendar, Docs, and Sheets remain `partial`.
  - approval actions may prepare or safe-fill, but final submit remains gated.
  - Cloud read-only actions convert to local browser read-only tasks.

### Naver

- Router command: `python scripts/browser/cdp/cdp_client.py naver ...`
- Required service catalog categories:
  - `session`
  - `mail`
  - `content`
  - `seo`
  - `developers`
  - `shopping`
  - `excel`
  - `cafe`
  - `calendar`
  - `mybox`
  - `pay`
  - `talk`
  - `place`
  - `smartstore`
- Required boundaries:
  - login is user-present.
  - send, publish, upload, save, and submit flows require approval.
  - if Naver session is missing, live function checks must report WARN, not
    hide the failure with mock data.

### SmartStore

- Router command: `python scripts/browser/cdp/cdp_client.py smartstore ...`
- Required action catalog counts:
  - read total: 8
  - prepare total: 3
  - approval total: 4
- Required boundaries:
  - product registration has a complete baseline.
  - product list, order, inventory, and analytics remain partial.
  - SEO, AI review reply, competitor, and CSV remain todo until live evidence
    and tests are added.

### Hiworks

- Router command: `python scripts/browser/cdp/cdp_client.py hiworks ...`
- Required action catalog minimum services: 17
- Required boundaries:
  - dashboard, apps, mail, compose, sales-mail prepare, service scan, action
    catalog, prepare-section, submit-section, and send-batch dry-run are routed.
  - actual send/submit requires approval.
  - unknown buttons remain gated.

### Gabia

- Router command: `python scripts/browser/cdp/cdp_client.py gabia ...`
- Required routed tasks:
  - `status`
  - `dns`
  - `login`
  - `domain`
  - `domain-assist`
  - `hosting`
  - `payment`
- Required boundaries:
  - public/account read flows may show policy only.
  - login, payment, OTP, 2FA, credential issue, and billing operations are
    `user_direct`.
  - DNS/domain/hosting changes require approval and must not auto-execute.

### YouTube

- Router command: `python scripts/browser/cdp/cdp_client.py youtube ...`
- Market research command: `python scripts/browser/cdp/cdp_client.py google youtube topic ...`
- Required routed tasks:
  - `record prepare`
  - `record execute`
  - `upload prepare`
  - `upload execute`
  - `upload verify`
- Required boundaries:
  - upload defaults to dry-run unless live execution is explicitly requested
    and approved.
  - missing local video files must block approval readiness.
  - keyword/topic research remains an internal app module and must not create a
    separate public domain unless productization is approved.

## Required Evidence

The following checks must pass before claiming the site work baseline is ready:

- Python compile for routers and audit script.
- Unit tests for Google, Naver, SmartStore, Hiworks, Gabia, YouTube, and SSO
  runtime contracts.
- `tools/audits/app/audit_site_work_function_baseline.py`
- `tools/quality/module_quality_gate.py --module repo_guard`

Live browser checks are useful evidence, but they are not required by this
static baseline because they depend on local login state.
