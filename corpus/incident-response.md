# Incident Response Runbook

## Severity Levels
Meridian uses four severity levels:

| Level | Name | Definition | Response SLA |
|---|---|---|---|
| P1 | Critical | Complete service outage or data loss risk | 15 minutes |
| P2 | High | Degraded service affecting >10% of users | 30 minutes |
| P3 | Medium | Partial degradation, workaround exists | 2 hours |
| P4 | Low | Cosmetic or non-impacting issue | Next business day |

## Declaring an Incident
Any engineer can declare an incident by running `/incident declare` in Slack. The bot creates a dedicated `#inc-<id>` channel and assigns the declaring engineer as the initial **Incident Commander (IC)**.

## Incident Commander Responsibilities
- Coordinate investigation and communication.
- Post status updates to `#incidents` every **15 minutes** during P1/P2 incidents.
- Notify the VP of Engineering for any P1 incident within **30 minutes** of declaration.
- Write a post-mortem within **5 business days** of incident resolution.

## War Room
For P1 incidents, a Zoom war room is auto-created at `meridian.zoom.us/war-room` and pinned in the incident channel.

## Post-Mortem Requirements
Post-mortems are blameless and must include:
1. Timeline of events (UTC timestamps).
2. Root cause analysis.
3. Three or more action items with owners and due dates.
4. Customer impact summary (number of affected users and duration).

Post-mortems are stored in Confluence under the **Incidents** space and linked from the incident Jira ticket.
