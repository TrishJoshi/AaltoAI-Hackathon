"""Review workspace: Markdown sections + merged PolicyDocument + human status."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.models import PolicyDocument, PolicyMeta


SectionStatus = Literal["pending", "covered", "no_restriction"]
VersionAction = Literal["created", "updated"]
PolicySyncAction = Literal["generate", "update", "none"]


class PolicySection(BaseModel):
    id: str
    title: str
    markdown: str
    order: int


class SectionReview(BaseModel):
    status: SectionStatus = "pending"
    note: str = ""
    needs_generation: bool = False


class DocumentVersion(BaseModel):
    version: int
    created_at: str
    filename: str
    action: VersionAction
    section_ids: list[str] = Field(default_factory=list)
    changed_section_ids: list[str] = Field(default_factory=list)


class PolicyReview(BaseModel):
    id: str
    domain: str
    source_md: str
    filename: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    sections: list[PolicySection] = Field(default_factory=list)
    document: PolicyDocument
    reviews: dict[str, SectionReview] = Field(default_factory=dict)
    versions: list[DocumentVersion] = Field(default_factory=list)

    def section_map(self) -> dict[str, PolicySection]:
        return {section.id: section for section in self.sections}

    def progress(self) -> dict[str, int]:
        counts = {"pending": 0, "covered": 0, "no_restriction": 0, "total": len(self.sections)}
        for section in self.sections:
            status = self.reviews.get(section.id, SectionReview()).status
            counts[status] = counts.get(status, 0) + 1
        return counts

    def dirty_section_ids(self) -> list[str]:
        return [
            section.id
            for section in self.sections
            if self.reviews.get(section.id, SectionReview()).needs_generation
            and self.reviews.get(section.id, SectionReview()).status != "no_restriction"
        ]

    def sync_action(self) -> PolicySyncAction:
        dirty = self.dirty_section_ids()
        if not dirty:
            return "none"
        if self.version <= 1:
            return "generate"
        return "update"


def empty_document(domain: str, title: str, source: str) -> PolicyDocument:
    return PolicyDocument(
        meta=PolicyMeta(domain=domain, title=title, source=source),
        keys=[],
        statements=[],
    )
