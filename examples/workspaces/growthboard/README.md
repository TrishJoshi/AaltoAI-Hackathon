# GrowthBoard

Marketing analytics dashboard for CRM contacts (EU customers).

## Hosting

Production database: Amazon RDS in us-east-1 (N. Virginia).
Disk encryption is not enabled; TLS terminates at the load balancer.

## Personal data

We ingest customer names, emails, and job titles from the CRM.

## Processors

Events go to a third-party analytics vendor that is not on the approved list.
A DPA with the cloud provider is on file.

## Access

The production SSH key is shared in 1Password. There is no MFA on the
cloud console for developers.
