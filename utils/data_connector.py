# DETERMINISTIC
"""
Data Connector — utils/data_connector.py
Přístupová vrstva k Databricks Silver tabulkám.

IS_DEMO=True  → vrací mock data (bez Databricks)
IS_DEMO=False → volá Databricks SQL connector

DETERMINISTIC — žádný LLM.
"""

import logging
import os

log = logging.getLogger(__name__)

# ── Konfigurace ────────────────────────────────────────────────────────────────

_ENV: str = os.getenv("ICM_ENV", "demo").lower()
IS_DEMO: bool = _ENV != "production"

SILVER: str = os.getenv("DATABRICKS_SCHEMA_SILVER", "icm_silver")

if not IS_DEMO:
    try:
        from databricks import sql as _dbsql  # type: ignore

        _DB_HOST  = os.environ["DATABRICKS_HOST"]
        _DB_TOKEN = os.environ["DATABRICKS_TOKEN"]
        _DB_PATH  = os.environ["DATABRICKS_HTTP_PATH"]

        def query(sql_text: str) -> list[dict]:
            """Spustí SQL query na Databricks a vrátí řádky jako list[dict]."""
            with _dbsql.connect(
                server_hostname=_DB_HOST,
                http_path=_DB_PATH,
                access_token=_DB_TOKEN,
            ) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql_text)
                    cols = [d[0] for d in cursor.description]
                    return [dict(zip(cols, row)) for row in cursor.fetchall()]

    except ImportError:
        log.error("[DataConnector] databricks-sql-connector není nainstalován!")
        raise
    except KeyError as e:
        log.error(f"[DataConnector] Chybí env proměnná: {e}")
        raise
else:
    def query(sql_text: str) -> list[dict]:  # noqa: F811
        """Stub — v demo mode se nevolá."""
        raise RuntimeError("query() nesmí být voláno v demo mode")


# ── Public API ─────────────────────────────────────────────────────────────────


def get_company_master(ico: str) -> dict | None:
    """silver_company_master — základní info firmy."""
    if IS_DEMO:
        from utils.mock_data import get_client
        client = get_client(ico)
        if client is None:
            return None
        return {
            "ico":               client["ico"],
            "company_name":      client["company_name"],
            "legal_form":        "a.s." if "a.s." in client["company_name"] else "s.r.o.",
            "nace_code":         "F41" if "Stavební" in client["company_name"] else "G47",
            "nace_description":  client["sector"],
            "city":              "Praha",
            "founding_year":     2005,
            "employee_category": "100-499",
            "archetype":         client.get("ew_alert_level", "GREEN"),
        }
    rows = query(f"""
        SELECT ico, company_name, legal_form, nace_code,
               nace_description, city, founding_year,
               employee_category, archetype
        FROM {SILVER}.silver_company_master
        WHERE ico = '{ico}'
        LIMIT 1
    """)
    return rows[0] if rows else None


def get_customer_id(ico: str) -> int | None:
    """silver_corporate_customer — bridge pro customer_id."""
    if IS_DEMO:
        return int(ico[:6])  # mock customer_id
    rows = query(f"""
        SELECT customer_id
        FROM {SILVER}.silver_corporate_customer
        WHERE CAST(ico AS STRING) = '{ico}'
        LIMIT 1
    """)
    return rows[0]["customer_id"] if rows else None


def get_financial_profile(customer_id: int) -> dict | None:
    """silver_corporate_financial_profile — SCD Type 2, is_current."""
    if IS_DEMO:
        from utils.mock_data import get_portfolio
        for client in get_portfolio():
            if int(client["ico"][:6]) == customer_id:
                fd = client.get("financial_data", {})
                util = (
                    client.get("current_utilisation", 0)
                    / max(client.get("credit_limit", 1), 1)
                )
                is_green = client.get("ew_alert_level") == "GREEN"
                return {
                    "avg_monthly_turnover":     round(fd.get("revenue", 0) / 12, 0),
                    "cash_flow_volatility":     0.12 if is_green else 0.38,
                    "intl_payment_ratio":       0.12,
                    "top_payer_concentration":  0.25,
                    "credit_limit_utilization": round(util, 4),
                    "days_past_due_max":        client.get("dpd_current", 0),
                    "salary_payment_stability": 0.97 if is_green else 0.84,
                    "supplier_payment_terms":   30,
                    "internal_rating_score":    7.2 if is_green else 4.5,
                    "product_penetration_count": 4,
                    "valid_from":               "2025-01-01",
                    "calculated_at":            "2025-12-31",
                    "is_current":               True,
                }
        return None
    rows = query(f"""
        SELECT avg_monthly_turnover, cash_flow_volatility,
               intl_payment_ratio, top_payer_concentration,
               credit_limit_utilization, days_past_due_max,
               salary_payment_stability, supplier_payment_terms,
               internal_rating_score, product_penetration_count,
               valid_from, calculated_at
        FROM {SILVER}.silver_corporate_financial_profile
        WHERE customer_id = {customer_id}
          AND is_current = TRUE
        LIMIT 1
    """)
    return rows[0] if rows else None


