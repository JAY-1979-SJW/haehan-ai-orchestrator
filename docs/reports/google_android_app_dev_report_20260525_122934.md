# Google Android App Development Verification Report

- Generated: 2026-05-25T12:29:34.573237+00:00
- Surfaces: 13
- Live verified: 13
- Status: pass=13, warn=0, fail=0
- Final clicked: 0

## Stage Labels

- `build`: app architecture, UI, local build, docs mapping (android_developers, google_developers, chrome_developers)
- `backend`: auth, data, messaging, analytics, crash, API/backend plan (firebase_console, cloud_console)
- `test`: internal testing, app distribution, QA checklist (play_console, firebase_console)
- `release`: package name, artifact, listing, policy, release plan (play_console)
- `operate`: vitals, crash, analytics, logs, monitoring, rollout status (play_console, firebase_console, cloud_monitoring, cloud_logging)

## Cost And Usage Labels

### Android Developers
- Stage: `build`
- Cost label: `free_documentation_and_tools`
- Free: Android developer documentation, Jetpack Compose guidance, and Android Studio setup guidance are free to access.
- Paid: 
- Limits: 
- Approval required: 

### Google Play Console
- Stage: `release`
- Cost label: `one_time_registration_fee_then_release_tools`
- Free: Play Console release/testing tools are available after developer registration; internal testing can distribute builds to trusted testers.
- Paid: Developer registration has a one-time US$25 fee. Apps or in-app products using Google Play billing can be subject to service fees.
- Limits: Internal testing supports up to 100 invited testers and builds are available quickly after being added.
- Approval required: Developer registration/payment, package registration, artifact upload, release rollout, store listing changes

### Firebase
- Stage: `backend`
- Cost label: `spark_free_blaze_pay_as_you_go`
- Free: Firebase Spark plan has no-cost products and no payment method requirement for eligible usage.
- Paid: Blaze plan links billing for pay-as-you-go usage and paid Google Cloud features; no-cost quotas can still apply.
- Limits: Common no-cost products include Analytics, Crashlytics, Cloud Messaging, Remote Config, App Distribution, and others; quotas vary by product.
- Approval required: Billing plan upgrade, rules deploy, database/storage destructive change, secret/config change

### Google Cloud for Android backend
- Stage: `backend_infra`
- Cost label: `billing_project_required_for_cloud_resources`
- Free: Some Google Cloud products have free tiers or trial credits, but production resources must be checked per product.
- Paid: Cloud Run, Storage, SQL, IAM, APIs/Credentials, Vertex AI, and related services can incur usage-based costs.
- Limits: Use project, region, quota, and billing checks before resource creation.
- Approval required: API key creation, IAM change, deploy, resource create/update/delete, billing change

### Google for Developers
- Stage: `build`
- Cost label: `free_public_documentation_product_index`
- Free: Google product documentation and API discovery pages are public; product usage costs depend on the selected API.
- Paid: Maps, Cloud, AI, and other product APIs can have product-specific quotas, billing, or enablement requirements.
- Limits: Treat docs as free read-only; check each API's quota and pricing page before enabling it.
- Approval required: API enablement, OAuth consent change, credential creation, billing-linked API use

### Chrome for Developers
- Stage: `build`
- Cost label: `free_public_documentation`
- Free: Chrome, web platform, PWA, and WebView guidance is public and free to read.
- Paid: No Android release fee is tied to reading Chrome developer docs; deployment costs depend on the hosting or store channel used.
- Limits: Use for Android WebView, Trusted Web Activity, PWA, and browser compatibility guidance.
- Approval required: 

### Google Cloud APIs and Credentials
- Stage: `backend_infra`
- Cost label: `credential_surface_approval_required`
- Free: Credential pages can be inspected read-only; creating credentials is a state-changing operation.
- Paid: The APIs used by credentials may incur charges depending on product, quota, and billing project.
- Limits: Confirm project, API, OAuth consent, referrer/package restrictions, and rotation policy before creating credentials.
- Approval required: credential create/update/delete, OAuth consent publish, API enablement

