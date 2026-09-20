"""Project-facing compliance health snapshot (one or more policy results)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Contact(BaseModel):
    name: str
    role: Literal["owner", "member"] = "member"
    title: str = ""
    email: str = ""
    organization: str = ""


class Remediation(BaseModel):
    """What the project can do after a failed or incomplete check."""

    actions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)


class HealthStatement(BaseModel):
    statement_id: str
    description: str = ""
    status: Literal["pass", "fail", "missinginfo"]
    detail: str = ""
    mismatched_keys: list[str] = Field(default_factory=list)
    missing_keys: list[str] = Field(default_factory=list)
    answers: dict[str, str] = Field(default_factory=dict)
    accepted: dict[str, list[str]] = Field(default_factory=dict)
    questions: dict[str, str] = Field(default_factory=dict)
    why: str = ""
    remediation: Remediation = Field(default_factory=Remediation)


class PolicyHealth(BaseModel):
    policy_id: str
    title: str
    domain: str
    version: str = "1.0"
    source: str = ""
    organization: str = ""
    owners: list[Contact] = Field(default_factory=list)
    results: list[HealthStatement] = Field(default_factory=list)

    def counts(self) -> dict[str, int]:
        passed = sum(1 for item in self.results if item.status == "pass")
        failed = sum(1 for item in self.results if item.status == "fail")
        missing = sum(1 for item in self.results if item.status == "missinginfo")
        total = len(self.results)
        return {
            "passed": passed,
            "failed": failed,
            "missing": missing,
            "total": total,
            "pass_pct": round(100 * passed / total) if total else 0,
        }


class HealthSnapshot(BaseModel):
    """Aggregated last health check for a project across applying policies."""

    id: str
    label: str = ""
    kind: Literal["demo", "workspace"] = "workspace"
    project_name: str = ""
    project_source: str = ""
    validated_at: str = ""
    overall_status: Literal["pass", "fail", "missinginfo"] = "pass"
    policies: list[PolicyHealth] = Field(default_factory=list)

    def totals(self) -> dict[str, int]:
        passed = failed = missing = 0
        for policy in self.policies:
            counts = policy.counts()
            passed += counts["passed"]
            failed += counts["failed"]
            missing += counts["missing"]
        total = passed + failed + missing
        return {
            "passed": passed,
            "failed": failed,
            "missing": missing,
            "total": total,
            "pass_pct": round(100 * passed / total) if total else 0,
        }

    def computed_status(self) -> Literal["pass", "fail", "missinginfo"]:
        statuses = {item.status for policy in self.policies for item in policy.results}
        if "fail" in statuses:
            return "fail"
        if "missinginfo" in statuses:
            return "missinginfo"
        return "pass"
