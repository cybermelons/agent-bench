# Access Provisioning

## Overview
All access to Meridian's production systems is managed through **Vault** (HashiCorp) and the internal **AccessBot** in Slack. Engineers must never share credentials or use personal accounts for service authentication.

## Requesting Access
To request access to a production system:
1. Run `/access request <system> <role>` in Slack. Valid roles are `read`, `write`, and `admin`.
2. AccessBot opens a ticket in the `SEC` Jira project and notifies the system owner.
3. The system owner (or a designated approver) must approve within **48 hours**; otherwise the request auto-expires and must be re-submitted.
4. Once approved, Vault issues a time-limited token valid for **8 hours**. Tokens are not renewable; engineers must re-request after expiry.

## Just-In-Time (JIT) Access
For emergency production access during incidents, engineers can request JIT access via `/access jit <system>`. JIT access:
- Requires approval from the current on-call primary or an IC.
- Is valid for **1 hour** only.
- Is automatically logged to the `#access-audit` channel.
- Triggers an alert to the Security team if used more than **3 times in a 7-day window** by the same engineer.

## Admin Access
`admin` role requests require two approvals: the system owner **and** a member of the Security team. Admin tokens are valid for **4 hours** (shorter than standard write tokens).

## Offboarding
When an engineer leaves Meridian, IT triggers an automated offboarding job that revokes all active Vault tokens and AccessBot grants within **2 hours** of the departure date.
