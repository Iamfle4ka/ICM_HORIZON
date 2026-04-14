# DETERMINISTIC + AI text pro recommended_action
"""
Anomaly Detector — early_warning/nodes/anomaly_detector.py
Aplikuje EW pravidla (DETERMINISTIC). AI přidá jen text recommended_action.
"""
import logging
import os
from datetime import datetime, timezone

from utils.audit import _audit
from utils.wcr_rules import EW_THRESHOLDS

log = logging.getLogger(__name__)


def detect_anomalies(state: dict) -> dict:
    """Aplikuje EW pravidla. AI přidá jen text recommended_action."""
    alerts: list[dict] = []

    for client in state["portfolio"]:
        ico = client.get("ico", "")
        metrics = state["metrics_computed"].get(ico, {})
        client_alerts = _apply_rules(client, metrics)
        # AI text pouze pro RED a AMBER, pouze pokud API key dostupný
        if client_alerts and os.getenv("ANTHROPIC_API_KEY"):
            client_alerts = _add_ai_recommendations(client, metrics, client_alerts)
        alerts.extend(client_alerts)

    # Seřadit RED → AMBER → GREEN, pak abecedně
    level_order = {"RED": 0, "AMBER": 1, "GREEN": 2}
    alerts.sort(key=lambda a: (level_order.get(a["alert_level"], 3), a.get("company_name", "")))

    audit = _audit(
        state,
        node="AnomalyDetector",
        action="detect_anomalies",
        result="success",
        metadata={
            "total_alerts": len(alerts),
            "red":   sum(1 for a in alerts if a["alert_level"] == "RED"),
            "amber": sum(1 for a in alerts if a["alert_level"] == "AMBER"),
        },
    )
    log.info(
        f"[AnomalyDetector] Detekce hotova | total={len(alerts)} "
        f"red={sum(1 for a in alerts if a['alert_level']=='RED')} "
        f"amber={sum(1 for a in alerts if a['alert_level']=='AMBER')}"
    )
    return {**state, "alerts": alerts, "audit_trail": audit}


