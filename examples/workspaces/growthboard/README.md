# GrowthBoard

Project metadata for **Check compliance**. These files are compared to the sample **GDPR** (personal data: transfers, DPA, retention, RoPA) and **EU AI Act** (risk class, human oversight, model card) policies. Check compliance fills answers from this metadata. The comparator — not the model — picks pass, fail, or missing info.

| Key | Value |
| --- | --- |
| Product | Marketing analytics dashboard for EU CRM contacts |
| Hosting region | `us-east-1` (N. Virginia) |
| Personal data | names, emails, job titles |
| Lawful basis | legitimate interest |
| Processors | AWS (DPA on file) · unlisted analytics SaaS (no DPA) |
| Retention | indefinite · RoPA not confirmed |
| AI | high-risk lead scoring · no named reviewer · no model card |

## Hosting

Production database: Amazon RDS in us-east-1 (N. Virginia).
EU personal data is transferred to the United States without an adequacy
decision.

## Personal data

We ingest customer names, emails, and job titles from the CRM.
Lawful basis on file: legitimate interest.

## Processors

Events go to a third-party analytics vendor. A DPA with the cloud provider
is on file.

## Retention

Event logs and CRM extracts are kept indefinitely for product research.
No RoPA row has been confirmed.

## AI

A lead-scoring model ranks contacts automatically. No named reviewer.
No model card.
