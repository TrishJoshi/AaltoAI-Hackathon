"""Canonical data contracts for the policy–project comparator."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyMeta(BaseModel):
    domain: str
    title: str
    source: str
    version: str = "1.0"


class PolicyKey(BaseModel):
    """One closed question a project must answer (flattened questionnaire)."""

    id: str
    question: str
    explanation: str
    value_enum: list[str] = Field(min_length=1)
    required: bool = True
    source_section_id: str | None = None


class StatementKey(BaseModel):
    """Closed question nested under one statement, including pass values."""

    id: str
    question: str
    explanation: str
    value_enum: list[str] = Field(min_length=1)
    accepted: list[str] = Field(min_length=1)
    required: bool = True

    @model_validator(mode="after")
    def _accepted_in_enum(self) -> StatementKey:
        illegal = [value for value in self.accepted if value not in self.value_enum]
        if illegal:
            raise ValueError(
                f"Key {self.id!r} accepted values {illegal} are not in "
                f"enum {list(self.value_enum)}"
            )
        return self

    def as_policy_key(self, source_section_id: str | None = None) -> PolicyKey:
        return PolicyKey(
            id=self.id,
            question=self.question,
            explanation=self.explanation,
            value_enum=list(self.value_enum),
            required=self.required,
            source_section_id=source_section_id,
        )


class PolicySchema(BaseModel):
    meta: PolicyMeta
    keys: list[PolicyKey] = Field(min_length=1)

    def key_map(self) -> dict[str, PolicyKey]:
        return {key.id: key for key in self.keys}


class PolicyStatement(BaseModel):
    """One independently checkable rule: nested questions + accepted values."""

    model_config = ConfigDict(exclude_none=True)

    id: str
    description: str
    keys: list[StatementKey] = Field(min_length=1)
    source_section_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _legacy_accepted_dict(cls, data):
        if not isinstance(data, dict):
            return data
        if "keys" in data or "accepted" not in data:
            return data
        accepted = data.get("accepted") or {}
        lifted = {key: value for key, value in data.items() if key != "accepted"}
        lifted["keys"] = [
            {
                "id": key_id,
                "question": key_id,
                "explanation": "",
                "value_enum": list(values) if values else [""],
                "accepted": list(values),
                "required": True,
            }
            for key_id, values in accepted.items()
        ]
        return lifted

    @property
    def accepted(self) -> dict[str, list[str]]:
        """Pass criteria as {key_id: accepted values} for the comparator."""
        return {key.id: list(key.accepted) for key in self.keys}


class PolicyObject(BaseModel):
    """Pass criteria only: schema with explanations and enums stripped."""

    statements: list[PolicyStatement] = Field(min_length=1)


class PolicyDocument(BaseModel):
    """Editable on-disk form: each statement owns its questions and pass values."""

    meta: PolicyMeta
    statements: list[PolicyStatement] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _nest_legacy_keys(cls, data):
        if not isinstance(data, dict):
            return data
        catalog = data.get("keys")
        statements = data.get("statements")
        if catalog is None:
            return data
        key_map = {_item_id(item): _item_dump(item) for item in catalog}
        nested = [_attach_catalog_keys(item, key_map) for item in statements or []]
        lifted = {key: value for key, value in data.items() if key != "keys"}
        lifted["statements"] = nested
        return lifted

    def as_schema(self) -> PolicySchema:
        return PolicySchema(meta=self.meta, keys=self.keys)

    def as_object(self) -> PolicyObject:
        return PolicyObject(statements=self.statements)

    @property
    def keys(self) -> list[PolicyKey]:
        """Unique questions across statements, for the project questionnaire."""
        seen: set[str] = set()
        ordered: list[PolicyKey] = []
        for statement in self.statements:
            for key in statement.keys:
                if key.id in seen:
                    continue
                seen.add(key.id)
                ordered.append(key.as_policy_key(statement.source_section_id))
        return ordered

    def key_map(self) -> dict[str, PolicyKey]:
        return {key.id: key for key in self.keys}

    @model_validator(mode="after")
    def _consistent_key_definitions(self) -> PolicyDocument:
        seen: dict[str, StatementKey] = {}
        for statement in self.statements:
            for key in statement.keys:
                previous = seen.get(key.id)
                if previous and _key_signature(previous) != _key_signature(key):
                    raise ValueError(
                        f"Key {key.id!r} has conflicting question or enum "
                        f"across statements {statement.id!r}"
                    )
                seen[key.id] = key
        return self


def _item_id(item) -> str:
    if isinstance(item, dict):
        return str(item["id"])
    return str(item.id)


def _item_dump(item) -> dict:
    if isinstance(item, dict):
        return item
    return item.model_dump()


def _attach_catalog_keys(statement, key_map: dict[str, dict]):
    payload = _item_dump(statement) if not isinstance(statement, dict) else dict(statement)
    accepted = payload.get("accepted") or {}
    existing_keys = payload.get("keys") or []
    if existing_keys:
        merged = []
        for key in existing_keys:
            spec = _item_dump(key)
            catalog = key_map.get(spec.get("id", ""))
            if catalog:
                spec = {
                    **catalog,
                    **{field: spec[field] for field in spec if field in {"accepted", "id"}},
                    "id": spec.get("id") or catalog["id"],
                    "accepted": spec.get("accepted") or accepted.get(spec.get("id"), []),
                }
            spec.pop("source_section_id", None)
            merged.append(spec)
        payload["keys"] = merged
        payload.pop("accepted", None)
        return payload
    payload["keys"] = [
        {
            **{
                field: value
                for field, value in key_map.get(key_id, {}).items()
                if field != "source_section_id"
            },
            "id": key_id,
            "question": key_map.get(key_id, {}).get("question", key_id),
            "explanation": key_map.get(key_id, {}).get("explanation", ""),
            "value_enum": key_map.get(key_id, {}).get("value_enum") or list(values),
            "accepted": list(values),
            "required": key_map.get(key_id, {}).get("required", True),
        }
        for key_id, values in accepted.items()
    ]
    payload.pop("accepted", None)
    return payload


def _key_signature(key: StatementKey) -> tuple[str, tuple[str, ...]]:
    return (" ".join(key.question.lower().split()), tuple(key.value_enum))


class ProjectObject(BaseModel):
    """Closed answers for policy keys. Empty string means unanswered / not relevant."""

    answers: dict[str, str] = Field(default_factory=dict)


class UnmappedAnswer(BaseModel):
    key: str
    proposed_answer: str
    enum: list[str]
    reason: str


class ProjectParseResponse(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    unmapped: list[UnmappedAnswer] = Field(default_factory=list)


class StatementResult(BaseModel):
    statement_id: str
    description: str = ""
    status: Literal["pass", "fail", "missinginfo"]
    detail: str
    mismatched_keys: list[str] = Field(default_factory=list)
    missing_keys: list[str] = Field(default_factory=list)


class UserInputRequired(BaseModel):
    key: str
    enum: list[str]
    proposed_answer: str | None = None
    reason: str
    attempts: int = 3


class ResultsObject(BaseModel):
    policy_title: str = ""
    policy_domain: str = ""
    project_source: str = ""
    results: list[StatementResult] = Field(default_factory=list)
    user_input_required: list[UserInputRequired] = Field(default_factory=list)
    project_object: ProjectObject = Field(default_factory=ProjectObject)

    def overall_status(self) -> Literal["pass", "fail", "missinginfo"]:
        statuses = {item.status for item in self.results}
        if "fail" in statuses:
            return "fail"
        if "missinginfo" in statuses or self.user_input_required:
            return "missinginfo"
        return "pass"
