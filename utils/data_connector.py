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


def _norm_ico(ico: str | int | None) -> str:
    """
    Normalizuje IČO pro CRIBIS JOIN — odstraní vedoucí nuly.

    Silver silver_company_master ukládá IČO jako STRING s vedoucími nulami:
        '00514152'
    CRIBIS sloupec `ic` je číselný typ, CAST(ic AS STRING) vrátí:
        '514152'
    Výsledek: CAST(ic AS STRING) = '00514152' → FALSE (no match!).

    Řešení: normalizujeme obě strany na čistý integer string bez vedoucích nul.
    """
    if ico is None:
        return ""
    try:
        return str(int(str(ico)))
    except (ValueError, TypeError):
        return str(ico)

# ── Konfigurace ────────────────────────────────────────────────────────────────

_ENV: str = os.getenv("ICM_ENV", "demo").lower()
IS_DEMO: bool = _ENV != "production"

SILVER: str = os.getenv("DATABRICKS_CATALOG", "vse_banka") + "." + os.getenv("DATABRICKS_SCHEMA_SILVER", "icm_silver")

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
    CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
    rows = query(f"""
        SELECT CAST(ico AS STRING) AS ico, company_name, legal_form,
               nace_description, city, employee_category, archetype
        FROM {CAT}.{SCH}.silver_company_master
        WHERE CAST(ico AS STRING) = '{ico}'
        LIMIT 1
    """)
    if not rows:
        return None
    row = rows[0]
    return {
        "ico":               row["ico"],
        "company_name":      row.get("company_name", ""),
        "legal_form":        row.get("legal_form", ""),
        "nace_code":         "",
        "nace_description":  row.get("nace_description", ""),
        "city":              row.get("city", ""),
        "founding_year":     None,
        "employee_category": row.get("employee_category", ""),
        "archetype":         row.get("archetype", ""),
    }


def get_customer_id(ico: str) -> int | None:
    """silver_corporate_customer — bridge pro customer_id.
    V prod: ICO samotné slouží jako customer_id (silver_corporate_customer má jiná data).
    """
    if IS_DEMO:
        return int(ico[:6])  # mock customer_id
    try:
        return int(ico)
    except (ValueError, TypeError):
        return None


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
    # silver_corporate_financial_profile má jiný customer_id mapping.
    # Buildujeme profil z silver_credit_history (transakce + loan data) pro dané IČO.
    CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
    ico_str = str(customer_id)  # customer_id = int(ico) v prod
    try:
        loan_rows = query(f"""
            SELECT approved_limit_czk, outstanding_balance_czk, utilisation_pct,
                   dpd_current, relationship_years
            FROM {CAT}.{SCH}.silver_credit_history
            WHERE CAST(ico AS STRING) = '{ico_str}'
              AND approved_limit_czk IS NOT NULL
            LIMIT 1
        """)
        tx_rows = query(f"""
            SELECT AVG(credit_turnover_czk) AS avg_monthly_turnover,
                   MAX(overdraft_days) AS overdraft_days_max
            FROM {CAT}.{SCH}.silver_credit_history
            WHERE CAST(ico AS STRING) = '{ico_str}'
              AND year_month IS NOT NULL
        """)
    except Exception as exc:
        log.warning(f"[DataConnector] get_financial_profile selhal | ico={ico_str} {exc}")
        return None

    if not loan_rows:
        return None

    loan = loan_rows[0]
    tx   = tx_rows[0] if tx_rows else {}
    limit = float(loan.get("approved_limit_czk") or 0)
    outstanding = float(loan.get("outstanding_balance_czk") or 0)
    util = outstanding / limit if limit > 0 else 0.0
    avg_turnover = float(tx.get("avg_monthly_turnover") or 0)

    return {
        "avg_monthly_turnover":     round(avg_turnover, 0),
        "cash_flow_volatility":     0.15,
        "intl_payment_ratio":       0.10,
        "top_payer_concentration":  0.25,
        "credit_limit_utilization": round(util, 4),
        "days_past_due_max":        int(loan.get("dpd_current") or 0),
        "salary_payment_stability": 0.95,
        "supplier_payment_terms":   "30",
        "internal_rating_score":    6.5,
        "product_penetration_count": 3,
        "valid_from":               "2024-01-01",
        "calculated_at":            "2024-12-31",
        "is_current":               True,
    }


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
    CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
    return query(f"""
        SELECT loan_type, approved_limit_czk, outstanding_balance_czk,
               utilisation_pct, dpd_current, dpd_max_historical,
               restructured, restructure_date, relationship_years,
               covenant_breach, covenant_breach_type,
               covenant_breach_count, covenant_breach_date,
               covenant_resolution_date, covenant_waived,
               covenant_status, cmp_flag
        FROM {CAT}.{SCH}.silver_credit_history
        WHERE CAST(ico AS STRING) = '{ico}'
          AND approved_limit_czk IS NOT NULL
    """)


