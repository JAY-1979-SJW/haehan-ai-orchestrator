# Gabia / MyGabia Domain Inventory - 2026-05-14

## Scope

- Browser session: CDP Chrome profile
- Mode: read-only exploration
- Account portal: MyGabia
- Sensitive owner/admin email, phone, business number values are intentionally not copied into this report.

## Confirmed Services

| Area | Finding |
| --- | --- |
| MyGabia dashboard | Logged-in MyGabia dashboard accessible |
| Service count | 2 active services shown on dashboard |
| Domain service count | 1 domain |
| Hiworks service count | 1 service |
| Purchased domain | `haehan-ai.kr` |
| Registration period | `2026-02-12` to `2027-02-12` |
| Days remaining at exploration time | `D-274` |
| Renewal display | `21,000원/년` |
| Domain status | Active / normal |

## Main MyGabia Routes

| Function | URL |
| --- | --- |
| Dashboard | `https://my.gabia.com/dashboard#/` |
| Service management | `https://my.gabia.com/service#/` |
| Domain service list | `https://my.gabia.com/service#/?carve_code=domain` |
| Billing | `https://my.gabia.com/billing#/` |
| Payment method | `https://my.gabia.com/payment#/method` |
| Auto pay | `https://my.gabia.com/payment#/auto-pay` |
| My info | `https://my.gabia.com/myinfo#/` |
| Manager settings | `https://my.gabia.com/myinfo/manager` |
| DNS management | `https://dns.gabia.com/` |
| Domain integrated dashboard | `https://domains.gabia.com/manage/dashboard` |

## Domain Management Routes

| Function | URL |
| --- | --- |
| Domain dashboard | `https://domains.gabia.com/manage/dashboard` |
| All domains | `https://domains.gabia.com/manage/domain/all` |
| Domain detail | `https://domains.gabia.com/manage/domain/all/5917014` |
| Domain info tab | `https://domains.gabia.com/manage/domain/all/5917014?tab=DOMAIN_INFO` |
| Owner/admin tab | `https://domains.gabia.com/manage/domain/all/5917014?tab=OWNER_ADMIN_INFO` |
| Nameserver/DNS host/DNSSEC tab | `https://domains.gabia.com/manage/domain/all/5917014?tab=NAMESERVER_DNS_DNSSEC` |
| Deleted domains | `https://domains.gabia.com/manage/domain/deleted` |
| Reserved domains | `https://domains.gabia.com/manage/reserve` |

## Domain Detail Summary

| Item | Value |
| --- | --- |
| Domain | `haehan-ai.kr` |
| Registration date | `2026-02-12` |
| Expiration date | `2027-02-12` |
| Renewal deadline | `2027-03-14` |
| Deletion date display | `2027-03-15` |
| Safe lock | Off |
| Registration info hidden | Off |
| Transfer lock | On |
| DNS host records | None |
| DNSSEC | None |

## Nameserver Summary

The current domain detail tab shows:

| Order | Nameserver |
| --- | --- |
| 1 | `ns1.gabia.co.kr` |
| 2 | `ns2.gabia.co.kr` |

The integrated dashboard also displayed Gabia nameserver infrastructure:

| Order | Nameserver / IP |
| --- | --- |
| 1 | `ns.gabia.co.kr` / `43.201.170.100` |
| 2 | `ns1.gabia.co.kr` / `20.200.205.248` |
| 3 | `ns.gabia.net` |

## DNS Records

Source: `https://dns.gabia.com/dns/internals/total_set`

| Type | Host | Value / Target | TTL | Priority | Service |
| --- | --- | --- | --- | --- | --- |
| A | `@` | `1.201.176.236` | `3600` |  | DNS 설정 |
| A | `www` | `1.201.176.236` | `3600` |  | DNS 설정 |
| A | `app` | `1.201.176.236` | `3600` |  | DNS 설정 |
| A | `support` | `1.201.176.236` | `3600` |  | DNS 설정 |
| A | `career` | `1.201.176.236` | `3600` |  | DNS 설정 |
| A | `blog` | `1.201.176.236` | `3600` |  | DNS 설정 |
| A | `docs` | `1.201.176.236` | `3600` |  | DNS 설정 |
| A | `status` | `1.201.176.236` | `3600` |  | DNS 설정 |
| TXT | `@` | `google-site-verification=...` | `3600` |  | DNS 설정 |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:...` | `600` |  | DNS 설정 |
| MX | `@` | `mailapp.hiworks.co.kr.` | `600` | `10` | DNS 설정 |
| TXT | `@` | `v=spf1 include:_spf.hiworks.co.kr ~all` | `600` |  | DNS 설정-하이웍스 |
| CNAME | `hiworks` | `hiworksapp.hiworks.co.kr.` | `600` |  | DNS 설정 |
| CNAME | `mail` | `mailapp.hiworks.co.kr.` | `600` |  | DNS 설정 |
| A | `api` | `1.201.176.236` | `600` |  | DNS 설정 |
| A | `bid` | `1.201.176.236` | `600` |  | DNS 설정 |
| A | `cloud` | `1.201.176.236` | `600` |  | DNS 설정 |
| A | `attendance` | `1.201.176.236` | `600` |  | DNS 설정 |
| A | `cad` | `1.201.176.236` | `600` |  | DNS 설정 |
| A | `esc` | `1.201.176.236` | `600` |  | DNS 설정 |
| A | `gongmu` | `1.201.176.236` | `600` |  | DNS 설정 |

## Snapshot Evidence

| Page | Snapshot |
| --- | --- |
| MyGabia dashboard | `data/manual_visits/my.gabia.com/dashboard__20260514_003905.json` |
| DNS total set | `data/manual_visits/dns.gabia.com/dns_internals_total_set__20260514_004838.json` |

## Next Safe Step

To change DNS, use the DNS settings screen and update only the required records. Any record edit, lock toggle, transfer action, renewal, or payment should require explicit approval before submitting.
