"""Generate or refresh closed checks for sections that need them."""

from __future__ import annotations

from src.llm import QuotaExceededError
from src.policy_agent import generate_policy_document
from src.policy_merge import merge_generated_document
from src.review_models import PolicyReview, SectionReview
from src.review_store import save_review

GENERATE_BATCH = 5


def generate_needed_policies(
    review: PolicyReview,
    *,
    limit: int = GENERATE_BATCH,
) -> tuple[PolicyReview, list[str], list[str], int]:
    """Run the policy agent on dirty sections. Saves after each success.

    Returns (review, generated_ids, errors, remaining_dirty).
    """
    generated: list[str] = []
    errors: list[str] = []
    document = review.document
    reviews = dict(review.reviews)
    remaining = review.dirty_section_ids()
    batch = remaining[: max(1, limit)]
    quota_hit = False
    for section_id in batch:
        section = review.section_map()[section_id]
        try:
            fragment = generate_policy_document(
                domain=review.domain,
                policy_text=section.markdown,
                source=review.source_md,
                source_section_id=section_id,
            )
            document = merge_generated_document(document, fragment, section_id)
            previous = reviews.get(section_id, SectionReview())
            reviews[section_id] = previous.model_copy(update={"needs_generation": False})
            generated.append(section_id)
            review = review.model_copy(update={"document": document, "reviews": reviews})
            save_review(review)
        except QuotaExceededError as exc:
            errors.append(str(exc))
            quota_hit = True
            break
        except Exception as exc:
            errors.append(f"{section.title}: {exc}")
            if "429" in str(exc) or "quota" in str(exc).lower():
                quota_hit = True
                break
    leftover = len(
        [
            section_id
            for section_id in review.dirty_section_ids()
        ]
    )
    return review, generated, errors, leftover
