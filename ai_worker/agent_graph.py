"""LangGraph state graph for processing one lead end-to-end.

START → qualify → decide → email → END
                          ↘ END  (not qualified or error)

Each node is a pure function over LeadProcessingState. LMs are injected by the
entry point (activity / process_one_lead) so importing this module makes no
API calls.
"""

from collections.abc import Mapping
from typing import Any

import dspy
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError
from typing_extensions import TypedDict

from ai_worker.dspy_engine import generate_email, qualify_lead
from shared.schemas import GeneratedEmail, Lead, PlaceDetails, QualifierVerdict

# END is Any (langgraph has no stubs); alias to str so _route stays typed.
_END: str = END


class LeadProcessingState(TypedDict):
    outreach_goal: str
    sender_context: str
    place: PlaceDetails
    verdict: QualifierVerdict | None
    email: GeneratedEmail | None
    error: str | None


def build_lead_state(
    outreach_goal: str,
    place: PlaceDetails,
    *,
    sender_context: str = "",
    verdict: QualifierVerdict | None = None,
    email: GeneratedEmail | None = None,
    error: str | None = None,
) -> LeadProcessingState:
    """Construct the per-lead graph state used by both orchestrators."""
    return {
        "outreach_goal": outreach_goal,
        "sender_context": sender_context,
        "place": place,
        "verdict": verdict,
        "email": email,
        "error": error,
    }


def _lm_from_config(config: RunnableConfig, key: str) -> dspy.BaseLM:
    configurable = config.get("configurable")
    if not isinstance(configurable, Mapping):
        raise RuntimeError(f"graph config missing configurable.{key}")
    lm = configurable.get(key)
    if not isinstance(lm, dspy.BaseLM):
        raise RuntimeError(f"graph config missing {key}")
    return lm


# ---------------------------------------------------------------------------
# Nodes (public — called directly by Temporal activities)
# ---------------------------------------------------------------------------


def qualify_node(state: LeadProcessingState, *, lm: dspy.BaseLM) -> dict[str, Any]:
    """Qualify the lead; catches LLM/network errors, lets ValidationError propagate."""
    try:
        verdict = qualify_lead(
            state["outreach_goal"],
            state["place"],
            lm=lm,
        )
        return {"verdict": verdict}
    except ValidationError:
        raise  # non-retryable; Temporal marks it via QUALIFY_RETRY.non_retryable_error_types
    except Exception as exc:
        return {"error": str(exc)}


def _decide_node(state: LeadProcessingState) -> dict[str, Any]:
    """No-op node — exists for graph clarity; routing is via conditional edge."""
    return {}


def email_node(state: LeadProcessingState, *, lm: dspy.BaseLM) -> dict[str, Any]:
    """Generate a personalised email; catches LLM errors, lets ValidationError propagate."""
    verdict = state["verdict"]
    assert verdict is not None  # invariant guaranteed by _route
    try:
        email = generate_email(
            state["outreach_goal"],
            state["place"],
            qualifier_reasoning=verdict.reasoning,
            sender_context=state["sender_context"],
            lm=lm,
        )
        return {"email": email}
    except ValidationError:
        raise  # non-retryable
    except Exception as exc:
        return {"error": str(exc)}


def _qualify_graph_node(state: LeadProcessingState, config: RunnableConfig) -> dict[str, Any]:
    return qualify_node(state, lm=_lm_from_config(config, "qualifier_lm"))


def _email_graph_node(state: LeadProcessingState, config: RunnableConfig) -> dict[str, Any]:
    return email_node(state, lm=_lm_from_config(config, "email_lm"))


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def should_generate_email(state: LeadProcessingState) -> bool:
    """True if the lead is qualified and no error occurred — mirrors workflow routing."""
    return state["error"] is None and state["verdict"] is not None and state["verdict"].is_qualified


def _route(state: LeadProcessingState) -> str:
    """Return next node name: 'email' if qualified, END otherwise."""
    return "email" if should_generate_email(state) else _END


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def _build_graph() -> Any:
    g: StateGraph[LeadProcessingState] = StateGraph(LeadProcessingState)
    g.add_node("qualify", _qualify_graph_node)
    g.add_node("decide", _decide_node)
    g.add_node("email", _email_graph_node)
    g.add_edge(START, "qualify")
    g.add_edge("qualify", "decide")
    g.add_conditional_edges("decide", _route)
    g.add_edge("email", END)
    return g.compile()


process_lead_graph: Any = _build_graph()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def process_one_lead(
    state: LeadProcessingState,
    *,
    qualifier_lm: dspy.BaseLM,
    email_lm: dspy.BaseLM,
) -> Lead:
    """Run the full qualify → (email | skip) pipeline for one lead.

    Returns a Lead with verdict + email populated if qualified, or error set
    if the qualify step failed.
    """
    result: LeadProcessingState = process_lead_graph.invoke(
        state,
        {"configurable": {"qualifier_lm": qualifier_lm, "email_lm": email_lm}},
    )
    return Lead(
        place=result["place"],
        verdict=result["verdict"],
        email=result["email"],
        error=result["error"],
    )
