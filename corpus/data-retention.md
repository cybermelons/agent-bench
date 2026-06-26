# Data Retention Policy

## Overview
Meridian Systems retains customer data according to contractual and regulatory obligations. This document defines retention tiers, deletion schedules, and the engineer's responsibilities when building data-storing features.

## Retention Tiers

| Tier | Retention Period | Example Data |
|---|---|---|
| Tier 1 — Transactional | 7 years | Billing records, invoices, payment events |
| Tier 2 — Operational | 2 years | Application logs, audit trails, access logs |
| Tier 3 — Ephemeral | 90 days | Session tokens, temporary uploads, debug snapshots |
| Tier 4 — Derived | 1 year | Analytics aggregates, ML feature vectors |

## Deletion Process
At the end of a retention period, data is soft-deleted (marked `deleted_at`) for **30 days** to allow dispute resolution, then hard-deleted by the **Reaper** batch job that runs nightly at **02:00 UTC**.

## Engineer Responsibilities
When building a feature that stores new data, engineers must:
1. Classify the data into one of the four tiers in the service's data-map document.
2. Annotate the database column or object storage prefix with the retention tier using the `@retention(tier=N)` metadata convention.
3. Open a `SEC` Jira ticket to request a review from the Privacy team before shipping to production.

## Exceptions
Retention extensions beyond the standard periods require written approval from Meridian's **Chief Privacy Officer (CPO)** and must be documented in the Legal hold registry at `legal.meridian.internal/holds`.

## Audit
The Privacy team audits all Tier 1 and Tier 2 data stores quarterly. Engineers are notified if their service is selected for audit with at least **5 business days** notice.
