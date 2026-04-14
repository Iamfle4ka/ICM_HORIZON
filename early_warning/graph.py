"""
EWS LangGraph Pipeline — early_warning/graph.py
Early Warning System pro ICM GenAI Platform.

Graf:
  START → portfolio_loader → metrics_calculator → anomaly_detector
        → alert_generator → alert_dispatcher → END
"""
import logging
import uuid
from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from early_warning.nodes.alert_dispatcher import dispatch_alerts
from early_warning.nodes.alert_generator import generate_alerts
from early_warning.nodes.anomaly_detector import detect_anomalies
from early_warning.nodes.metrics_calculator import calculate_portfolio_metrics
from early_warning.nodes.portfolio_loader import load_portfolio_state
from early_warning.state import EWState

log = logging.getLogger(__name__)


def build_ews_graph() -> StateGraph:
    """Sestaví a zkompiluje EWS StateGraph."""
    builder = StateGraph(dict)

    builder.add_node("portfolio_loader",   load_portfolio_state)
    builder.add_node("metrics_calculator", calculate_portfolio_metrics)
    builder.add_node("anomaly_detector",   detect_anomalies)
    builder.add_node("alert_generator",    generate_alerts)
    builder.add_node("alert_dispatcher",   dispatch_alerts)

    builder.add_edge(START,                "portfolio_loader")
    builder.add_edge("portfolio_loader",   "metrics_calculator")
    builder.add_edge("metrics_calculator", "anomaly_detector")
    builder.add_edge("anomaly_detector",   "alert_generator")
    builder.add_edge("alert_generator",    "alert_dispatcher")
    builder.add_edge("alert_dispatcher",   END)

    return builder.compile()


_compiled_ews_graph = None


def get_ews_graph():
    """Vrátí zkompilovaný EWS graph (singleton)."""
    global _compiled_ews_graph
    if _compiled_ews_graph is None:
        _compiled_ews_graph = build_ews_graph()
    return _compiled_ews_graph


def run_early_warning(run_type: str = "daily_batch") -> dict:
    """
    Spustí kompletní EWS pipeline.

    Args:
        run_type: "daily_batch" | "on_demand"

    Returns:
        Finální EWState se summary, alerts a audit_trail.
    """
    initial_state = {
        "run_id":           str(uuid.uuid4()),
        "run_type":         run_type,
        "triggered_at":     datetime.now(timezone.utc).isoformat(),
        "portfolio":        [],
        "metrics_computed": {},
        "alerts":           [],
        "summary":          {},
        "status":           "running",
        "audit_trail":      [],
    }

    log.info(f"[EWSGraph] Spouštím EWS | run_type={run_type} run_id={initial_state['run_id']}")
    graph = get_ews_graph()
    result = graph.invoke(initial_state)
    log.info(
        f"[EWSGraph] EWS dokončen | "
        f"RED={result['summary'].get('red_alerts', 0)} "
        f"AMBER={result['summary'].get('amber_alerts', 0)}"
    )
    return result


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    result = run_early_warning("on_demand")
    s = result["summary"]
    print(f"\nEWS OK")
    print(f"  Run ID:  {result['run_id']}")
    print(f"  Klientů: {s['total_clients']}")
    print(f"  🔴 RED:  {s['red_alerts']}")
    print(f"  🟡 AMBER:{s['amber_alerts']}")
    print(f"  🟢 GREEN:{s['green_clients']}")
    print(f"  Alertů:  {len(result['alerts'])}")
    if result["alerts"]:
        print("\nTop alertů:")
        for a in result["alerts"][:3]:
            print(f"  [{a['alert_level']}] {a['company_name']} — {a['alert_type']}: {a['description'][:60]}")
    print("\nOK — early_warning/graph.py smoke test passed")
