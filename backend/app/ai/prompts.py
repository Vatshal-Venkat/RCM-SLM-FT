"""Prompt templates. Kept short and explicit: a 1.7B model follows terse instructions best."""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.llm_provider import ChatMessage

SYSTEM_BASE = (
    "You are an expert Revenue Cycle Management (RCM) assistant for US healthcare billing teams. "
    "Answer accurately, concisely and professionally. Use standard US RCM terminology. "
    "Never invent definitions, codes, figures or policies. Never include patient names or other "
    "personal identifiers."
)

GROUNDING_RULES = (
    "Use ONLY the reference material below to state definitions and facts. "
    "If the references define a term, use that definition exactly. "
    "Cite references inline as [1], [2]. "
    "If the references do not contain the answer, say so briefly instead of guessing."
)

DATA_RULES = (
    "The DATA section contains figures computed by the analytics engine. "
    "Quote these numbers exactly. Do not calculate, estimate or invent any other numbers."
)

FORMAT_KNOWLEDGE = (
    "Start directly with **Answer:** (do not repeat the question). "
    "Format your answer in Markdown with these sections, each 1-3 sentences:\n"
    "**Answer:** ...\n**Why it matters:** ...\n**Example:** ...\n**Recommended action:** ...\n"
    "Do not add a Sources section; sources are attached automatically."
)

FORMAT_ANALYTICS = (
    "Start directly with **Answer:** (do not repeat the question). Format in Markdown:\n"
    "**Answer:** 1-2 sentences restating KEY FINDING 1 with its exact figures.\n"
    "**Key drivers:** 2-4 bullet points based on the KEY FINDINGS, quoting their figures.\n"
    "**Recommended actions:** 2-3 bullet points that address those specific drivers.\n"
    "Do not add a Sources section."
)

FORMAT_CLAIM = (
    "Format your answer in Markdown with these sections, each 1-3 sentences:\n"
    "**Claim summary:** ...\n**Current status:** ...\n**Potential issue:** ...\n"
    "**Explanation:** why this happened, using the reference material.\n**Recommended next action:** ...\n"
    "Use only facts from DATA. Do not add a Sources section."
)

REGENERATION_NOTE = (
    "IMPORTANT: A previous draft was rejected because it contradicted the reference material: {reason}. "
    "Use the reference definitions verbatim."
)


@dataclass
class ContextBlock:
    """One numbered reference given to the model."""

    ref: int
    title: str
    text: str


def build_messages(
    question: str,
    history: list[ChatMessage] | None = None,
    references: list[ContextBlock] | None = None,
    data_context: str | None = None,
    format_instructions: str | None = FORMAT_KNOWLEDGE,
    correction: str | None = None,
) -> list[ChatMessage]:
    system = [SYSTEM_BASE]
    if references:
        system.append(GROUNDING_RULES)
    if data_context:
        system.append(DATA_RULES)
    if format_instructions:
        system.append(format_instructions)
    if correction:
        system.append(REGENERATION_NOTE.format(reason=correction))

    user_parts: list[str] = []
    if references:
        refs = "\n\n".join(f"[{c.ref}] {c.title}\n{c.text.strip()}" for c in references)
        user_parts.append(f"REFERENCE MATERIAL:\n{refs}")
    if data_context:
        user_parts.append(f"DATA:\n{data_context.strip()}")
    user_parts.append(f"QUESTION: {question.strip()}")

    return [
        ChatMessage("system", "\n\n".join(system)),
        *(history or []),
        ChatMessage("user", "\n\n".join(user_parts)),
    ]


GREETING_REPLY = (
    "Hello! I'm your RCM assistant. Ask me about claims, denials, ERAs/EOBs, payment posting, "
    "prior authorization, or revenue cycle KPIs."
)

OUT_OF_SCOPE_REPLY = (
    "I'm specialised in healthcare Revenue Cycle Management, so I can't help with that. "
    "Try asking about claims, denials, remittances, payment posting, or RCM KPIs."
)