### Google Cloud IAM
- Stage: `backend_infra`
- Cost label: `access_control_surface_approval_required`
- Free: IAM can be inspected read-only to understand access and service accounts.
- Paid: IAM itself is access control, but roles can permit paid resource creation or data access.
- Limits: Use least privilege and record project/member/role before any change.
- Approval required: role grant/revoke, service account key creation, policy binding change

### Cloud Run
- Stage: `backend_infra`
- Cost label: `usage_based_backend_runtime`
- Free: Cloud Run may include product-specific free usage, but project billing and quotas must be checked before deployment.
- Paid: Runtime, networking, build, logging, and dependent services can incur charges.
- Limits: Confirm region, min instances, concurrency, ingress, service account, and rollback before deploy.
- Approval required: service deploy, traffic shift, env/secret change, delete service

### Cloud Storage
- Stage: `backend_infra`
- Cost label: `usage_based_storage`
- Free: Storage configuration can be inspected read-only; no-cost usage depends on product/region/quota.
- Paid: Stored data, operations, retrieval, egress, and lifecycle choices can incur charges.
- Limits: Confirm bucket, region, IAM, lifecycle, public access, and retention before change.
- Approval required: bucket create/delete, IAM/public access change, object delete, retention/lifecycle change

### Cloud Logging
- Stage: `operate`
- Cost label: `operations_observability_usage_based`
- Free: Logs can be inspected read-only if access exists.
- Paid: Ingestion, storage, routing, and retention can have product-specific pricing.
- Limits: Define log level, retention, redaction, and alerting policy before production.
- Approval required: sink creation, retention change, alerting/routing change

### Cloud Monitoring
- Stage: `operate`
- Cost label: `operations_observability_usage_based`
- Free: Dashboards and metrics can be inspected read-only if access exists.
- Paid: Metric ingestion, uptime checks, alerting channels, and dependent services can have product-specific pricing.
- Limits: Define SLOs, alert thresholds, notification channels, and escalation rules before production.
- Approval required: alert policy change, notification channel change, dashboard create/update

### Vertex AI
- Stage: `ai_integration`
- Cost label: `usage_based_ai_cloud_service`
- Free: Docs and console inspection are read-only; model usage must be checked against current Vertex AI pricing and quotas.
- Paid: Generative AI calls, tuning, batch jobs, endpoints, storage, and logging can incur charges.
- Limits: Confirm model, region, quota, safety policy, data handling, and budget controls before calling or deploying models.
- Approval required: prompt/job execution, model deploy, endpoint create/update, quota or billing change

## Surface Verification

- `cloud_console` (console.cloud.google.com): pass, live=visited, controls=0, inputs=0, risk_controls=0
- `cloud_apis_credentials` (console.cloud.google.com): pass, live=visited, controls=9, inputs=1, risk_controls=0
- `cloud_iam` (console.cloud.google.com): pass, live=visited, controls=9, inputs=1, risk_controls=0
- `cloud_run` (console.cloud.google.com): pass, live=visited, controls=9, inputs=1, risk_controls=0
- `cloud_storage` (console.cloud.google.com): pass, live=visited, controls=9, inputs=1, risk_controls=0
- `cloud_logging` (console.cloud.google.com): pass, live=visited, controls=9, inputs=1, risk_controls=0
- `cloud_monitoring` (console.cloud.google.com): pass, live=visited, controls=9, inputs=1, risk_controls=0
- `vertex_ai` (console.cloud.google.com): pass, live=visited, controls=9, inputs=1, risk_controls=0
- `android_developers` (developer.android.com): pass, live=visited, controls=80, inputs=0, risk_controls=1
- `play_console` (play.google.com): pass, live=visited, controls=0, inputs=0, risk_controls=0
- `firebase_console` (console.firebase.google.com): pass, live=visited, controls=0, inputs=0, risk_controls=0
- `google_developers` (developers.google.com): pass, live=visited, controls=30, inputs=0, risk_controls=0
- `chrome_developers` (developer.chrome.com): pass, live=visited, controls=65, inputs=0, risk_controls=2
