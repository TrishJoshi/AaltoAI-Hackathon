"""Compliance guide chat for project owners."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from src.health_models import HealthSnapshot, HealthStatement, PolicyHealth


class GuideReply(BaseModel):
    reply: str
    suggested_prompts: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: str
    content: str


def guide_project_owner(
    *,
    snapshot: HealthSnapshot,
    messages: list[ChatMessage],
    active_file: str = "",
    file_excerpt: str = "",
    focus_policy_id: str = "",
) -> GuideReply:
    """Answer with the configured model when available; otherwise a deterministic fallback."""
    try:
        from src.llm import complete_json, get_api_key

        get_api_key()
        return complete_json(
            system=_system_prompt(),
            user=_user_prompt(snapshot, messages, active_file, file_excerpt, focus_policy_id),
            response_model=GuideReply,
            retries=1,
        )
    except Exception:
        return fallback_guide(
            messages[-1].content if messages else "",
            snapshot,
            active_file=active_file,
        )


def fallback_guide(question: str, snapshot: HealthSnapshot, active_file: str = "") -> GuideReply:
    failed = _failed_checks(snapshot)
    missing = _missing_checks(snapshot)
    prompts = _default_prompts(snapshot)
    if not failed and not missing:
        return GuideReply(
            reply=(
                f"{snapshot.project_name or 'This project'} currently passes every recorded check "
                f"({snapshot.totals()['passed']}/{snapshot.totals()['total']}). "
                "Re-run the health check after any hosting or processor change."
            ),
            suggested_prompts=prompts,
        )

    match = _best_check(question, failed + missing, active_file)
    if match is None:
        lines = [
            f"{snapshot.project_name or 'This project'} has {len(failed)} failed check(s)"
            + (f" and {len(missing)} waiting on information" if missing else "")
            + ".",
            "Start with the highest-impact failures, then ask the policy owner if a control is unclear.",
        ]
        for policy, item in (failed + missing)[:4]:
            lines.append(f"- {policy.domain}: {item.description} ({item.status}).")
        if failed:
            policy, item = failed[0]
            contact = _contact_line(policy, item)
            if contact:
                lines.append(f"Primary contact: {contact}.")
        return GuideReply(reply="\n".join(lines), suggested_prompts=prompts)

    policy, item = match
    rem = item.remediation
    parts = [
        f"**{item.description}** ({item.status}) under {policy.title}.",
        item.why or item.detail,
    ]
    if rem.actions:
        parts.append("What you can do:\n" + "\n".join(f"- {row}" for row in rem.actions[:4]))
    if rem.steps:
        parts.append("Next steps:\n" + "\n".join(f"{index}. {row}" for index, row in enumerate(rem.steps[:4], start=1)))
    contact = _contact_line(policy, item)
    if contact:
        parts.append(f"Who to contact: {contact}.")
    if active_file:
        parts.append(f"You are looking at `{active_file}`. Evidence for this check may be highlighted in that file.")
    return GuideReply(reply="\n".join(parts), suggested_prompts=prompts)


def _system_prompt() -> str:
    return """You are a compliance guide for a project owner (not a policy lawyer).
You help them understand closed-schema health-check results and what to do next.
Rules:
- Use only the provided health snapshot, contacts, and file excerpt. Do not invent legal citations.
- Prefer concrete next steps, then who to contact (policy owner/members).
- If the user asks why something failed, quote the check's why/detail and current vs accepted answers.
- If information is missing, tell them what fact to collect.
- Keep replies under 180 words. Use short markdown lists.
- Return JSON: {"reply": "...", "suggested_prompts": ["...", "..."]}
"""


def _user_prompt(
    snapshot: HealthSnapshot,
    messages: list[ChatMessage],
    active_file: str,
    file_excerpt: str,
    focus_policy_id: str,
) -> str:
    context = {
        "project": snapshot.project_name,
        "validated_at": snapshot.validated_at,
        "overall_status": snapshot.computed_status(),
        "totals": snapshot.totals(),
        "active_file": active_file,
        "focus_policy_id": focus_policy_id,
        "policies": [
            {
                "policy_id": policy.policy_id,
                "title": policy.title,
                "domain": policy.domain,
                "organization": policy.organization,
                "counts": policy.counts(),
                "owners": [item.model_dump() for item in policy.owners[:3]],
                "results": [
                    {
                        "statement_id": item.statement_id,
                        "description": item.description,
                        "status": item.status,
                        "why": item.why,
                        "answers": item.answers,
                        "accepted": item.accepted,
                        "actions": item.remediation.actions[:4],
                        "steps": item.remediation.steps[:4],
                        "contacts": [row.model_dump() for row in item.remediation.contacts[:3]],
                    }
                    for item in policy.results
                    if item.status != "pass"
                ],
            }
            for policy in snapshot.policies
        ],
    }
    history = [{"role": item.role, "content": item.content} for item in messages[-8:]]
    excerpt = (file_excerpt or "")[:2500]
    return (
        "Health snapshot:\n"
        f"{json.dumps(context, indent=2)}\n\n"
        f"File excerpt:\n{excerpt or '(none)'}\n\n"
        f"Conversation:\n{json.dumps(history, indent=2)}\n"
    )


def _failed_checks(snapshot: HealthSnapshot) -> list[tuple[PolicyHealth, HealthStatement]]:
    return [
        (policy, item)
        for policy in snapshot.policies
        for item in policy.results
        if item.status == "fail"
    ]


def _missing_checks(snapshot: HealthSnapshot) -> list[tuple[PolicyHealth, HealthStatement]]:
    return [
        (policy, item)
        for policy in snapshot.policies
        for item in policy.results
        if item.status == "missinginfo"
    ]


def _best_check(
    question: str,
    checks: list[tuple[PolicyHealth, HealthStatement]],
    active_file: str,
) -> tuple[PolicyHealth, HealthStatement] | None:
    if not checks:
        return None
    blob = f"{question} {active_file}".lower()
    tokens = set(re.findall(r"[a-z0-9_]{3,}", blob))
    best = None
    best_score = 0
    for policy, item in checks:
        hay = " ".join(
            [
                item.statement_id,
                item.description,
                item.why,
                policy.domain,
                policy.title,
                " ".join(item.mismatched_keys),
                " ".join(item.missing_keys),
            ]
        ).lower()
        score = sum(1 for token in tokens if token in hay)
        if score > best_score:
            best = (policy, item)
            best_score = score
    if best_score == 0:
        return checks[0]
    return best


def _contact_line(policy: PolicyHealth, item: HealthStatement) -> str:
    contacts = item.remediation.contacts or policy.owners
    if not contacts:
        return ""
    person = next((row for row in contacts if row.role == "owner"), contacts[0])
    bits = [person.name]
    if person.title:
        bits.append(person.title)
    if person.email:
        bits.append(person.email)
    org = person.organization or policy.organization
    if org:
        bits.append(org)
    return " · ".join(bits)


def _default_prompts(snapshot: HealthSnapshot) -> list[str]:
    failed = _failed_checks(snapshot)
    missing = _missing_checks(snapshot)
    prompts = ["What should I do first?", "Who do I contact about the failed checks?"]
    if failed:
        prompts.insert(0, f"Why did “{failed[0][1].description}” fail?")
    if missing:
        prompts.append("What information is still missing?")
    return prompts[:4]
