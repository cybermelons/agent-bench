# Deploy Process: Production Environment

## Overview
Production deploys at Meridian Systems require a completed staging validation and at least one approval from a senior engineer or team lead. Production runs on the **us-east-1** and **eu-west-2** clusters; deploys roll out to **us-east-1 first**, with a 10-minute observation window before proceeding to **eu-west-2**.

## Prerequisites
Before triggering a production deploy:
1. The staging deploy for the same image tag must show status `READY`.
2. A deploy request (DR) must be opened in the internal Jira project **PLAT** and approved by at least one person with the `release-approver` role.
3. The current on-call primary must be notified via the `/notify-oncall` Slack command.

## Triggering a Production Deploy
```
meridian deploy --env production --service <service-name> --tag <image-tag> --dr PLAT-<number>
```

The `--dr` flag is mandatory; the CLI will reject deploys without a linked DR.

## Rollback
If the error rate on any endpoint exceeds **2% over a 5-minute window** during or after a deploy, the Canary Runner automatically initiates a rollback to the previous image tag. Engineers can also trigger a manual rollback with:

```
meridian rollback --env production --service <service-name>
```

## Freeze Windows
Production deploys are **frozen** from **December 20 through January 2** (inclusive) every year, and for 48 hours before any scheduled maintenance window. Freeze windows are listed in the `#deploy-freeze` Slack channel.

## Post-Deploy
After a successful production deploy, the deploying engineer must update the DR in Jira with the final image tag and close it. Failure to close DRs within 24 hours triggers an automated reminder.
