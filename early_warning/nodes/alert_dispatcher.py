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
        CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
        SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
        run_id    = state.get("run_id", "")
        alerts    = state.get("alerts", [])
        run_at    = state.get("run_at", "")
        try:
            from utils.data_connector import query
            for alert in alerts:
                ico       = str(alert.get("ico", "")).replace("'", "''")
                level     = str(alert.get("alert_level", "GREEN")).replace("'", "''")
                reason    = str(alert.get("reason", "")).replace("'", "''")[:1000]
                action    = str(alert.get("recommended_action", "")).replace("'", "''")[:2000]
                query(f"""
                    INSERT INTO {CAT}.{SCH}.ews_alerts
                    (run_id, ico, alert_level, reason, recommended_action, created_at)
                    VALUES (
                        '{run_id}',
                        '{ico}',
                        '{level}',
                        '{reason}',
                        '{action}',
                        '{run_at}'
                    )
                """)
            log.info(
                f"[AlertDispatcher] Prod INSERT ews_alerts | "
                f"run_id={run_id} alerts={len(alerts)} "
                f"target={CAT}.{SCH}.ews_alerts"
            )
        except Exception as exc:
            log.error(f"[AlertDispatcher] Prod INSERT selhal | {exc}")

        # Notifikace Risk Management přes Databricks Workflow
        workflow_id = os.getenv("DATABRICKS_EWS_WORKFLOW_ID", "")
        databricks_host  = os.getenv("DATABRICKS_HOST", "")
        databricks_token = os.getenv("DATABRICKS_TOKEN", "")
        if workflow_id and databricks_host and databricks_token:
            try:
                import urllib.request, json as _json
                payload = _json.dumps({
                    "job_id": int(workflow_id),
                    "notebook_params": {
                        "run_id":      run_id,
                        "red_alerts":  str(summary.get("red_alerts", 0)),
                        "amber_alerts": str(summary.get("amber_alerts", 0)),
                    },
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"https://{databricks_host}/api/2.1/jobs/run-now",
                    data=payload,
                    headers={
                        "Content-Type":  "application/json",
                        "Authorization": f"Bearer {databricks_token}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp_data = _json.loads(resp.read().decode("utf-8"))
                    log.info(
                        f"[AlertDispatcher] Databricks Workflow triggered | "
                        f"run_id={run_id} job_run_id={resp_data.get('run_id')}"
                    )
            except Exception as exc:
                log.error(f"[AlertDispatcher] Databricks Workflow trigger selhal | {exc}")

    audit = _audit(
        state,
        node="AlertDispatcher",
        action="dispatch",
        result="success",
        metadata={**summary, "mode": "demo" if is_demo else "production"},
    )
    return {**state, "status": "completed", "audit_trail": audit}
