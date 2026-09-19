"""Review workspace: Markdown sections + merged PolicyDocument + human status."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.models import PolicyDocument, PolicyMeta


SectionStatus = Literal["pending", "covered", "no_restriction"]


class PolicySection(BaseModel):
    id: str
    title: str
    markdown: str
    order: int


class SectionReview(BaseModel):
    status: SectionStatus = "pending"
    note: str = ""


class PolicyReview(BaseModel):
    id: str
    domain: str
    source_md: str
    sections: list[PolicySection] = Field(default_factory=list)
    document: PolicyDocument
    reviews: dict[str, SectionReview] = Field(default_factory=dict)

    def section_map(self) -> dict[str, PolicySection]:
        return {section.id: section for section in self.sections}

    def progress(self) -> dict[str, int]:
        counts = {"pending": 0, "covered": 0, "no_restriction": 0, "total": len(self.sections)}
        for section in self.sections:
            status = self.reviews.get(section.id, SectionReview()).status
            counts[status] = counts.get(status, 0) + 1
        return counts


def empty_document(domain: str, title: str, source: str) -> PolicyDocument:
    return PolicyDocument(
        meta=PolicyMeta(domain=domain, title=title, source=source),
        keys=[],
        statements=[],
    )
