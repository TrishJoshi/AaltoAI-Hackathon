# Project: Campus Pilot (incomplete)

Product: a prototype booking tool for one department.

Hosting: “probably some EU region” — the intern who set up Terraform left and
the region is not documented. We think encryption at rest might be on, and
the Terraform module comment says `storage_encrypted = true` with AES-256.

Personal data: the form collects university email addresses.

Contracts: a DPA with the cloud provider is on file.

Access: Okta + hardware keys are required before anyone can open the
production console.
