"""DSPy-based lead qualification and email generation engine.

LM is injected per-call via dspy.context(lm=...) to avoid the race condition
that dspy.configure(lm=...) would cause under parallel Temporal activities
(CLAUDE.md §11 anti-pattern #1).
"""

import dspy

from shared.schemas import GeneratedEmail, PlaceDetails, QualifierVerdict


class QualifyLead(dspy.Signature):  # type: ignore[misc]
    """Determine if a business is a qualified lead for a given outreach goal."""

    outreach_goal: str = dspy.InputField(
        desc="What kind of leads the user wants, "
        "e.g. 'B2B SaaS companies selling to dental practices'"
    )
    business: str = dspy.InputField(desc="JSON-serialized PlaceDetails")

    is_qualified: bool = dspy.OutputField(
        desc="True only if the business clearly matches the outreach goal"
    )
    score: float = dspy.OutputField(desc="Confidence 0.0-1.0")
    reasoning: str = dspy.OutputField(desc="One sentence explaining the verdict")
    icp_fit: dict[str, bool] = dspy.OutputField(
        desc="Dict mapping ICP criteria names to bool, "
        "e.g. {'is_b2b': True, 'has_website': True, 'size_match': False}"
    )


class GenerateEmail(dspy.Signature):  # type: ignore[misc]
    """Draft a personalized cold outreach email for a qualified lead."""

    outreach_goal: str = dspy.InputField(
        desc="What kind of leads the user wants, used to frame the email angle"
    )
    business: str = dspy.InputField(desc="JSON-serialized PlaceDetails")
    qualifier_reasoning: str = dspy.InputField(
        desc="Why this lead was qualified — use to ground personalization"
    )
    sender_context: str = dspy.InputField(
        desc="Who the sender is and their value proposition, derived from user prompt"
    )

    subject: str = dspy.OutputField(desc="≤80 chars, specific, not spammy")
    body: str = dspy.OutputField(
        desc="≤200 words, plain text, no marketing fluff, references the business specifically"
    )
    personalization_hooks: list[str] = dspy.OutputField(
        desc="The 2-3 specific business details you keyed off, e.g. ['4.8-star rating', 'Warsaw location']"
    )


# Module-level predictors — stateless; LM is resolved from context at call time.
_qualify_predictor = dspy.Predict(QualifyLead)
_email_predictor = dspy.Predict(GenerateEmail)


def qualify_lead(
    outreach_goal: str,
    place: PlaceDetails,
    *,
    lm: dspy.BaseLM,
) -> QualifierVerdict:
    """Qualify a lead against an outreach goal using DSPy.

    ``lm`` is applied via dspy.context per-call so parallel Temporal activities
    running this function concurrently never share a global LM setting.
    """
    with dspy.context(lm=lm):
        prediction = _qualify_predictor(
            outreach_goal=outreach_goal,
            business=place.model_dump_json(),
        )
    return QualifierVerdict(
        is_qualified=prediction.is_qualified,
        score=float(prediction.score),
        reasoning=str(prediction.reasoning),
        icp_fit=dict(prediction.icp_fit),
    )


def generate_email(
    outreach_goal: str,
    place: PlaceDetails,
    qualifier_reasoning: str,
    sender_context: str,
    *,
    lm: dspy.BaseLM,
) -> GeneratedEmail:
    """Generate a personalized cold outreach email for a qualified lead.

    ``lm`` is applied via dspy.context per-call so parallel Temporal activities
    running this function concurrently never share a global LM setting.
    """
    with dspy.context(lm=lm):
        prediction = _email_predictor(
            outreach_goal=outreach_goal,
            business=place.model_dump_json(),
            qualifier_reasoning=qualifier_reasoning,
            sender_context=sender_context,
        )
    return GeneratedEmail(
        subject=str(prediction.subject),
        body=str(prediction.body),
        personalization_hooks=list(prediction.personalization_hooks),
        model_used=str(lm.model),
    )