def _apply_rules(client: dict, metrics: dict) -> list[dict]:
    """DETERMINISTIC — aplikuje EW_THRESHOLDS pravidla."""
    now = datetime.now(timezone.utc).isoformat()
    alerts = []

    def make_alert(atype: str, level: str, curr: float, thresh: float, base: float, desc: str) -> dict:
        dev = ((curr - base) / base * 100) if base else 0.0
        return {
            "ico":                client.get("ico", ""),
            "company_name":       client.get("company_name", ""),
            "alert_type":         atype,
            "alert_level":        level,
            "current_value":      round(curr, 2),
            "threshold":          thresh,
            "baseline":           round(base, 2),
            "deviation_pct":      round(dev, 1),
            "description":        desc,
            "recommended_action": "",
            "detected_at":        now,
        }

    util  = metrics.get("utilisation_pct", 0.0)
    dpd   = metrics.get("dpd_current", 0.0)
    mom   = metrics.get("mom_turnover_change", 0.0)
    odft  = metrics.get("overdraft_frequency", 0.0)
    tax   = metrics.get("tax_compliance", 100.0)
    dtb   = metrics.get("days_to_limit_breach")
    cvnt  = metrics.get("covenant_status", client.get("covenant_status", "OK"))
    cr    = metrics.get("covenant_risk_score", 0.0)
    base_u = metrics.get("baseline_utilisation", util * 0.9)

    # Utilisation
    if util >= EW_THRESHOLDS["utilisation_red_pct"]:
        alerts.append(make_alert("utilisation_spike", "RED", util, 85.0, base_u,
            f"Čerpání limitu {util:.1f} % překračuje WCR limit 85 %"))
    elif util >= EW_THRESHOLDS["utilisation_amber_pct"]:
        alerts.append(make_alert("utilisation_spike", "AMBER", util, 75.0, base_u,
            f"Čerpání limitu {util:.1f} % překračuje AMBER práh 75 %"))
    elif dtb is not None and dtb < EW_THRESHOLDS["days_to_breach_amber"]:
        alerts.append(make_alert("utilisation_spike", "AMBER", util, 85.0, base_u,
            f"Při aktuálním trendu dosáhne WCR limit za {dtb:.0f} dní"))

    # DPD
    if dpd >= EW_THRESHOLDS["dpd_red_days"]:
        alerts.append(make_alert("dpd_increase", "RED", dpd, 30.0, 0.0,
            f"DPD {dpd:.0f} dní překračuje WCR limit 30 dní"))
    elif dpd >= EW_THRESHOLDS["dpd_amber_days"]:
        alerts.append(make_alert("dpd_increase", "AMBER", dpd, 15.0, 0.0,
            f"DPD {dpd:.0f} dní — sledovat vývoj"))

    # Covenant
    if cvnt == "BREACH" or cr >= EW_THRESHOLDS["covenant_risk_red"]:
        alerts.append(make_alert("covenant_breach", "RED", cr, 0.7, 0.0,
            f"Aktivní porušení kovenantu | composite risk {cr:.2f}"))
    elif cvnt == "WARNING" or cr >= EW_THRESHOLDS["covenant_risk_amber"]:
        alerts.append(make_alert("covenant_breach", "AMBER", cr, 0.5, 0.0,
            "Varování kovenantu — sledovat plnění podmínek"))

    # Revenue drop
    if mom <= -EW_THRESHOLDS["revenue_drop_red_pct"]:
        alerts.append(make_alert("revenue_drop", "RED", mom, -20.0, 0.0,
            f"Pokles obratu {abs(mom):.1f} % MoM překračuje RED práh"))
    elif mom <= -EW_THRESHOLDS["revenue_drop_amber_pct"]:
        alerts.append(make_alert("revenue_drop", "AMBER", mom, -10.0, 0.0,
            f"Pokles obratu {abs(mom):.1f} % MoM — sledovat trend"))

    # Overdraft
    if odft >= EW_THRESHOLDS["overdraft_red_pct"]:
        alerts.append(make_alert("overdraft_risk", "RED", odft, 50.0, 0.0,
            f"Přečerpání {odft:.0f} % dní za poslední 3M"))
    elif odft >= EW_THRESHOLDS["overdraft_amber_pct"]:
        alerts.append(make_alert("overdraft_risk", "AMBER", odft, 20.0, 0.0,
            f"Přečerpání {odft:.0f} % dní — zvýšit monitoring"))

    # Tax compliance
    if tax < EW_THRESHOLDS["tax_compliance_amber"]:
        alerts.append(make_alert("tax_risk", "AMBER", tax, 80.0, 100.0,
            f"Daňová compliance {tax:.0f} % — riziko problémů s FÚ"))

    # CRIBIS YoY signály (pokud dostupné)
    yoy_rev    = float(client.get("yoy_revenue_change_pct") or 0)
    yoy_ebitda = float(client.get("yoy_ebitda_change_pct") or 0)
    suspicious = bool(client.get("is_suspicious_cribis", False))

    if yoy_rev != 0:
        if yoy_rev <= -EW_THRESHOLDS["revenue_drop_red_pct"]:
            alerts.append(make_alert("revenue_drop", "RED", yoy_rev, -20.0, 0.0,
                f"CRIBIS: YoY pokles obratu {yoy_rev:.1f} % — RED práh"))
        elif yoy_rev <= -EW_THRESHOLDS["revenue_drop_amber_pct"]:
            alerts.append(make_alert("revenue_drop", "AMBER", yoy_rev, -10.0, 0.0,
                f"CRIBIS: YoY pokles obratu {yoy_rev:.1f} % — AMBER práh"))

    if yoy_ebitda <= -25.0:
        alerts.append(make_alert("dscr_deterioration", "RED", yoy_ebitda, -25.0, 0.0,
            f"CRIBIS: YoY pokles EBITDA {yoy_ebitda:.1f} % — výrazné zhoršení"))

    if suspicious:
        alerts.append(make_alert("covenant_breach", "AMBER", 1.0, 0.0, 0.0,
            "CRIBIS: data označena jako podezřelá (is_suspicious=True) — ověřte manuálně"))

    return alerts


def _add_ai_recommendations(client: dict, metrics: dict, alerts: list[dict]) -> list[dict]:
    """AI přidá jen recommended_action text pro RED a AMBER."""
    try:
        import json

        import anthropic

        from skills import registry

        skill = registry.get("ew_analyzer_skill")
        api_client = anthropic.Anthropic()

        for alert in alerts:
            if alert["alert_level"] not in ("RED", "AMBER"):
                continue
            ctx = (
                f"Firma: {alert['company_name']} (IČO: {alert['ico']})\n"
                f"Alert: {alert['alert_type']} | Úroveň: {alert['alert_level']}\n"
                f"Popis: {alert['description']}\n"
                f"Hodnota: {alert['current_value']} | Práh: {alert['threshold']}"
            )
            response = api_client.messages.create(
                model="claude-opus-4-6",
                max_tokens=256,
                system=skill["prompt"],
                messages=[{"role": "user", "content": ctx}],
            )
            try:
                result = json.loads(response.content[0].text)
                alert["recommended_action"] = result.get("recommended_action", "")
            except Exception:
                alert["recommended_action"] = response.content[0].text[:200]

    except Exception as exc:
        log.warning(f"[AnomalyDetector] AI recommendations failed: {exc}")
    return alerts