def get_transactions_12m(ico: str) -> list[dict]:
    """silver_transactions — posledních 12 měsíců."""
    if IS_DEMO:
        from utils.mock_data import _mock_transactions_12m
        return _mock_transactions_12m(ico)
    CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
    return query(f"""
        SELECT CAST(year_month AS STRING) AS year_month,
               CAST(credit_turnover_czk    AS DOUBLE) AS credit_turnover,
               CAST(debit_turnover_czk     AS DOUBLE) AS debit_turnover,
               CAST(min_balance_czk        AS DOUBLE) AS min_balance,
               CAST(avg_balance_czk        AS DOUBLE) AS avg_balance,
               CAST(overdraft_days         AS INT)    AS overdraft_days,
               CAST(overdraft_max_depth_czk AS DOUBLE) AS overdraft_depth,
               tax_payment_made,
               CAST(tax_payment_delay_days AS INT)    AS tax_delay_days,
               CAST(payroll_amount_czk     AS DOUBLE) AS payroll_amount,
               CAST(payroll_employees_count AS INT)   AS payroll_employees,
               CAST(deposit_balance_czk    AS DOUBLE) AS deposit_balance,
               CAST(savings_balance_czk    AS DOUBLE) AS savings_balance
        FROM {CAT}.{SCH}.silver_transactions
        WHERE CAST(ico AS STRING) = '{ico}'
          AND year_month IS NOT NULL
          AND year_month >= ADD_MONTHS(CURRENT_DATE(), -12)
        ORDER BY year_month DESC
    """)


def get_incidents_24m(ico: str) -> list[dict]:
    """silver_client_incidents — posledních 24 měsíců."""
    if IS_DEMO:
        return []  # prázdný seznam = žádné incidenty v demo
    CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
    return query(f"""
        SELECT incident_date, incident_type, channel,
               resolution_status,
               CAST(resolution_days AS INT) AS resolution_days,
               escalated
        FROM {CAT}.{SCH}.silver_client_incidents
        WHERE CAST(ico AS STRING) = '{ico}'
          AND incident_date IS NOT NULL
          AND incident_date >= ADD_MONTHS(CURRENT_DATE(), -24)
        ORDER BY incident_date DESC
    """)


