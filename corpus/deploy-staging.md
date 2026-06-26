# Deploy Process: Staging Environment

## Overview
The staging environment at Meridian Systems mirrors production infrastructure but runs on reduced capacity (50% node count). It is used for final integration testing before a production release.

## Triggering a Staging Deploy
Any engineer can trigger a staging deploy by running:

```
meridian deploy --env staging --service <service-name> --tag <image-tag>
```

The deploy CLI authenticates against the **Meridian Internal Registry (MIR)** and streams logs to your terminal. A successful deploy prints `DEPLOY OK: staging/<service-name>@<tag>`.

## Automated Smoke Tests
After every staging deploy, the **Canary Runner** service automatically executes the smoke-test suite for the affected service. Smoke tests must all pass before the deploy is marked `READY`. If any test fails, the deploy is rolled back automatically and an alert is posted to `#staging-alerts`.

## Environment-Specific Behavior
- **Feature flags:** All feature flags default to `enabled` in staging to maximize test coverage.
- **External integrations:** Third-party webhooks are routed to Meridian's mock-webhook relay (`mock-hooks.staging.meridian.internal`) to prevent real-world side effects.
- **Database:** Staging uses a daily snapshot of the production database, anonymized via the `anon-snap` pipeline. Data is at most 24 hours stale.

## Retention Policy
Staging deploys are automatically cleaned up after **7 days** if not promoted to production. Engineers wishing to preserve a staging build beyond 7 days must tag it with `keep:true` in the deploy manifest.
