# Project: GrowthBoard (non-compliant)

Product: a marketing analytics dashboard for CRM contacts of EU customers.

Hosting: the production database is Amazon RDS in us-east-1 (N. Virginia).
EU personal data is processed in the United States without an adequacy
decision or other approved transfer tool.

Personal data: yes — we ingest customer names, emails, and job titles from
the CRM.

Lawful basis: legitimate interest for CRM analytics (balancing test on file).

Processors: AWS has a DPA on file. Events also go to a third-party analytics
vendor.

Retention: event logs and CRM extracts are kept indefinitely. The DPO has not
confirmed a RoPA row.
