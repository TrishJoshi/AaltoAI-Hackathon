"""Project Parser: fill policy keys from project metadata using closed enums."""

from __future__ import annotations

import json

from src.llm import complete_json
from src.models import PolicyKey, ProjectParseResponse, UnmappedAnswer

PROJECT_PARSER_SYSTEM = """You are a Project Parser AI Agent.

You read project metadata (hosting region, processors, retention, RoPA, and
AI features such as lead scoring or model cards) and answer a batch of policy
keys. You never decide pass or fail. You only pick values from each key's
value_enum. Typical GDPR keys include data_residency and retention_policy;
typical EU AI Act keys include human_oversight and model_card.

Hard rules:
- Every answer MUST be exactly one string from that key's value_enum.
- If the question is not relevant and "" is in value_enum, answer "".
- If the true answer is not in value_enum, do NOT guess. Put the key in
  "unmapped" with proposed_answer, the enum you were given, and a reason.
  Do not also put a guessed value in "answers" for that key.
- Prefer evidence in the project metadata over assumptions.
- If metadata is silent and the key is required, still pick the closest enum
  member only when it is clearly implied; otherwise unmapped.
- Return JSON only: {"answers": {key_id: value}, "unmapped": [...]}
"""


def parse_project_keys(
    *,
    project_metadata: str,
    keys: list[PolicyKey],
    previous_invalid: dict[str, str] | None = None,
    previous_unmapped: list[UnmappedAnswer] | None = None,
) -> ProjectParseResponse:
    if not keys:
        return ProjectParseResponse()

    payload = [
        {
            "id": key.id,
            "question": key.question,
            "explanation": key.explanation,
            "value_enum": key.value_enum,
            "required": key.required,
        }
        for key in keys
    ]
    user_parts = [
        "Project metadata:\n",
        project_metadata,
        "\n\nKeys to fill (choose only from value_enum):\n",
        json.dumps(payload, indent=2),
    ]
    if previous_invalid:
        user_parts.append(
            "\n\nThese previous answers were REJECTED because they are not in "
            "value_enum. Choose a legal value or mark unmapped:\n"
            f"{json.dumps(previous_invalid, indent=2)}"
        )
    if previous_unmapped:
        user_parts.append(
            "\n\nThese keys were previously unmapped. Try again only if a value_enum "
            "member now clearly fits; otherwise keep them unmapped:\n"
            f"{json.dumps([item.model_dump() for item in previous_unmapped], indent=2)}"
        )
    user_parts.append(
        "\n\nReturn JSON matching:\n"
        f"{json.dumps(ProjectParseResponse.model_json_schema(), indent=2)}"
    )
    return complete_json(
        system=PROJECT_PARSER_SYSTEM,
        user="".join(user_parts),
        response_model=ProjectParseResponse,
        retries=1,
    )
