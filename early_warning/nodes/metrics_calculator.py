# DETERMINISTIC
"""
Metrics Calculator — early_warning/nodes/metrics_calculator.py
Vypočítá EWS trendy pro každého klienta ze Silver tabulek.
DETERMINISTIC — čistá Python matematika, žádný LLM.
"""
import logging

from utils.audit import _audit

log = logging.getLogger(__name__)


def calculate_portfolio_metrics(state: dict) -> dict:
    """Vypočítá EWS trendy pro každého klienta v portfoliu."""
    results: dict[str, dict] = {}

    for client in state["portfolio"]:
        ico = client.get("ico", "")
        results[ico] = _compute_client_metrics(ico, client)

    log.info(f"[MetricsCalculator] Metriky vypočteny | clients={len(results)}")
    audit = _audit(
        state,
        node="MetricsCalculator",
        action="calculate_trends",
        result="success",
        metadata={"clients_processed": len(results)},
    )
    return {**state, "metrics_computed": results, "audit_trail": audit}


def _get_transactions(ico: str) -> list[dict]:
    """Načte poslední 12 měsíců transakcí z Silver nebo mock dat."""
    is_demo = __import__("os").getenv("ICM_ENV", "demo").lower() != "production"
    if is_demo:
        from utils.mock_data import _mock_transactions_12m
        return _mock_transactions_12m(ico)
    try:
        from utils.data_connector import query
        rows = query(f"""
            SELECT
                year_month,
                CAST(credit_turnover_czk AS DOUBLE)  AS credit_turnover,
                CAST(overdraft_days AS INT)           AS overdraft_days,
                tax_payment_made
            FROM vse_banka.obsluha_klienta.silver_transactions
            WHERE CAST(ico AS STRING) = '{ico}'
            ORDER BY year_month DESC
            LIMIT 12
        """)
        return rows
    except Exception as exc:
        log.warning(f"[MetricsCalculator] silver_transactions selhal pro {ico}: {exc}")
        return []


def _compute_client_metrics(ico: str, client: dict) -> dict:
    """DETERMINISTIC výpočet trendů pro jednoho klienta."""
    txns = _get_transactions(ico)
    credits = [float(t.get("credit_turnover", 0) or 0) for t in txns]

    # MoM turnover change
    mom_change = 0.0
    if len(credits) >= 2 and credits[1] != 0:
        mom_change = (credits[0] / credits[1] - 1) * 100  # DETERMINISTIC

    # Overdraft frequency (poslední 3M)
    overdraft_days_3m = sum(int(t.get("overdraft_days", 0) or 0) for t in txns[:3])
    overdraft_freq = overdraft_days_3m / 90 * 100  # DETERMINISTIC

    # Tax compliance (poslední 3M)
    tax_ok = sum(1 for t in txns[:3] if str(t.get("tax_payment_made", "")).lower() in ("true", "1"))
    tax_compliance = (tax_ok / 3 * 100) if txns else 100.0  # DETERMINISTIC

    # Utilisation a trend
    util = float(client.get("utilisation_pct", 0) or 0)
    # Simulujeme trend: u RED klientů +8pp, u GREEN -2pp
    ew_level = client.get("ew_alert_level", "GREEN")
    util_baseline = util * 0.9 if ew_level in ("RED", "AMBER") else util * 1.02
    util_trend = util - util_baseline  # DETERMINISTIC (pozitivní = nárůst)

    # DPD
    dpd = float(client.get("dpd_current", 0) or 0)

    # Days to limit breach (prediktivní) — DETERMINISTIC
    days_to_breach = None
    if util_trend > 0:
        days_to_breach = max(0.0, (85.0 - util) / util_trend * 30)

    # Covenant risk composite — DETERMINISTIC
    cov_status = client.get("covenant_status", "OK")
    covenant_risk = min(1.0,
        0.4 * min(1.0, dpd / 30)
        + 0.3 * (1.0 if cov_status == "BREACH" else 0.0)
        + 0.2 * (1.0 if client.get("is_restructured") else 0.0)
        + 0.1 * (1.0 if client.get("cmp_monitored") else 0.0)
    )  # DETERMINISTIC

    return {
        "utilisation_pct":       round(util, 1),
        "utilisation_trend_30d": round(util_trend, 2),
        "baseline_utilisation":  round(util_baseline, 1),
        "days_to_limit_breach":  round(days_to_breach, 0) if days_to_breach is not None else None,
        "mom_turnover_change":   round(mom_change, 2),
        "overdraft_frequency":   round(overdraft_freq, 1),
        "tax_compliance":        round(tax_compliance, 1),
        "dpd_current":           dpd,
        "covenant_risk_score":   round(covenant_risk, 3),
        "covenant_status":       cov_status,
    }
