# Project: GrowthBoard (non-compliant)

Product: a marketing analytics dashboard.

Hosting: the production database is Amazon RDS in us-east-1 (N. Virginia).
Disk encryption is not enabled; we terminate TLS at the load balancer.

Personal data: yes — we ingest customer names, emails, and job titles from
the CRM.

Processors: we push events to a third-party analytics vendor. No data
processing agreement has been signed yet; legal review is “on the backlog”.

Access: the production SSH key is shared in 1Password. There is no MFA on
the cloud console for developers.
