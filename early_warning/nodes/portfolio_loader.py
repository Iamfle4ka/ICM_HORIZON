# DETERMINISTIC
"""
Portfolio Loader — early_warning/nodes/portfolio_loader.py
Načte ACTIVE klienty ze Silver tabulek nebo mock dat.
DETERMINISTIC — žádný LLM.
"""
import logging
import os

from utils.audit import _audit

log = logging.getLogger(__name__)


def load_portfolio_state(state: dict) -> dict:
    """Načte ACTIVE klienty z Portfolio State Store."""
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"

    if is_demo:
        from utils.mock_data import get_portfolio
        portfolio = get_portfolio()
    else:
        from utils.data_connector import query
        CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
        SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
        rows = query(f"""
            SELECT
                CAST(cc.ico AS STRING)                             AS ico,
                CAST(fp.credit_limit_utilization * 100 AS DOUBLE) AS utilisation_pct,
                CAST(fp.days_past_due_max AS INT)                  AS dpd_current,
                CAST(fp.internal_rating_score AS DOUBLE)           AS internal_rating_score,
                CAST(fp.avg_monthly_turnover AS DOUBLE)            AS avg_monthly_turnover,
                CAST(fp.cash_flow_volatility AS DOUBLE)            AS cash_flow_volatility,
                CAST(fp.salary_payment_stability AS DOUBLE)        AS salary_payment_stability
            FROM {CAT}.{SCH}.silver_corporate_financial_profile fp
            JOIN {CAT}.{SCH}.silver_corporate_customer cc
              ON cc.customer_id = fp.customer_id
            WHERE fp.is_current = TRUE
        """)
        portfolio = rows

    # Obohaťme portfolio o CRIBIS YoY signály pro EWS
    try:
        from utils.data_connector import get_cribis_data
        for client in portfolio:
            cribis = get_cribis_data(client.get("ico", ""))
            if cribis:
                client["yoy_revenue_change_pct"] = cribis.get("yoy_revenue_change_pct")
                client["yoy_ebitda_change_pct"]  = cribis.get("yoy_ebitda_change_pct")
                client["is_suspicious_cribis"]   = bool(cribis.get("is_suspicious", False))
                client["leverage_ratio"]         = cribis.get("leverage_ratio")
                client["dscr"]                   = cribis.get("dscr")
    except Exception as exc:
        log.warning(f"[PortfolioLoader] CRIBIS obohacení selhalo: {exc}")

    audit = _audit(
        state,
        node="PortfolioLoader",
        action="load_portfolio",
        result="success",
        metadata={
            "clients_loaded": len(portfolio),
            "mode": "demo" if is_demo else "production",
        },
    )
    log.info(f"[PortfolioLoader] Načteno {len(portfolio)} klientů | mode={'demo' if is_demo else 'prod'}")
    return {**state, "portfolio": portfolio, "audit_trail": audit}
