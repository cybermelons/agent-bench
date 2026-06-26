# On-Call Policy

## Overview
Meridian Systems operates a 24/7 on-call rotation for all production services. Every engineer on the Platform team rotates into primary on-call for one week at a time, beginning Monday at 09:00 ET.

## Rotation Schedule
- **Primary on-call:** Responsible for all pages within 5 minutes.
- **Secondary on-call:** Backup if primary does not acknowledge within 5 minutes; also the escalation path for P1 incidents.
- Rotation assignments are published in PagerDuty under the schedule named **"Platform Primary"**. Engineers can swap shifts using the `/swap` command in the `#oncall` Slack channel, subject to manager approval.

## Escalation Path
1. Page fires → Primary on-call (5-minute SLA to acknowledge).
2. Primary does not acknowledge → Secondary on-call is auto-paged.
3. Secondary does not acknowledge within 10 minutes → Incident Commander (IC) role is activated; the current IC is listed in the `#incidents` channel topic.
4. P1 incidents always require an IC regardless of acknowledgment timing.

## Compensation
- **Weekday on-call:** $50 per day stipend.
- **Weekend on-call:** $150 per day stipend.
- Stipends are processed automatically through Workday at the end of the rotation week.

## Handoff
At the end of each rotation, the outgoing primary must post a handoff note to `#oncall` covering: open incidents, recurring alerts worth watching, and any infrastructure changes made during the week.

## Prohibited Actions During On-Call
Engineers may not take vacation days or travel internationally during a primary on-call week without arranging a swap at least 72 hours in advance and notifying their team lead.
