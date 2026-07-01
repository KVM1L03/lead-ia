"""LangGraph state graph for processing one lead end-to-end.

START → qualify → decide → email → END
                          ↘ END  (not qualified or error)

Each node is a pure function over LeadProcessingState. LMs are resolved lazily
via get_lm() at invocation time so importing this module makes no API calls.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from ai_worker.dspy_engine import generate_email, qualify_lead
from ai_worker.llm_router import get_lm
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


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def _qualify_node(state: LeadProcessingState) -> dict[str, Any]:
    """Qualify the lead; on any exception set error and leave verdict=None."""
    try:
        verdict = qualify_lead(
            state["outreach_goal"],
            state["place"],
            lm=get_lm("qualifier"),
        )
        return {"verdict": verdict}
    except Exception as exc:
        return {"error": str(exc)}


def _decide_node(state: LeadProcessingState) -> dict[str, Any]:
    """No-op node — exists for graph clarity; routing is via conditional edge."""
    return {}


def _email_node(state: LeadProcessingState) -> dict[str, Any]:
    """Generate a personalised email for a qualified lead."""
    verdict = state["verdict"]
    assert verdict is not None  # invariant guaranteed by _route
    email = generate_email(
        state["outreach_goal"],
        state["place"],
        qualifier_reasoning=verdict.reasoning,
        sender_context=state["sender_context"],
        lm=get_lm("email"),
    )
    return {"email": email}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _route(state: LeadProcessingState) -> str:
    """Return next node name: 'email' if qualified, END otherwise."""
    if state["error"] is not None:
        return _END
    verdict = state["verdict"]
    if verdict is None or not verdict.is_qualified:
        return _END
    return "email"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def _build_graph() -> Any:
    g: StateGraph[LeadProcessingState] = StateGraph(LeadProcessingState)
    g.add_node("qualify", _qualify_node)
    g.add_node("decide", _decide_node)
    g.add_node("email", _email_node)
    g.add_edge(START, "qualify")
    g.add_edge("qualify", "decide")
    g.add_conditional_edges("decide", _route)
    g.add_edge("email", END)
    return g.compile()


process_lead_graph: Any = _build_graph()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def process_one_lead(state: LeadProcessingState) -> Lead:
    """Run the full qualify → (email | skip) pipeline for one lead.

    Returns a Lead with verdict + email populated if qualified, or error set
    if the qualify step failed.
    """
    result: LeadProcessingState = process_lead_graph.invoke(state)
    return Lead(
        place=result["place"],
        verdict=result["verdict"],
        email=result["email"],
        error=result["error"],
    )
