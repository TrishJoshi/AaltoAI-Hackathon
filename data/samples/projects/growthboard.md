# Project: GrowthBoard (GDPR fail)

Product: a marketing analytics dashboard for CRM contacts of EU customers.

Hosting: the production database is Amazon RDS in us-east-1 (N. Virginia).
EU personal data is processed in the United States without an adequacy
decision or other approved transfer tool.

Personal data: yes — customer names, emails, and job titles from the CRM.

Lawful basis: the team recorded legitimate interest for CRM analytics.

Processors: AWS has a DPA on file. Events also go to a third-party analytics
vendor.

Retention: event logs and CRM extracts are kept indefinitely for product
research. No RoPA row has been confirmed with the DPO.

Access: the production SSH key is shared in 1Password. There is no MFA on
the cloud console for developers.

AI: a lead-scoring model ranks contacts automatically. There is no named
reviewer and no model card.
