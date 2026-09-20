"""Document repo versioning and upload update rules."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.review_models import SectionReview
from src.review_store import create_review, load_review, update_review_from_markdown
from webapp.app import PDF_LATER, _read_markdown_upload, app


def test_create_review_starts_at_v1(tmp_path, monkeypatch):
    monkeypatch.setattr("src.review_store.REVIEWS_DIR", tmp_path)
    markdown = "# Policy\n\n## Residency\nStore in the EU.\n\n## Encryption\nUse AES-256.\n"
    review = create_review(domain="InfoSec", markdown=markdown, source_md="policy.md", filename="policy.md")
    assert review.version == 1
    assert review.versions[0].action == "created"
    assert (tmp_path / review.id / "versions" / "1" / "source.md").exists()
    dirty = review.dirty_section_ids()
    assert "sec_residency" in dirty
    assert "sec_encryption" in dirty
    assert review.sync_action() == "generate"


def test_update_bumps_version_and_marks_changed_sections(tmp_path, monkeypatch):
    monkeypatch.setattr("src.review_store.REVIEWS_DIR", tmp_path)
    original = "# Policy\n\n## Residency\nStore in the EU.\n\n## Encryption\nUse AES-256.\n"
    review = create_review(domain="InfoSec", markdown=original, source_md="policy.md", filename="policy.md")
    covered = dict(review.reviews)
    covered["sec_residency"] = SectionReview(status="covered", needs_generation=False)
    covered["sec_encryption"] = SectionReview(status="covered", needs_generation=False)
    review = review.model_copy(update={"reviews": covered})
    updated_md = "# Policy\n\n## Residency\nStore in the EU.\n\n## Encryption\nUse AES-256 or equivalent.\n"
    updated = update_review_from_markdown(review, updated_md, "policy-v2.md")
    assert updated.version == 2
    assert updated.versions[-1].action == "updated"
    assert updated.versions[-1].filename == "policy-v2.md"
    assert "sec_encryption" in updated.versions[-1].changed_section_ids
    assert "sec_residency" not in updated.versions[-1].changed_section_ids
    assert updated.reviews["sec_residency"].status == "covered"
    assert updated.reviews["sec_encryption"].status == "pending"
    assert updated.reviews["sec_encryption"].needs_generation is True
    assert updated.sync_action() == "update"
    v1 = (tmp_path / updated.id / "versions" / "1" / "source.md").read_text(encoding="utf-8")
    v2 = (tmp_path / updated.id / "versions" / "2" / "source.md").read_text(encoding="utf-8")
    assert "equivalent" not in v1
    assert "equivalent" in v2
    reloaded = load_review(updated.id)
    assert reloaded.version == 2


def test_pdf_upload_is_rejected_with_later_message():
    try:
        _read_markdown_upload("policy.pdf", b"%PDF-fake")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "later" in exc.detail.lower()
        assert exc.detail == PDF_LATER


def test_upload_new_policy_via_api(tmp_path, monkeypatch):
    monkeypatch.setattr("src.review_store.REVIEWS_DIR", tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/reviews/upload",
        data={"domain": "InfoSec", "review_id": "", "title": "Access policy"},
        files={"file": ("new-policy.md", b"# Policy\n\n## Access\nRequire MFA.\n", "text/markdown")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["sync_action"] == "generate"
    assert body["filename"] == "new-policy.md"
    assert body["title"] == "Access policy"


def test_save_with_checks_writes_policies_folder(tmp_path, monkeypatch):
    reviews = tmp_path / "reviews"
    policies = tmp_path / "policies"
    monkeypatch.setattr("src.review_store.REVIEWS_DIR", reviews)
    monkeypatch.setattr("src.review_store.POLICIES_DIR", policies)
    from src.models import PolicyDocument, PolicyKey, PolicyMeta, PolicyStatement
    from src.review_store import save_review

    markdown = "# Policy\n\n## Access\nRequire MFA.\n"
    review = create_review(domain="InfoSec", markdown=markdown, source_md="policy.md", filename="policy.md")
    assert not (policies / f"{review.id}.json").exists()
    document = PolicyDocument(
        meta=PolicyMeta(domain="InfoSec", title="Access policy", source="policy.md"),
        keys=[
            PolicyKey(
                id="mfa",
                question="MFA?",
                explanation="Console MFA",
                value_enum=["yes", "no"],
            )
        ],
        statements=[
            PolicyStatement(id="stmt_mfa", description="MFA required", accepted={"mfa": ["yes"]})
        ],
    )
    save_review(review.model_copy(update={"document": document}))
    exported = policies / f"{review.id}.json"
    assert exported.exists()
    payload = exported.read_text(encoding="utf-8")
    assert "stmt_mfa" in payload
    assert "mfa" in payload


def test_delete_review_removes_workspace_and_policy_json(tmp_path, monkeypatch):
    reviews = tmp_path / "reviews"
    policies = tmp_path / "policies"
    monkeypatch.setattr("src.review_store.REVIEWS_DIR", reviews)
    monkeypatch.setattr("src.review_store.POLICIES_DIR", policies)
    from src.models import PolicyDocument, PolicyKey, PolicyMeta, PolicyStatement
    from src.review_store import delete_review, save_review

    markdown = "# Policy\n\n## Access\nRequire MFA.\n"
    review = create_review(domain="InfoSec", markdown=markdown, source_md="policy.md", filename="policy.md")
    document = PolicyDocument(
        meta=PolicyMeta(domain="InfoSec", title="Access policy", source="policy.md"),
        keys=[
            PolicyKey(
                id="mfa",
                question="MFA?",
                explanation="Console MFA",
                value_enum=["yes", "no"],
            )
        ],
        statements=[
            PolicyStatement(id="stmt_mfa", description="MFA required", accepted={"mfa": ["yes"]})
        ],
    )
    save_review(review.model_copy(update={"document": document}))
    assert (reviews / review.id).exists()
    assert (policies / f"{review.id}.json").exists()
    delete_review(review.id)
    assert not (reviews / review.id).exists()
    assert not (policies / f"{review.id}.json").exists()


def test_delete_policy_via_api(tmp_path, monkeypatch):
    reviews = tmp_path / "reviews"
    policies = tmp_path / "policies"
    monkeypatch.setattr("src.review_store.REVIEWS_DIR", reviews)
    monkeypatch.setattr("src.review_store.POLICIES_DIR", policies)
    client = TestClient(app)
    created = client.post(
        "/api/reviews/upload",
        data={"domain": "InfoSec", "review_id": "", "title": "Temp policy"},
        files={"file": ("temp.md", b"# Policy\n\n## Access\nRequire MFA.\n", "text/markdown")},
    )
    assert created.status_code == 200
    review_id = created.json()["id"]
    response = client.delete(f"/api/reviews/{review_id}")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    missing = client.get(f"/api/reviews/{review_id}")
    assert missing.status_code == 404


def test_new_upload_requires_a_name(tmp_path, monkeypatch):
    monkeypatch.setattr("src.review_store.REVIEWS_DIR", tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/reviews/upload",
        data={"domain": "InfoSec", "review_id": "", "title": ""},
        files={"file": ("new-policy.md", b"# Policy\n\n## Access\nRequire MFA.\n", "text/markdown")},
    )
    assert response.status_code == 400