def get_credit_history(ico: str) -> list[dict]:
    """silver_credit_history — kreditní historie, kovenanty, DPD."""
    if IS_DEMO:
        from utils.mock_data import get_client
        client = get_client(ico) or {}
        limit = client.get("credit_limit", 0)
        util  = client.get("current_utilisation", 0)
        dpd   = client.get("dpd_current", 0)
        cov   = client.get("covenant_status", "OK")
        breach = cov == "BREACH"
        return [{
            "loan_type":               "revolving",
            "approved_limit_czk":      str(int(limit)),
            "outstanding_balance_czk": str(int(util)),
            "utilisation_pct":         str(round(util / max(limit, 1) * 100, 1)),
            "dpd_current":             str(dpd),
            "dpd_max_historical":      str(dpd),
            "restructured":            "false",
            "restructure_date":        None,
            "relationship_years":      "3",
            "covenant_breach":         "true" if breach else "false",
            "covenant_breach_type":    "Leverage" if breach else "",
            "covenant_breach_count":   "1" if breach else "0",
            "covenant_breach_date":    "2025-06-01" if breach else None,
            "covenant_resolution_date": None,
            "covenant_waived":         "false",
            "covenant_status":         cov,
            "cmp_flag":                "false",
        }]
    return query(f"""
        SELECT loan_type, approved_limit_czk, outstanding_balance_czk,
               utilisation_pct, dpd_current, dpd_max_historical,
               restructured, restructure_date, relationship_years,
               covenant_breach, covenant_breach_type,
               covenant_breach_count, covenant_breach_date,
               covenant_resolution_date, covenant_waived,
               covenant_status, cmp_flag
        FROM {SILVER}.silver_credit_history
        WHERE ico = '{ico}'
    """)


def get_transactions_12m(ico: str) -> list[dict]:
    """silver_transactions — posledních 12 měsíců."""
    if IS_DEMO:
        from utils.mock_data import _mock_transactions_12m
        return _mock_transactions_12m(ico)
    return query(f"""
        SELECT year_month,
               CAST(credit_turnover_czk AS DOUBLE) AS credit_turnover,
               CAST(debit_turnover_czk  AS DOUBLE) AS debit_turnover,
               CAST(min_balance_czk     AS DOUBLE) AS min_balance,
               CAST(avg_balance_czk     AS DOUBLE) AS avg_balance,
               CAST(overdraft_days      AS INT)    AS overdraft_days,
               CAST(overdraft_max_depth_czk AS DOUBLE) AS overdraft_depth,
               tax_payment_made,
               CAST(tax_payment_delay_days AS INT) AS tax_delay_days,
               CAST(payroll_amount_czk     AS DOUBLE) AS payroll_amount,
               CAST(payroll_employees_count AS INT)   AS payroll_employees,
               CAST(deposit_balance_czk    AS DOUBLE) AS deposit_balance,
               CAST(savings_balance_czk    AS DOUBLE) AS savings_balance
        FROM {SILVER}.silver_transactions
        WHERE ico = '{ico}'
          AND year_month >= DATE_FORMAT(ADD_MONTHS(CURRENT_DATE, -12), 'yyyy-MM')
        ORDER BY year_month DESC
    """)


def get_incidents_24m(ico: str) -> list[dict]:
    """silver_client_incidents — posledních 24 měsíců."""
    if IS_DEMO:
        return []  # prázdný seznam = žádné incidenty v demo
    return query(f"""
        SELECT incident_date, incident_type, channel,
               resolution_status,
               CAST(resolution_days AS INT) AS resolution_days,
               escalated
        FROM {SILVER}.silver_client_incidents
        WHERE ico = '{ico}'
          AND incident_date >= ADD_MONTHS(CURRENT_DATE, -24)
        ORDER BY incident_date DESC
    """)


