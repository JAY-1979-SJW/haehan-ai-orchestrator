# Gabia Domain Full Setup Plan - 2026-05-14

## Target

- Domain: `haehan-ai.kr`
- Registrar/portal: Gabia / MyGabia
- Current status: Active / normal
- Expiration: `2027-02-12`

## Safety Boundary

This plan separates safe read-only confirmation from state-changing actions.

Do not click final save/apply/payment/renewal buttons until the exact change set is approved. DNS, owner, transfer, and billing changes can interrupt website, email, or ownership operations.

## Current Confirmed Configuration

### Domain

| Item | Current |
| --- | --- |
| Domain | `haehan-ai.kr` |
| Registration date | `2026-02-12` |
| Expiration date | `2027-02-12` |
| Status | Active / normal |
| Transfer lock | On |
| Safe lock | Off |
| Registration information hidden | Off |
| DNSSEC | None |
| DNS host | None |

### Nameserver

| Order | Current |
| --- | --- |
| 1 | `ns1.gabia.co.kr` |
| 2 | `ns2.gabia.co.kr` |

### DNS Records

| Type | Host | Value / Target | TTL | Priority |
| --- | --- | --- | --- | --- |
| A | `@` | `1.201.176.236` | `3600` |  |
| A | `www` | `1.201.176.236` | `3600` |  |
| A | `app` | `1.201.176.236` | `3600` |  |
| A | `support` | `1.201.176.236` | `3600` |  |
| A | `career` | `1.201.176.236` | `3600` |  |
| A | `blog` | `1.201.176.236` | `3600` |  |
| A | `docs` | `1.201.176.236` | `3600` |  |
| A | `status` | `1.201.176.236` | `3600` |  |
| TXT | `@` | `google-site-verification=...` | `3600` |  |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:...` | `600` |  |
| MX | `@` | `mailapp.hiworks.co.kr.` | `600` | `10` |
| TXT | `@` | `v=spf1 include:_spf.hiworks.co.kr ~all` | `600` |  |
| CNAME | `hiworks` | `hiworksapp.hiworks.co.kr.` | `600` |  |
| CNAME | `mail` | `mailapp.hiworks.co.kr.` | `600` |  |
| A | `api` | `1.201.176.236` | `600` |  |
| A | `bid` | `1.201.176.236` | `600` |  |
| A | `cloud` | `1.201.176.236` | `600` |  |
| A | `attendance` | `1.201.176.236` | `600` |  |
| A | `cad` | `1.201.176.236` | `600` |  |
| A | `esc` | `1.201.176.236` | `600` |  |
| A | `gongmu` | `1.201.176.236` | `600` |  |

## Recommended Full Setup

### Keep As-Is

| Area | Decision | Reason |
| --- | --- | --- |
| Nameserver | Keep Gabia nameservers | Current DNS is managed in Gabia and records are visible there. |
| Transfer lock | Keep On | Protects against unauthorized registrar transfer. |
| Hiworks MX/SPF/CNAME | Keep | Mail is already routed to Hiworks. |
| Existing A records | Keep unless server IP changes | Web/app subdomains currently point to one server IP. |
| DNSSEC | Keep Off until key management is verified | Enabling incorrectly can break resolution. |
| Auto-renew/payment | Do not change without explicit billing approval | Billing side effect. |

### Apply After Approval

| Area | Proposed Change | Impact |
| --- | --- | --- |
| Safe lock | Turn On | Blocks/limits sensitive domain changes. Good default after DNS is stable. |
| Registration information hidden | Turn On | Hides owner address/email/phone through Gabia privacy proxy where supported. |
| DNS record edits | Only apply exact requested changes | Wrong DNS values can break website/email. |

### Needs User Value Before Action

| Required Input | Example |
| --- | --- |
| Web server IP if changing | `1.201.176.236` or new public IP |
| Subdomains to add/remove | `admin`, `dev`, `erp`, `mail`, etc. |
| Mail provider change | Hiworks / Google Workspace / Microsoft 365 |
| Verification TXT records | Google, Naver, Search Console, etc. |
| DMARC enforcement level | `none`, `quarantine`, `reject` |

## Execution Order

1. Confirm desired mode: keep current DNS and apply security toggles only, or provide exact DNS changes.
2. If approved, open `https://domains.gabia.com/manage/domain/all/5917014?tab=DOMAIN_INFO`.
3. Enable Safe Lock.
4. Enable Registration Information Hidden.
5. Open `https://dns.gabia.com/dns/internals/total_set`.
6. Apply only explicitly approved DNS record edits.
7. Save screenshots/snapshots after changes.
8. Re-save Gabia sessions.
9. Run external DNS verification (`nslookup`, `Resolve-DnsName`, or equivalent).

## Approval Phrase

Use one explicit instruction before state-changing actions:

`승인: haehan-ai.kr 보안 기본값 적용 - 안전잠금 ON, 등록정보 숨김 ON, DNS는 현재 유지`

For DNS changes, include every record to change in the approval.
