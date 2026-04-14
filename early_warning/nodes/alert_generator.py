# DETERMINISTIC
"""
Alert Generator — early_warning/nodes/alert_generator.py
Generuje souhrnný EWS report ze alertů.
DETERMINISTIC — žádný LLM.
"""
import logging
from datetime import datetime, timezone

from utils.audit import _audit

log = logging.getLogger(__name__)


def generate_alerts(state: dict) -> dict:
    """Sestaví summary EWS reportu ze všech alertů."""
    alerts = state.get("alerts", [])
    portfolio = state.get("portfolio", [])

    red   = [a for a in alerts if a["alert_level"] == "RED"]
    amber = [a for a in alerts if a["alert_level"] == "AMBER"]
    alerted_icos = {a["ico"] for a in alerts}
    green_count = max(0, len(portfolio) - len(alerted_icos))

    summary = {
        "run_id":        state.get("run_id", ""),
        "run_type":      state.get("run_type", "on_demand"),
        "total_clients": len(portfolio),
        "red_alerts":    len(red),
        "amber_alerts":  len(amber),
        "green_clients": green_count,
        "top_risks":     red[:5],
        "generated_at":  datetime.now(timezone.utc).isoformat(),
    }

    log.info(
        f"[AlertGenerator] Summary | RED={len(red)} AMBER={len(amber)} GREEN={green_count}"
    )
    audit = _audit(
        state,
        node="AlertGenerator",
        action="generate_summary",
        result="success",
        metadata={"red": len(red), "amber": len(amber), "green": green_count},
    )
    return {**state, "summary": summary, "audit_trail": audit}
