# Project: Nordic Notes (compliant)

Product: a notes app for EU universities.

Hosting: AWS eu-north-1 (Stockholm). All user content and account emails live in
an RDS PostgreSQL instance in that region. RDS encryption at rest is enabled
with AWS-managed AES-256 keys.

Personal data: yes — we store student email addresses and note text.

Processors: AWS is the only processor. A GDPR data processing agreement is
signed and stored in the contracts folder.

Access: production AWS console and SSH bastion require hardware security keys
(MFA). Password-only login is disabled.
