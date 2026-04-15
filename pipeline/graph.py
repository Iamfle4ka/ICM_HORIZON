"""
LangGraph Pipeline — pipeline/graph.py
Sestavuje a kompiluje StateGraph pro ICM GenAI Platform.

Graf:
  START
    → data_extractor_agent
    → extraction_validator
    ─[freeze]─→ END
    ─[continue_phase2]─→ context_builder
    → credit_analysis_service
    → memo_preparation_agent
    → quality_control_checker
    ─[freeze / escalate]─→ END
    ─[retry_maker]─→ memo_preparation_agent  (loop, max 3×)
    ─[policy_check]─→ policy_rules_engine
    → human_review_node
    → END  (čeká na record_human_decision ze Streamlit UI)

Demo mode: pipeline spuštěna s mock daty (bez real API volání).
"""

import logging

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import END, START, StateGraph

from pipeline.nodes.phase1_extraction import data_extractor_agent, extraction_validator
from pipeline.nodes.phase2_analysis import context_builder, credit_analysis_service
from pipeline.nodes.phase3_maker_checker import (
    memo_preparation_agent,
    policy_rules_engine,
    quality_control_checker,
)
from pipeline.nodes.phase4_human_audit import human_review_node
from pipeline.routing import (
    route_after_checker,
    route_after_extraction,
    route_after_policy,
)
from pipeline.state import AgentState, make_initial_state

log = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """
    Sestaví a zkompiluje LangGraph StateGraph.

    Returns:
        Zkompilovaný graph (CompiledGraph) připravený k invoke().
    """
    graph = StateGraph(dict)

    # ── Uzly ──────────────────────────────────────────────────────────────────
    graph.add_node("data_extractor_agent",   data_extractor_agent)
    graph.add_node("extraction_validator",   extraction_validator)
    graph.add_node("context_builder",        context_builder)
    graph.add_node("credit_analysis_service", credit_analysis_service)
    graph.add_node("memo_preparation_agent", memo_preparation_agent)
    graph.add_node("quality_control_checker", quality_control_checker)
    graph.add_node("policy_rules_engine",    policy_rules_engine)
    graph.add_node("human_review_node",      human_review_node)

    # ── Hrany — lineární průchod ───────────────────────────────────────────────
    graph.add_edge(START,                    "data_extractor_agent")
    graph.add_edge("data_extractor_agent",   "extraction_validator")

    # Podmíněná hrana po validaci extrakce
    graph.add_conditional_edges(
        "extraction_validator",
        route_after_extraction,
        {
            "freeze":          END,
            "continue_phase2": "context_builder",
        },
    )

    graph.add_edge("context_builder",        "credit_analysis_service")
    graph.add_edge("credit_analysis_service", "memo_preparation_agent")
    graph.add_edge("memo_preparation_agent", "quality_control_checker")

    # Podmíněná hrana po quality check (Maker-Checker loop)
    graph.add_conditional_edges(
        "quality_control_checker",
        route_after_checker,
        {
            "freeze":       END,
            "escalate":     END,
            "retry_maker":  "memo_preparation_agent",
            "policy_check": "policy_rules_engine",
        },
    )

    # Podmíněná hrana po WCR check → vždy human review
    graph.add_conditional_edges(
        "policy_rules_engine",
        route_after_policy,
        {
            "human_review": "human_review_node",
        },
    )

    graph.add_edge("human_review_node", END)

    return graph.compile()


# Singleton zkompilovaný graph (lazy initialization)
_compiled_graph = None


def get_graph():
    """Vrátí zkompilovaný graph (singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        log.info("[Graph] Kompiluji LangGraph pipeline")
        _compiled_graph = build_graph()
        log.info("[Graph] Pipeline zkompilována")
    return _compiled_graph


def run_pipeline(ico: str, request_id: str | None = None, raw_documents: dict | None = None) -> dict:
    """
    Spustí kompletní pipeline pro daný IČO.

    Args:
        ico:           IČO klienta (8 číslic)
        request_id:    Volitelné request ID (generuje se automaticky)
        raw_documents: dict[source_id → text] — skutečné dokumenty
                       Pokud None/prázdné → Demo mode (mock data)

    Returns:
        Finální AgentState po dokončení pipeline.
    """
    import uuid
    if request_id is None:
        request_id = f"REQ-{ico[:4]}-{uuid.uuid4().hex[:6].upper()}"

    initial_state = make_initial_state(ico, request_id)
    if raw_documents:
        initial_state["raw_documents"] = raw_documents

    log.info(f"[Graph] Spouštím pipeline | ico={ico} request_id={request_id}")

    graph = get_graph()
    final_state = graph.invoke(initial_state)

    log.info(
        f"[Graph] Pipeline dokončena | ico={ico} request_id={request_id} "
        f"status={final_state.get('status')} "
        f"audit_events={len(final_state.get('audit_trail', []))}"
    )
    return final_state


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    ico = sys.argv[1] if len(sys.argv) > 1 else "27082440"
    print(f"\nSpouštím pipeline pro IČO: {ico}")
    print("=" * 60)

    result = run_pipeline(ico)

    print(f"\nStatus:    {result.get('status')}")
    print(f"Company:   {result.get('case_view', {}).get('company_name', 'N/A')}")
    print(f"WCR:       {'PASS' if result.get('wcr_passed') else 'FAIL'}")
    print(f"Checker:   {result.get('checker_verdict', 'N/A')}")
    print(f"Coverage:  {result.get('citation_coverage', 0):.1%}")
    print(f"Iteration: {result.get('maker_iteration', 0)}")
    print(f"Audit events: {len(result.get('audit_trail', []))}")

    if result.get("draft_memo"):
        print(f"\nMemo preview (prvních 300 znaků):")
        print(result["draft_memo"][:300] + "...")

    print("\nOK — graph.py smoke test passed")
