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
                cm.ico,
                cm.company_name,
                cm.nace_description AS sector,
                fp.credit_limit_utilization * 100 AS utilisation_pct,
                fp.days_past_due_max AS dpd_current,
                fp.internal_rating_score,
                fp.avg_monthly_turnover,
                fp.cash_flow_volatility,
                fp.salary_payment_stability
            FROM {CAT}.{SCH}.silver_corporate_financial_profile fp
            JOIN {CAT}.{SCH}.silver_company_master cm
              ON cm.ico = CAST(fp.customer_id AS STRING)
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
