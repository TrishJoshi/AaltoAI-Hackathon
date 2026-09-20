# InfoSec data-handling policy (synthetic, for prototype demo)

Source: Internal Information Security Standard v3, aligned with GDPR Art. 32
(security of processing) and company hosting rules. Upload this file to try
a third domain after the GDPR walkthrough.

1. Personal data residency
   Personal data of EU persons must be stored in the European Union or the
   European Economic Area. Hosting in the United States or other regions is
   not permitted for production systems that process personal data.

2. Encryption at rest
   Production datastores that hold personal data must use AES-256 (or an
   equivalent approved algorithm) for encryption at rest. Transport encryption
   alone is not sufficient. Unencrypted production storage is forbidden.

3. Processor agreements
   If the project processes personal data, a data processing agreement (DPA)
   must be signed with every processor. Projects that do not process personal
   data may record this requirement as not applicable.

4. Privileged access
   Interactive access to production systems must require multi-factor
   authentication (MFA). Password-only production access is not allowed.
