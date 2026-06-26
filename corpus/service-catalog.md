# Service Catalog

## Overview
Meridian Systems maintains a registry of all internal services in the **Service Catalog** (accessible at `catalog.meridian.internal`). Every service must have a registered catalog entry before it can receive production traffic.

## Core Services

| Service Name | Owner Team | Language | SLA (Availability) |
|---|---|---|---|
| `auth-gateway` | Identity | Go | 99.99% |
| `billing-engine` | Payments | Java | 99.95% |
| `event-router` | Platform | TypeScript | 99.9% |
| `search-indexer` | Data | Python | 99.5% |
| `notification-hub` | Growth | TypeScript | 99.9% |

## Registering a New Service
To register a new service, create a YAML manifest at `catalog/services/<service-name>.yaml` with the following required fields:
- `name`: the service identifier (lowercase, hyphenated)
- `owner`: the team slug (must match a team in `teams.yaml`)
- `language`: primary language
- `sla_percent`: the agreed availability target
- `runbook_url`: link to the service runbook in Confluence

Open a pull request to the `platform/catalog` repository. The PR must be approved by the **Platform Ops** team before merging.

## Deprecation Process
A service must be in `deprecated` status for at least **90 days** before it can be removed from the catalog. During the deprecation window, traffic must be drained and all dependent services must migrate to the replacement.

## SLA Reporting
SLA compliance is computed monthly by the **Reliability Dashboard** at `reliability.meridian.internal`. Breaches are reported to the owning team's engineering manager within 24 hours of month close.
