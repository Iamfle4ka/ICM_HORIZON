# DETERMINISTIC
"""
Alert Dispatcher — early_warning/nodes/alert_dispatcher.py
Demo: loguje výsledky. Prod: Delta table + notifikace Risk Mgmt.
DETERMINISTIC — žádný LLM.
"""
import logging
import os

from utils.audit import _audit

log = logging.getLogger(__name__)


def dispatch_alerts(state: dict) -> dict:
    """Demo: loguje. Prod: Delta table + notifikace."""
    summary = state.get("summary", {})
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"

    log.info(
        f"[AlertDispatcher] EWS run {state.get('run_id', '')} dokončen | "
        f"RED={summary.get('red_alerts', 0)} "
        f"AMBER={summary.get('amber_alerts', 0)} "
        f"GREEN={summary.get('green_clients', 0)} "
        f"mode={'demo' if is_demo else 'prod'}"
    )

    if not is_demo:
        # TODO: INSERT INTO vse_banka.obsluha_klienta.ews_alerts
        # TODO: Notifikace Risk Mgmt přes Databricks Workflow
        pass

    audit = _audit(
        state,
        node="AlertDispatcher",
        action="dispatch",
        result="success",
        metadata={**summary, "mode": "demo" if is_demo else "production"},
    )
    return {**state, "status": "completed", "audit_trail": audit}
