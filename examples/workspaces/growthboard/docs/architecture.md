# Architecture notes

GrowthBoard is a three-tier app: React UI, API, and Amazon RDS.

Traffic: CloudFront → ALB (TLS) → ECS → RDS (us-east-1).
Object exports land in an S3 bucket in the same region.

CRM sync runs hourly and stores names, emails, and job titles.
Analytics events (including user ids) are forwarded to an external vendor.
Event logs and CRM extracts are kept indefinitely for product research.
A lead-scoring model ranks contacts with no human reviewer.

Open questions for compliance:
- Can RDS move to eu-north-1 without breaking the CRM connector?
- Is GrowthBoard listed in the organisation RoPA?