def get_cribis_data(ico: str) -> dict | None:
    """
    CRIBIS data z Týmu 8 — silver_data_cribis_v3.
    Vrátí nejaktuálnější období (MAX obdobi_do).
    POZOR: sloupec je 'ic', ne 'ico' — CAST nutný.
    """
    if IS_DEMO:
        from utils.mock_data import _mock_cribis
        return _mock_cribis(ico)

    CAT = os.getenv("DATABRICKS_CATALOG_CRIBIS", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_CRIBIS", "investment_banking")

    rows = query(f"""
        SELECT
            CAST(ic AS STRING) AS ic,
            nazev_subjektu,
            hlavni_nace_kod,
            obdobi_od,
            obdobi_do,
            CAST(cisty_obrat_za_ucetni_obdobi_i_ii_iii_iv_v_vi_vii AS DOUBLE) AS revenue,
            CAST(ebit    AS DOUBLE) AS ebit,
            CAST(ebitda  AS DOUBLE) AS ebitda,
            CAST(vysledek_hospodareni_za_ucetni_obdobi AS DOUBLE) AS net_income,
            CAST(roa_rentabilita_aktiv_v_cisty_zisk_aktiva AS DOUBLE) AS roa,
            CAST(roe_rentabilita_vlastniho_kapitalu_v_cisty_zisk_vlastni_kapital AS DOUBLE) AS roe,
            CAST(ros_vynosnost_trzeb_v_ebit_trzby AS DOUBLE) AS ros,
            CAST(celkova_zadluzenost_v_cizi_zdroje_pasiva_celkem AS DOUBLE) AS total_leverage_pct,
            CAST(likvidita_bezna AS DOUBLE) AS current_ratio,
            CAST(cizi_zdroje AS DOUBLE) AS total_debt,
            CAST(vlastni_kapital AS DOUBLE) AS equity,
            CAST(zavazky_k_uverovym_institucim AS DOUBLE) AS bank_liabilities_st,
            CAST(zavazky_k_uverovym_institucim_1 AS DOUBLE) AS bank_liabilities_lt,
            CAST(penezni_prostredky AS DOUBLE) AS cash,
            CAST(nakladove_uroky_a_podobne_naklady AS DOUBLE) AS interest_expense,
            CAST(aktiva_celkem AS DOUBLE) AS total_assets,
            CAST(obezna_aktiva AS DOUBLE) AS current_assets,
            CAST(zmena_obrat_pct  AS DOUBLE) AS yoy_revenue_change_pct,
            CAST(zmena_ebitda_pct AS DOUBLE) AS yoy_ebitda_change_pct,
            CAST(cisty_pracovni_kapital_v_tis_kc AS DOUBLE) AS net_working_capital_k,
            CAST(odpisy           AS DOUBLE) AS depreciation,
            CAST(stala_aktiva     AS DOUBLE) AS fixed_assets,
            CAST(zasoby           AS DOUBLE) AS inventories,
            CAST(dan_z_prijmu_1   AS DOUBLE) AS income_tax,
            is_suspicious,
            missing_key_kpi
        FROM {CAT}.{SCH}.silver_data_cribis_v3
        WHERE CAST(ic AS STRING) = '{ico}'
        ORDER BY obdobi_do DESC
        LIMIT 1
    """)
    if not rows:
        return None

    row = rows[0]
    # Výpočet net_debt a leverage_ratio
    bank_st = float(row.get("bank_liabilities_st") or 0)
    bank_lt = float(row.get("bank_liabilities_lt") or 0)
    cash    = float(row.get("cash") or 0)
    ebitda  = float(row.get("ebitda") or 0)
    int_exp = float(row.get("interest_expense") or 0)

    net_debt = (bank_st + bank_lt) - cash if (bank_st + bank_lt) > 0 else None
    leverage_ratio = None
    if net_debt is not None and ebitda and ebitda > 0:
        leverage_ratio = round(net_debt / ebitda, 3)

    dscr = None
    if ebitda and int_exp and int_exp > 0:
        debt_service = int_exp + (bank_st / 12 if bank_st else 0)
        if debt_service > 0:
            dscr = round(ebitda / debt_service, 3)

    return {
        **row,
        "net_debt":       round(net_debt, 0) if net_debt is not None else None,
        "leverage_ratio": leverage_ratio,
        "dscr":           dscr,
        "dscr_note":      "Proxy: EBITDA/debt_service (ne přesný Op.CF/DS)" if dscr else None,
    }


def get_cribis_prev_period(ico: str) -> dict | None:
    """
    CRIBIS data za předchozí účetní období (pro výpočet CAPEX).
    Vrátí druhý nejnovější záznam (ORDER BY obdobi_do DESC LIMIT 1 OFFSET 1).
    """
    if IS_DEMO:
        from utils.mock_data import _mock_cribis_prev
        return _mock_cribis_prev(ico)

    CAT = os.getenv("DATABRICKS_CATALOG_CRIBIS", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_CRIBIS", "investment_banking")

    rows = query(f"""
        SELECT
            CAST(ic AS STRING) AS ic,
            obdobi_od,
            obdobi_do,
            CAST(stala_aktiva AS DOUBLE) AS stala_aktiva,
            CAST(odpisy       AS DOUBLE) AS odpisy,
            CAST(ebitda       AS DOUBLE) AS ebitda,
            CAST(cisty_obrat_za_ucetni_obdobi_i_ii_iii_iv_v_vi_vii AS DOUBLE) AS revenue
        FROM {CAT}.{SCH}.silver_data_cribis_v3
        WHERE CAST(ic AS STRING) = '{ico}'
        ORDER BY obdobi_do DESC
        LIMIT 1 OFFSET 1
    """)
    if not rows:
        return None
    return rows[0]


def get_flood_risk(city: str) -> dict:
    """
    Flood risk pro město ze silver_building_flood_join.
    Vrátí {'flood_risk': 'HIGH'|'MEDIUM'|'LOW'|'MINIMAL', 'buildings_checked': int}.
    """
    if IS_DEMO:
        # Mock flood risk podle názvu města
        city_lower = city.lower()
        if "liberec" in city_lower or "ostrava" in city_lower:
            return {"flood_risk": "HIGH", "buildings_checked": 3}
        if "brno" in city_lower or "plzeň" in city_lower:
            return {"flood_risk": "MEDIUM", "buildings_checked": 5}
        return {"flood_risk": "LOW", "buildings_checked": 2}

    ESG_CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    ESG_SCH = os.getenv("DATABRICKS_SCHEMA_ESG", "icm_gen_ai")

    rows = query(f"""
        SELECT
            COUNT(*) AS buildings_checked,
            MAX(CASE WHEN bfj.in_flood_zone = TRUE THEN
                CASE bfj.q_level
                    WHEN 'Q5'   THEN 3
                    WHEN 'Q20'  THEN 2
                    WHEN 'Q100' THEN 1
                    ELSE 0
                END ELSE 0 END) AS max_flood_score,
            MIN(bfj.distance_to_zone_m) AS min_distance_m
        FROM {ESG_CAT}.{ESG_SCH}.silver_ruian_buildings b
        LEFT JOIN {ESG_CAT}.{ESG_SCH}.silver_building_flood_join bfj
            ON b.building_code = bfj.building_code
        WHERE LOWER(b.city) = LOWER('{city}')
    """)

    if not rows or not rows[0].get("buildings_checked"):
        return {"flood_risk": "UNKNOWN", "buildings_checked": 0}

    row = rows[0]
    score = int(row.get("max_flood_score") or 0)
    return {
        "flood_risk":           {3: "HIGH", 2: "MEDIUM", 1: "LOW"}.get(score, "MINIMAL"),
        "buildings_checked":    int(row.get("buildings_checked") or 0),
        "min_distance_m":       row.get("min_distance_m"),
    }


if __name__ == "__main__":
    # Smoke test — demo mode
    assert IS_DEMO, "Smoke test pouze v demo mode"

    company = get_company_master("27082440")
    assert company is not None
    assert company["company_name"] == "Stavební holding Praha a.s."
    print(f"  company: {company['company_name']}")

    cid = get_customer_id("27082440")
    assert cid is not None
    print(f"  customer_id: {cid}")

    fp = get_financial_profile(cid)
    assert fp is not None
    assert fp["is_current"] is True
    print(f"  fin_profile avg_monthly_turnover: {fp['avg_monthly_turnover']:,.0f}")

    credit = get_credit_history("27082440")
    assert len(credit) >= 1
    print(f"  credit rows: {len(credit)}, utilisation_pct: {credit[0]['utilisation_pct']}")

    txns = get_transactions_12m("27082440")
    assert len(txns) == 12
    print(f"  transactions: {len(txns)} měsíců, první: {txns[0]['year_month']}")

    inc = get_incidents_24m("27082440")
    print(f"  incidents: {len(inc)}")

    # Neznámé IČO
    assert get_company_master("99999999") is None
    print("  unknown ICO → None: OK")

    print("OK — data_connector.py smoke test passed")
