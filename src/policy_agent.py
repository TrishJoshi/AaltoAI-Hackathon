"""Policy Agent: turn regulation or company policy text into a closed schema."""

from __future__ import annotations

import json

from src.llm import complete_json
from src.models import PolicyDocument

POLICY_AGENT_SYSTEM = """You are a governance Policy Agent.

Convert policy, regulation, or company-rule text into a CLOSED questionnaire and
independent pass criteria. You never judge a project. You only define:

1. keys — questions a project owner can answer
2. value_enum — the only legal answers for each key (closed set)
3. statements — independently checkable rules. Each statement maps key ids to
   the list of values that constitute a PASS for that rule.

Rules:
- key ids are stable snake_case
- questions must be answerable from project metadata
- explanations tell the project parser how to choose
- include "" in value_enum only when the question is optional / not always applicable
- every key referenced in statements.accepted must exist in keys
- every accepted value must be a member of that key's value_enum
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
            "keys": [
                key.model_copy(update={"source_section_id": source_section_id})
                for key in document.keys
            ],
            "statements": [
                item.model_copy(update={"source_section_id": source_section_id})
                for item in document.statements
            ],
        }
    )
