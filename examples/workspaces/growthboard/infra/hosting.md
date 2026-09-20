# Hosting and access

Region: us-east-1
RDS storage encryption: off
ALB: TLS 1.2
Backups: 35-day encrypted snapshots (API setting), older plaintext copies exist
Retention: event logs and CRM extracts have no deletion job

## Privileged access

- AWS console: password only, no org-wide MFA
- Production SSH: one key stored in the shared 1Password vault
- On-call: listed in the service catalogue (incident contact: yes)

Central logging (CloudTrail → SIEM) is enabled.
