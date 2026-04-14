# DETERMINISTIC
"""
ESG Collector — esg_pipeline/collector.py
Sbírá raw ESG data pro Tým 5. NESOUVISÍ s Credit Memo (DP1).
DETERMINISTIC — žádný LLM.
"""
import logging
import os

log = logging.getLogger(__name__)


def collect_esg_data(icos: list[str] | None = None) -> list[dict]:
    """
    Načte ESG raw data.
    Demo: vrátí mock hodnoty z mock_data.
    Prod: Databricks query pro ESG zdroje.

    Args:
        icos: Seznam IČO k načtení (None = všechny ACTIVE klienty)

    Returns:
        list[dict] s raw ESG daty
    """
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"

    if is_demo:
        from utils.mock_data import get_portfolio
        from utils.data_connector import get_flood_risk
        portfolio = get_portfolio()
        records = []
        for c in portfolio:
            if icos is not None and c["ico"] not in icos:
                continue
            city = "Praha"  # mock city default
            flood = get_flood_risk(city)
            records.append({
                "ico":            c["ico"],
                "company_name":   c["company_name"],
                "city":           city,
                "esg_score_raw":  c.get("esg_score", 50),
                "flood_risk_raw": flood.get("flood_risk", "LOW"),
                "flood_buildings_checked": flood.get("buildings_checked", 0),
                "source":         "mock",
            })
        log.info(f"[ESGCollector] Demo mode | {len(records)} záznamů")
        return records

    # Prod: Databricks flood zones query
    from utils.data_connector import query, get_company_master, get_flood_risk
    ESG_CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    ESG_SCH = os.getenv("DATABRICKS_SCHEMA_ESG", "icm_gen_ai")

    results = []
    for ico in (icos or []):
        company = get_company_master(ico) or {}
        city = company.get("city", "")
        if not city:
            results.append({
                "ico":   ico,
                "company_name": company.get("company_name", ""),
                "city":  "",
                "esg_score_raw": 50,
                "flood_risk_raw": "UNKNOWN",
                "flood_buildings_checked": 0,
                "source": "databricks",
            })
            continue
        flood = get_flood_risk(city)
        results.append({
            "ico":                      ico,
            "company_name":             company.get("company_name", ""),
            "city":                     city,
            "esg_score_raw":            50,  # TODO: CRIBIS ESG skóre
            "flood_risk_raw":           flood.get("flood_risk", "UNKNOWN"),
            "flood_buildings_checked":  flood.get("buildings_checked", 0),
            "flood_min_distance_m":     flood.get("min_distance_m"),
            "source":                   "databricks_flood_zones",
        })
    log.info(f"[ESGCollector] Prod mode | {len(results)} záznamů")
    return results