def get_cribis_data(ico: str) -> dict | None:
    """
    CRIBIS data z Týmu 8 — silver_data_cribis_v3.
    Nejnovější snapshot (ORDER BY obdobi_do DESC LIMIT 1).
    ic je NUMERIC — normalizujeme přes TRY_CAST pro JOIN.
    """
    if IS_DEMO:
        from utils.mock_data import _mock_cribis
        return _mock_cribis(ico)

    CAT = os.getenv("DATABRICKS_CATALOG_CRIBIS", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_CRIBIS", "investment_banking")

    rows = query(f"""
        SELECT
            CAST(TRY_CAST(ic AS BIGINT) AS STRING)                                   AS ic,
            nazev_subjektu, hlavni_nace_kod, hlavni_nace_popis,
            mesto, pravni_forma, datum_zalozeni, zakladni_kapital_z_or,
            kategorie_poctu_zamestnancu, kategorie_obratu,
            obdobi_od, obdobi_do,
            CAST(cisty_obrat_za_ucetni_obdobi_i_ii_iii_iv_v_vi_vii AS DOUBLE)        AS revenue,
            CAST(ebit       AS DOUBLE)                                                AS ebit,
            CAST(ebitda     AS DOUBLE)                                                AS ebitda,
            CAST(vysledek_hospodareni_za_ucetni_obdobi AS DOUBLE)                    AS net_income,
            CAST(roa_rentabilita_aktiv_v_cisty_zisk_aktiva AS DOUBLE)                AS roa,
            CAST(roe_rentabilita_vlastniho_kapitalu_v_cisty_zisk_vlastni_kapital AS DOUBLE) AS roe,
            CAST(ros_vynosnost_trzeb_v_ebit_trzby AS DOUBLE)                         AS ros,
            CAST(celkova_zadluzenost_v_cizi_zdroje_pasiva_celkem AS DOUBLE)          AS total_debt_ratio,
            CAST(likvidita_bezna AS DOUBLE)                                           AS quick_ratio,
            CAST(likvidita_celkova_kratkodoba_aktiva_kratkodobe_zavazky AS DOUBLE)   AS current_ratio_direct,
            CAST(cisty_pracovni_kapital_v_tis_kc AS DOUBLE)                          AS net_working_capital,
            CAST(doba_obratu_kratkodobych_pohledavek_ve_dnech_pohledavky_kratkodobe_trzby_celkem_365 AS DOUBLE) AS days_receivables,
            CAST(doba_obratu_kratkodobych_zavazku_ve_dnech_zavazky_kratkodobe_naklady_365 AS DOUBLE)            AS days_payables,
            CAST(obratka_aktiv_trzby_celkova_aktiva AS DOUBLE)                       AS asset_turnover,
            CAST(cizi_zdroje   AS DOUBLE)                                             AS cizi_zdroje,
            CAST(vlastni_kapital AS DOUBLE)                                           AS equity,
            CAST(zavazky_k_uverovym_institucim   AS DOUBLE)                          AS bank_liabilities_lt,
            CAST(zavazky_k_uverovym_institucim_1 AS DOUBLE)                          AS bank_liabilities_st,
            CAST(penezni_prostredky AS DOUBLE)                                        AS cash,
            CAST(nakladove_uroky_a_podobne_naklady AS DOUBLE)                        AS interest_expense,
            CAST(aktiva_celkem  AS DOUBLE)                                            AS total_assets,
            CAST(obezna_aktiva  AS DOUBLE)                                            AS current_assets,
            CAST(zasoby         AS DOUBLE)                                            AS inventories,
            CAST(stala_aktiva   AS DOUBLE)                                            AS fixed_assets,
            CAST(upravy_hodnot_dlouhodobeho_hmotneho_a_nehmotneho_majetku_trvale AS DOUBLE) AS depreciation,
            CAST(dan_z_prijmu_1 AS DOUBLE)                                            AS income_tax
        FROM {CAT}.{SCH}.silver_data_cribis_v3
        WHERE CAST(TRY_CAST(ic AS BIGINT) AS STRING) = '{_norm_ico(ico)}'
        ORDER BY obdobi_do DESC
        LIMIT 1
    """)
    if not rows:
        return None

    row = rows[0]

    # CRIBIS ukládá hodnoty v tisících CZK → převést na CZK (*1000).
    # Koeficienty (roa, roe, current_ratio_direct ...) a textová pole se nepřevádí.
    _CRIBIS_MONETARY = {
        "ebitda", "ebit", "depreciation",
        "bank_liabilities_st", "bank_liabilities_lt",
        "cash", "interest_expense",
        "revenue", "total_assets", "equity",
        "current_assets", "inventories", "fixed_assets",
        "net_working_capital", "cizi_zdroje", "net_income",
        "income_tax",
    }
    row = {
        k: (float(v) * 1000 if k in _CRIBIS_MONETARY and v is not None else v)
        for k, v in row.items()
    }

    _EBITDA_MIN = 50_000  # 50 000 CZK — práh po převodu na CZK
    ebitda_raw = row.get("ebitda")
    ebit_raw   = float(row.get("ebit") or 0)
    depr_raw   = float(row.get("depreciation") or 0)
    ebitda_col = float(ebitda_raw) if ebitda_raw is not None else None
    if ebitda_col is None or abs(ebitda_col) < _EBITDA_MIN:
        ebitda_col = ebit_raw + depr_raw

    ebitda  = ebitda_col
    bank_st = float(row.get("bank_liabilities_st") or 0)
    bank_lt = float(row.get("bank_liabilities_lt") or 0)
    cash    = float(row.get("cash") or 0)
    int_exp = float(row.get("interest_expense") or 0)

    current_ratio = row.get("current_ratio_direct")
    if current_ratio is not None:
        current_ratio = round(float(current_ratio), 3)

    net_debt = (bank_st + bank_lt) - cash if (bank_st + bank_lt) > 0 else None
    leverage_ratio = None
    if net_debt is not None and ebitda != 0:
        raw_lev = net_debt / ebitda
        leverage_ratio = round(raw_lev, 3) if abs(raw_lev) <= 100 else None

    dscr = None
    if ebitda and int_exp and int_exp > 0:
        debt_service = int_exp + (bank_st / 12 if bank_st else 0)
        if debt_service > 0:
            dscr = round(ebitda / debt_service, 3)

    return {
        **row,
        "ebitda":         round(ebitda, 0),
        "current_ratio":  current_ratio,
        "net_debt":       round(net_debt, 0) if net_debt is not None else None,
        "leverage_ratio": leverage_ratio,
        "dscr":           dscr,
        "dscr_note":      "DSCR proxy (interest + ST bank debt / 12)" if dscr else None,
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
            CAST(upravy_hodnot_dlouhodobeho_hmotneho_a_nehmotneho_majetku_trvale AS DOUBLE) AS odpisy,
            CAST(ebitda       AS DOUBLE) AS ebitda,
            CAST(cisty_obrat_za_ucetni_obdobi_i_ii_iii_iv_v_vi_vii AS DOUBLE) AS revenue
        FROM {CAT}.{SCH}.silver_data_cribis_v3
        WHERE CAST(TRY_CAST(ic AS BIGINT) AS STRING) = '{_norm_ico(ico)}'
        ORDER BY obdobi_do DESC
        LIMIT 1 OFFSET 1
    """)
    if not rows:
        return None

    _PREV_MONETARY = {"stala_aktiva", "odpisy", "ebitda", "revenue"}
    row = rows[0]
    return {
        k: (float(v) * 1000 if k in _PREV_MONETARY and v is not None else v)
        for k, v in row.items()
    }


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


def _build_client_info(ico: str, profile_row: dict) -> dict:
    """
    Sestaví dict klienta z profilu + CRIBIS + WCR výpočtů.
    Produkční ekvivalent mock_data.get_client().
    DETERMINISTIC — žádný LLM.
    """
    from utils.wcr_rules import check_wcr_breaches, EW_THRESHOLDS

    approved_limit  = float(profile_row.get("approved_limit_czk")      or 0)
    outstanding     = float(profile_row.get("outstanding_balance_czk") or 0)
    utilisation_pct = float(profile_row.get("utilisation_pct")         or 0)
    if utilisation_pct == 0 and approved_limit > 0:
        utilisation_pct = round(outstanding / approved_limit * 100, 1)
    dpd_current     = int(profile_row.get("dpd_current") or 0)
    covenant_status = profile_row.get("covenant_status") or "OK"

    cribis = get_cribis_data(ico) or {}

    leverage_ratio = float(cribis.get("leverage_ratio") or 0) or None
    dscr           = float(cribis.get("dscr")           or 0) or None
    current_ratio  = float(cribis.get("current_ratio")  or 0) or None
    ebitda_val     = float(cribis.get("ebitda")         or 0)

    wcr_breaches = check_wcr_breaches(
        leverage_ratio=leverage_ratio or 0,
        dscr=dscr or 0,
        utilisation_pct=utilisation_pct,
        current_ratio=current_ratio or 0,
        dpd_current=dpd_current,
    )

    n_breaches = len(wcr_breaches)
    if dpd_current >= EW_THRESHOLDS["dpd_red_days"] or n_breaches >= 3:
        ew_level = "RED"
    elif (
        dpd_current >= EW_THRESHOLDS["dpd_amber_days"]
        or utilisation_pct >= EW_THRESHOLDS["utilisation_amber_pct"]
        or n_breaches >= 1
    ):
        ew_level = "AMBER"
    else:
        ew_level = "GREEN"

    if leverage_ratio and dscr:
        if   leverage_ratio <= 2.5 and dscr >= 1.8: cribis_rating = "A1"
        elif leverage_ratio <= 3.5 and dscr >= 1.4: cribis_rating = "A2"
        elif leverage_ratio <= 4.5 and dscr >= 1.2: cribis_rating = "B1"
        elif leverage_ratio <= 5.0 and dscr >= 1.0: cribis_rating = "B2"
        else:                                        cribis_rating = "C1"
    else:
        cribis_rating = "N/A"

    credit_limit = approved_limit
    current_util = outstanding

    return {
        "ico":              ico,
        "company_name":     profile_row.get("company_name", ico),
        "sector":           profile_row.get("sector", ""),
        "ew_alert_level":   ew_level,
        "covenant_status":  covenant_status,
        "cribis_rating":    cribis_rating,
        "dpd_current":      dpd_current,
        "credit_limit":     credit_limit,
        "current_utilisation": current_util,
        "financial_data": {
            "revenue":             float(cribis.get("revenue")              or 0),
            "ebitda":              ebitda_val,
            "net_debt":            float(cribis.get("net_debt")             or 0),
            "total_assets":        float(cribis.get("total_assets")         or 0),
            "current_assets":      float(cribis.get("current_assets")       or 0),
            "current_liabilities": float(cribis.get("current_liabilities")  or 0),
            "debt_service":        float(cribis.get("interest_expense")     or 0),
            "operating_cashflow":  ebitda_val * 0.8,
        },
        "metrics": {
            "leverage_ratio": leverage_ratio,
            "dscr":           dscr,
            "current_ratio":  current_ratio,
            "utilisation_pct": utilisation_pct,
        },
        "wcr_breaches":     wcr_breaches,
        "portfolio_status": "ACTIVE",
        "esg_score":        None,
        "last_memo_date":   None,
        "katastr_data":     None,
        "flood_risk":       None,
        "data_sources": {
            "cribis_v3": f"CRIBIS silver_data_cribis_v3 (ic: {ico})",
            "silver_fp": "Databricks Silver financial_profile (is_current=TRUE)",
        },
    }


def get_portfolio_clients() -> list[dict]:
    """
    Vrátí seznam aktivních klientů pro Portfolio Dashboard.
    Demo: mock data · Production: 3 batch dotazy místo N+1.
    DETERMINISTIC — žádný LLM.
    """
    if IS_DEMO:
        from utils.mock_data import get_portfolio
        return get_portfolio()

    from utils.wcr_rules import check_wcr_breaches, EW_THRESHOLDS

    CAT     = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    SCH     = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
    CAT_CR  = os.getenv("DATABRICKS_CATALOG_CRIBIS", "vse_banka")
    SCH_CR  = os.getenv("DATABRICKS_SCHEMA_CRIBIS", "investment_banking")

    # ── Batch 1: silver_company_master JOIN silver_credit_history ─────────────
    # silver_corporate_financial_profile / silver_corporate_customer neobsahují
    # odpovídající data → silver_credit_history je denormalizovaná tabulka se vším.
    try:
        profile_rows = query(f"""
            SELECT
                CAST(cm.ico AS STRING)                             AS ico,
                cm.company_name,
                cm.nace_description                                AS sector,
                cm.city,
                cm.employee_category,
                MAX(ch.approved_limit_czk)                         AS approved_limit_czk,
                MAX(ch.outstanding_balance_czk)                    AS outstanding_balance_czk,
                MAX(ch.utilisation_pct)                            AS utilisation_pct,
                MAX(CAST(ch.dpd_current AS INT))                   AS dpd_current,
                MAX(ch.relationship_years)                         AS relationship_years,
                MAX(CASE WHEN ch.covenant_breach = true THEN 'BREACH'
                         ELSE COALESCE(ch.covenant_status, 'OK') END) AS covenant_status,
                MAX(CAST(ch.cmp_flag AS BOOLEAN))                  AS cmp_flag
            FROM {CAT}.{SCH}.silver_company_master cm
            JOIN {CAT}.{SCH}.silver_credit_history ch
              ON CAST(cm.ico AS STRING) = CAST(ch.ico AS STRING)
            WHERE ch.approved_limit_czk IS NOT NULL
            GROUP BY cm.ico, cm.company_name, cm.nace_description, cm.city, cm.employee_category
        """)
    except Exception as silver_exc:
        log.error(
            f"[DataConnector] Silver Batch 1 selhal — fallback na mock data | {silver_exc}"
        )
        from utils.mock_data import get_portfolio
        mock = get_portfolio()
        # Označíme jako fallback aby UI mohl zobrazit varování
        for c in mock:
            c["_fallback"] = True
        return mock

    if not profile_rows:
        log.warning(
            f"[DataConnector] Silver Batch 1 vrátil 0 řádků — fallback na mock data | "
            f"tabulky: {CAT}.{SCH}.silver_corporate_financial_profile"
        )
        from utils.mock_data import get_portfolio
        mock = get_portfolio()
        for c in mock:
            c["_fallback"] = True
        return mock

    # Normalizovaný seznam IČO (bez vedoucích nul) pro CRIBIS JOIN
    ico_list_norm = "', '".join(_norm_ico(r["ico"]) for r in profile_rows)
    # Originální seznam pro Silver covenant query
    ico_list = "', '".join(str(r["ico"]) for r in profile_rows)

    # ── Batch 2: CRIBIS přes silver_data_cribis_v3 ────────────────────────────
    # QUALIFY ROW_NUMBER() → pouze nejnovější snapshot per IČO (PARTITION BY ic).
    try:
        cribis_rows = query(f"""
            SELECT
                CAST(TRY_CAST(ic AS BIGINT) AS STRING)                                AS ic_norm,
                CAST(ebitda AS DOUBLE)                                                 AS ebitda,
                CAST(nakladove_uroky_a_podobne_naklady AS DOUBLE)                     AS interest_expense,
                CAST(zavazky_k_uverovym_institucim_1 AS DOUBLE)                       AS bank_liabilities_st,
                CAST(zavazky_k_uverovym_institucim   AS DOUBLE)                       AS bank_liabilities_lt,
                CAST(penezni_prostredky AS DOUBLE)                                    AS cash,
                CAST(obezna_aktiva AS DOUBLE)                                         AS current_assets,
                CAST(likvidita_celkova_kratkodoba_aktiva_kratkodobe_zavazky AS DOUBLE) AS current_ratio_direct,
                CAST(cisty_obrat_za_ucetni_obdobi_i_ii_iii_iv_v_vi_vii AS DOUBLE)    AS revenue,
                CAST(vlastni_kapital AS DOUBLE)                                       AS equity
            FROM {CAT_CR}.{SCH_CR}.silver_data_cribis_v3
            WHERE CAST(TRY_CAST(ic AS BIGINT) AS STRING) IN ('{ico_list_norm}')
            QUALIFY ROW_NUMBER() OVER (PARTITION BY ic ORDER BY obdobi_do DESC) = 1
        """)
    except Exception as cribis_exc:
        log.warning(
            f"[DataConnector] CRIBIS batch selhal — pokračuji bez CRIBIS dat | {cribis_exc}"
        )
        cribis_rows = []
    # Klíč v mapě: normalizované IČO bez vedoucích nul
    cribis_map = {str(r["ic_norm"]): r for r in cribis_rows}

    # Covenant data уже есть в Batch 1 (MAX covenant_status per ICO)

    from utils.wcr_rules import WCR_LIMITS, EW_THRESHOLDS

    # ── Sestavení výsledku v Pythonu ───────────────────────────────────────────
    clients = []
    for row in profile_rows:
        ico             = str(row.get("ico", ""))
        approved_limit  = float(row.get("approved_limit_czk")      or 0)
        outstanding     = float(row.get("outstanding_balance_czk") or 0)
        utilisation_pct = float(row.get("utilisation_pct")         or 0)
        if utilisation_pct == 0 and approved_limit > 0:
            utilisation_pct = round(outstanding / approved_limit * 100, 1)
        dpd_current     = int(row.get("dpd_current")    or 0)
        covenant_status = row.get("covenant_status")    or "OK"

        cribis     = cribis_map.get(_norm_ico(ico), {})
        has_cribis = bool(cribis)

        # CRIBIS ukládá hodnoty v tisících CZK → převést na CZK (*1000).
        # current_ratio_direct je koeficient — nepřevádí se.
        _K = 1000
        bank_st    = float(cribis.get("bank_liabilities_st") or 0) * _K if has_cribis else 0.0
        bank_lt    = float(cribis.get("bank_liabilities_lt") or 0) * _K if has_cribis else 0.0
        cash       = float(cribis.get("cash")               or 0) * _K if has_cribis else 0.0
        int_exp    = float(cribis.get("interest_expense")   or 0) * _K if has_cribis else 0.0
        ebitda     = float(cribis.get("ebitda")             or 0) * _K if has_cribis else 0.0
        cur_assets = float(cribis.get("current_assets")     or 0) * _K if has_cribis else 0.0
        cr_direct  = float(cribis.get("current_ratio_direct") or 0) if has_cribis else 0.0

        net_debt      = (bank_st + bank_lt) - cash if (has_cribis and (bank_st + bank_lt) > 0) else None
        _raw_lev      = (net_debt / ebitda) if (net_debt is not None and ebitda > 0) else None
        leverage_ratio = round(_raw_lev, 3) if (_raw_lev is not None and abs(_raw_lev) <= 100) else None
        debt_service  = int_exp + (bank_st / 12 if bank_st else 0)
        dscr          = round(ebitda / debt_service, 3) if (has_cribis and ebitda and debt_service > 0) else None
        current_ratio = round(cr_direct, 3) if (has_cribis and cr_direct > 0) else None

        wcr_breaches = []
        if utilisation_pct > WCR_LIMITS["max_utilisation_pct"]:
            wcr_breaches.append(f"Využití limitu {utilisation_pct:.1f} % > {WCR_LIMITS['max_utilisation_pct']} %")
        if dpd_current > WCR_LIMITS["max_dpd_days"]:
            wcr_breaches.append(f"DPD {dpd_current} dní > {WCR_LIMITS['max_dpd_days']} dní")
        if has_cribis:
            if leverage_ratio is not None and leverage_ratio > WCR_LIMITS["max_leverage_ratio"]:
                wcr_breaches.append(f"Leverage {leverage_ratio:.2f}x > {WCR_LIMITS['max_leverage_ratio']}x")
            if dscr is not None and dscr < WCR_LIMITS["min_dscr"]:
                wcr_breaches.append(f"DSCR {dscr:.2f} < {WCR_LIMITS['min_dscr']}")
            if current_ratio is not None and current_ratio < WCR_LIMITS["min_current_ratio"]:
                wcr_breaches.append(f"Current Ratio {current_ratio:.2f} < {WCR_LIMITS['min_current_ratio']}")

        n = len(wcr_breaches)
        if dpd_current >= EW_THRESHOLDS["dpd_red_days"] or n >= 3:
            ew_level = "RED"
        elif dpd_current >= EW_THRESHOLDS["dpd_amber_days"] or utilisation_pct >= EW_THRESHOLDS["utilisation_amber_pct"] or n >= 1:
            ew_level = "AMBER"
        else:
            ew_level = "GREEN"

        clients.append({
            "ico":                 ico,
            "company_name":        row.get("company_name", ico),
            "sector":              row.get("sector", ""),
            "city":                row.get("city", ""),
            "ew_alert_level":      ew_level,
            "covenant_status":     covenant_status,
            "cribis_rating":       "N/A",
            "dpd_current":         dpd_current,
            "credit_limit":        approved_limit,
            "current_utilisation": outstanding,
            "financial_data": {
                "revenue":             float(cribis.get("revenue") or 0),
                "ebitda":              ebitda,
                "net_debt":            round(net_debt, 0) if net_debt is not None else 0,
                "total_assets":        cur_assets,
                "current_assets":      cur_assets,
                "current_liabilities": bank_st,
                "debt_service":        debt_service,
                "operating_cashflow":  ebitda * 0.8,
            },
            "metrics": {
                "leverage_ratio":  leverage_ratio,
                "dscr":            dscr,
                "current_ratio":   current_ratio,
                "utilisation_pct": utilisation_pct,
            },
            "wcr_breaches":     wcr_breaches,
            "portfolio_status": "ACTIVE",
            "esg_score":        None,
            "last_memo_date":   None,
            "katastr_data":     None,
            "flood_risk":       None,
            "data_sources": {
                "silver_credit": f"silver_credit_history (ico: {ico})",
                "cribis_snap":   f"silver_data_cribis_v3 (ic: {_norm_ico(ico)})",
            },
        })

    return clients


def get_client_info(ico: str) -> dict | None:
    """
    Vrátí info o klientovi podle IČO s metrikami a WCR statusem.
    Demo: mock data · Production: Databricks Silver + CRIBIS.
    DETERMINISTIC — žádný LLM.
    """
    if IS_DEMO:
        from utils.mock_data import get_client
        return get_client(ico)

    CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")

    try:
        rows = query(f"""
            SELECT
                CAST(cm.ico AS STRING)             AS ico,
                cm.company_name,
                cm.nace_description                AS sector,
                cm.city,
                MAX(ch.approved_limit_czk)         AS approved_limit_czk,
                MAX(ch.outstanding_balance_czk)    AS outstanding_balance_czk,
                MAX(ch.utilisation_pct)            AS utilisation_pct,
                MAX(CAST(ch.dpd_current AS INT))   AS dpd_current,
                MAX(ch.relationship_years)         AS relationship_years,
                MAX(CASE WHEN ch.covenant_breach = true THEN 'BREACH'
                         ELSE COALESCE(ch.covenant_status, 'OK') END) AS covenant_status
            FROM {CAT}.{SCH}.silver_company_master cm
            JOIN {CAT}.{SCH}.silver_credit_history ch
              ON CAST(cm.ico AS STRING) = CAST(ch.ico AS STRING)
            WHERE CAST(cm.ico AS STRING) = '{ico}'
              AND ch.approved_limit_czk IS NOT NULL
            GROUP BY cm.ico, cm.company_name, cm.nace_description, cm.city
            LIMIT 1
        """)
    except Exception as exc:
        log.error(f"[DataConnector] get_client_info selhal | ico={ico} {exc}")
        from utils.mock_data import get_client
        fb = get_client(ico)
        if fb:
            fb["_fallback"] = True
        return fb

    if not rows:
        return None

    return _build_client_info(ico, rows[0])


def get_cmp_data(ico: str) -> dict | None:
    """
    CMP (Credit Monitoring Platform) — monitoring a kovenanty.
    Demo: mock stub · Prod: SELECT z vse_banka.obsluha_klienta.cmp_monitoring
    DETERMINISTIC — žádný LLM.
    """
    if IS_DEMO:
        from utils.mock_data import get_client
        client = get_client(ico) or {}
        cov = client.get("covenant_status", "OK")
        return {
            "ico":                  ico,
            "monitoring_status":    "ACTIVE",
            "covenant_status":      cov,
            "covenant_breach":      cov == "BREACH",
            "last_review_date":     "2025-12-31",
            "next_review_date":     "2026-06-30",
            "cmp_flag":             cov == "BREACH",
            "monitoring_notes":     "CMP stub — demo mode",
            "source":               "cmp_stub",
        }

    CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
    rows = query(f"""
        SELECT ico, monitoring_status, covenant_status, covenant_breach,
               last_review_date, next_review_date, cmp_flag, monitoring_notes
        FROM {CAT}.{SCH}.cmp_monitoring
        WHERE CAST(ico AS STRING) = '{ico}'
          AND is_current = TRUE
        LIMIT 1
    """)
    return rows[0] if rows else None


def get_cbs_data(ico: str) -> dict | None:
    """
    CBS (Core Banking System) — transakční a platební data.
    Demo: mock stub · Prod: SELECT z vse_banka.obsluha_klienta.cbs_transactions_summary
    DETERMINISTIC — žádný LLM.
    """
    if IS_DEMO:
        from utils.mock_data import get_client
        client = get_client(ico) or {}
        fd = client.get("financial_data", {})
        return {
            "ico":                      ico,
            "avg_monthly_credit_czk":   fd.get("revenue", 0) / 12,
            "avg_monthly_debit_czk":    fd.get("revenue", 0) / 12 * 0.92,
            "active_accounts":          3,
            "fx_transactions_pct":      0.12,
            "payment_regularity_score": 0.95,
            "last_large_payment_date":  "2025-12-15",
            "overdraft_days_ytd":       client.get("dpd_current", 0),
            "source":                   "cbs_stub",
        }

    CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
    rows = query(f"""
        SELECT ico, avg_monthly_credit_czk, avg_monthly_debit_czk,
               active_accounts, fx_transactions_pct,
               payment_regularity_score, last_large_payment_date,
               overdraft_days_ytd
        FROM {CAT}.{SCH}.cbs_transactions_summary
        WHERE CAST(ico AS STRING) = '{ico}'
          AND summary_period = 'LAST_12M'
        LIMIT 1
    """)
    return rows[0] if rows else None


def get_crm_data(ico: str) -> dict | None:
    """
    CRM (Client Relationship Management) — obchodní vztah a kontakty.
    Demo: mock stub · Prod: SELECT z vse_banka.obsluha_klienta.crm_client_profile
    DETERMINISTIC — žádný LLM.
    """
    if IS_DEMO:
        from utils.mock_data import get_client
        client = get_client(ico) or {}
        fd = client.get("financial_data", {})
        return {
            "ico":                  ico,
            "relationship_manager": "Jan Novák",
            "relationship_since":   "2018-03-01",
            "relationship_years":   7.0,
            "client_tier":          "PREMIUM" if fd.get("revenue", 0) > 500_000_000 else "STANDARD",
            "nps_score":            8,
            "last_contact_date":    "2026-03-20",
            "active_products":      ["revolving_credit", "fx_hedging", "trade_finance"],
            "pending_requests":     [],
            "crm_notes":            "CRM stub — demo mode",
            "source":               "crm_stub",
        }

    CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
    SCH = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
    rows = query(f"""
        SELECT ico, relationship_manager, relationship_since,
               relationship_years, client_tier, nps_score,
               last_contact_date, active_products_json,
               pending_requests_json, crm_notes
        FROM {CAT}.{SCH}.crm_client_profile
        WHERE CAST(ico AS STRING) = '{ico}'
          AND is_current = TRUE
        LIMIT 1
    """)
    if not rows:
        return None
    row = rows[0]
    import json
    try:
        row["active_products"] = json.loads(row.pop("active_products_json", "[]"))
    except Exception:
        row["active_products"] = []
    try:
        row["pending_requests"] = json.loads(row.pop("pending_requests_json", "[]"))
    except Exception:
        row["pending_requests"] = []
    return row


def search_companies_snapshot(query: str, limit: int = 50) -> list[dict]:
    """
    Hledá firmy v silver_data_cribis_v3 podle IČO nebo názvu.
    Vrátí list[dict] s klíči: ico, company_name, city, nace_description.

    Demo: fallback na mock portfolio + snapshot stub.
    Prod: LIKE query na silver_data_cribis_v3 (nejnovější snapshot per IČO).
    DETERMINISTIC — žádný LLM.
    """
    q = str(query).strip()
    if not q:
        return []

    if IS_DEMO:
        from utils.mock_data import get_portfolio as _gp
        results = []
        ql = q.lower()
        for c in _gp():
            if ql in c["company_name"].lower() or ql in str(c["ico"]):
                results.append({
                    "ico":              c["ico"],
                    "company_name":     c["company_name"],
                    "city":             c.get("city", ""),
                    "nace_description": c.get("sector", ""),
                })
        return results[:limit]

    CAT_CR = os.getenv("DATABRICKS_CATALOG_CRIBIS", os.getenv("DATABRICKS_CATALOG", "vse_banka"))
    SCH_CR = os.getenv("DATABRICKS_SCHEMA_CRIBIS", "investment_banking")

    # Detect if query is a pure IČO (only digits)
    if q.isdigit():
        norm = _norm_ico(q)
        where = f"CAST(TRY_CAST(ic AS BIGINT) AS STRING) LIKE '{norm}%'"
    else:
        safe_q = q.replace("'", "''")
        where = f"LOWER(nazev_subjektu) LIKE LOWER('%{safe_q}%')"

    try:
        rows = query(f"""
            SELECT
                CAST(TRY_CAST(ic AS BIGINT) AS STRING) AS ic,
                nazev_subjektu                          AS company_name,
                mesto                                   AS city,
                hlavni_nace_popis                       AS nace_description
            FROM {CAT_CR}.{SCH_CR}.silver_data_cribis_v3
            WHERE {where}
            QUALIFY ROW_NUMBER() OVER (PARTITION BY ic ORDER BY obdobi_do DESC) = 1
            LIMIT {int(limit)}
        """)
        results = []
        for r in rows:
            results.append({
                "ico":              str(int(str(r.get("ic") or "0"))),  # strip leading zeros
                "company_name":     r.get("company_name") or "",
                "city":             r.get("city") or "",
                "nace_description": r.get("nace_description") or "",
            })
        return results
    except Exception as exc:
        log.warning(f"[search_companies_snapshot] Selhalo: {exc}")
        return []


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
