"""Policy Agent: turn regulation or company policy text into a closed schema."""

from __future__ import annotations

import json

from src.llm import complete_json
from src.models import PolicyDocument

POLICY_AGENT_SYSTEM = """You are a governance Policy Agent for a DPO or AI Act officer.

Convert policy, regulation, or company-rule text (for example GDPR articles
on transfers, lawful basis, DPA, retention, and RoPA, or EU AI Act duties on
risk class, human oversight, logging, and model cards) into independently
checkable statements. You never judge a project. Each statement is self-contained:

1. description — the rule in plain language
2. keys — the closed questions needed to check that rule. Each key has:
   - id (stable snake_case)
   - question a project owner can answer from metadata
   - explanation telling the project parser how to choose
   - value_enum (the only legal answers)
   - accepted (the subset of value_enum that constitutes a PASS for this statement)
   - required

Rules:
- nest every question under the statement it belongs to
- include "" in value_enum only when the question is optional / not always applicable
- every accepted value must be a member of that key's value_enum
- if two statements share a question, reuse the same key id, question, and enum
- keep enums small and mutually exclusive where possible
- prefer several simple AND-statements over one complex rule
- do not invent obligations that are not in the source text
- output a single JSON object matching the provided schema
"""


def generate_policy_document(
    domain: str,
    policy_text: str,
    source: str = "",
    source_section_id: str | None = None,
) -> PolicyDocument:
    schema_hint = json.dumps(PolicyDocument.model_json_schema(), indent=2)
    user = (
        f"Domain: {domain}\n"
        f"Source label: {source or 'user-provided policy text'}\n"
    )
    if source_section_id:
        user += (
            f"Source section id: {source_section_id}\n"
            "Only extract obligations from this section. Do not invent rules from other parts of the document.\n"
        )
    user += (
        "\nPolicy text:\n"
        f"{policy_text}\n\n"
        "Return JSON matching this schema:\n"
        f"{schema_hint}\n"
    )
    document = complete_json(
        system=POLICY_AGENT_SYSTEM,
        user=user,
        response_model=PolicyDocument,
        retries=1,
    )
    if not source_section_id:
        return document
    return document.model_copy(
        update={
            "statements": [
                item.model_copy(update={"source_section_id": source_section_id})
                for item in document.statements
            ]
        }
    )
