# Aalto AI System Use Standard (synthetic, for live demo)

Source: Aalto AI Office draft standard v1. Intended to be uploaded in Poliview
and turned into closed checks. Governance keeps final say on the generated
schema.

1. Human oversight
   Any AI system that produces decisions or recommendations affecting students,
   staff, or research subjects must keep a human in the loop. Fully automated
   high-impact decisions without a named reviewer are not permitted.

2. Training and fine-tuning data
   Models that process personal data of EU persons for training or fine-tuning
   must use only data with a documented lawful basis. Scraped personal data
   without a basis is forbidden. Systems that do not train or fine-tune on
   personal data may record this requirement as not applicable.

3. Transparency
   Production AI features must publish a short model card: purpose, model
   family, and known limitations. Undocumented production models are not
   allowed.

4. Logging of AI outputs
   Privileged or high-impact AI outputs (admissions, grading, hiring, or
   access-control recommendations) must be logged for at least 90 days.
   Unlogged high-impact outputs are not permitted.
