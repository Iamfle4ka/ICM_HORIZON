"""
EWS Pipeline — early_warning/graph.py
Early Warning System pro ICM GenAI Platform.

Pipeline (lineární, bez LangGraph — žádný conditional routing není potřeba):
  load_portfolio_state → calculate_portfolio_metrics → detect_anomalies
  → generate_alerts → dispatch_alerts
"""
import logging
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from early_warning.nodes.alert_dispatcher import dispatch_alerts
from early_warning.nodes.alert_generator import generate_alerts
from early_warning.nodes.anomaly_detector import detect_anomalies
from early_warning.nodes.metrics_calculator import calculate_portfolio_metrics
from early_warning.nodes.portfolio_loader import load_portfolio_state

log = logging.getLogger(__name__)


def run_early_warning(run_type: str = "daily_batch") -> dict:
    """
    Spustí kompletní EWS pipeline.

    Args:
        run_type: "daily_batch" | "on_demand"

    Returns:
        Finální state se summary, alerts a audit_trail.
    """
    state = {
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

    log.info(f"[EWSGraph] Spouštím EWS | run_type={run_type} run_id={state['run_id']}")

    state = load_portfolio_state(state)
    state = calculate_portfolio_metrics(state)
    state = detect_anomalies(state)
    state = generate_alerts(state)
    state = dispatch_alerts(state)

    log.info(
        f"[EWSGraph] EWS dokončen | "
        f"RED={state['summary'].get('red_alerts', 0)} "
        f"AMBER={state['summary'].get('amber_alerts', 0)}"
    )
    return state


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
