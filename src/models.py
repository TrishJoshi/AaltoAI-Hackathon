"""Canonical data contracts for the policy–project comparator."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PolicyMeta(BaseModel):
    domain: str
    title: str
    source: str
    version: str = "1.0"


class PolicyKey(BaseModel):
    """One closed question a project must answer."""

    id: str
    question: str
    explanation: str
    value_enum: list[str] = Field(min_length=1)
    required: bool = True


class PolicySchema(BaseModel):
    meta: PolicyMeta
    keys: list[PolicyKey] = Field(min_length=1)

    def key_map(self) -> dict[str, PolicyKey]:
        return {key.id: key for key in self.keys}


class PolicyStatement(BaseModel):
    """One independently checkable rule: accepted values that constitute a pass."""

    id: str
    description: str
    accepted: dict[str, list[str]] = Field(min_length=1)


class PolicyObject(BaseModel):
    """Pass criteria only: schema with explanations and enums stripped."""

    statements: list[PolicyStatement] = Field(min_length=1)


class PolicyDocument(BaseModel):
    """Editable on-disk form: questionnaire + pass criteria together."""

    meta: PolicyMeta
    keys: list[PolicyKey] = Field(min_length=1)
    statements: list[PolicyStatement] = Field(min_length=1)

    def as_schema(self) -> PolicySchema:
        return PolicySchema(meta=self.meta, keys=self.keys)

    def as_object(self) -> PolicyObject:
        return PolicyObject(statements=self.statements)

    def key_map(self) -> dict[str, PolicyKey]:
        return {key.id: key for key in self.keys}

    @model_validator(mode="after")
    def _statements_reference_known_keys(self) -> PolicyDocument:
        known = {key.id for key in self.keys}
        enums = {key.id: set(key.value_enum) for key in self.keys}
        for statement in self.statements:
            for key_id, accepted in statement.accepted.items():
                if key_id not in known:
                    raise ValueError(
                        f"Statement {statement.id!r} references unknown key {key_id!r}"
                    )
                illegal = [value for value in accepted if value not in enums[key_id]]
                if illegal:
                    raise ValueError(
                        f"Statement {statement.id!r} accepted values {illegal} "
                        f"are not in {key_id!r} enum {sorted(enums[key_id])}"
                    )
        return self


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
