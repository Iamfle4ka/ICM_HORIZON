"""
Fáze 2 — Deterministická analýza — pipeline/nodes/phase2_analysis.py

Uzly:
  - context_builder            ← sestaví CaseView z Silver tabulkových dat
  - credit_analysis_service    ← vypočítá dostupné metriky (ČISTÝ PYTHON)

DETERMINISTIC — žádný LLM v této fázi.

Poznámka k partial WCR:
  Ze Silver tabulek jsou dostupné: utilisation_pct, dpd_current.
  Leverage, DSCR, Current Ratio vyžadují CRIBIS (external) → None.
  Příznak wcr_partial=True informuje UI a underwritera.
"""

import logging

from utils.audit import _audit
from utils.wcr_rules import WCR_LIMITS

log = logging.getLogger(__name__)


# DETERMINISTIC
def context_builder(state: dict) -> dict:
    """
    Sestaví CaseView ze Silver tabulkových dat (výsledek Phase 1 extraction).

    Pokud extraction_result obsahuje raw_data (Silver path):
      - Agreguje transakce (12M)
      - Vypočítá transakční metriky
      - Sestaví data_sources mapu pro citace

    Fallback (legacy): pokud raw_data chybí, použije extraction_result přímo.
    Čistý Python, žádný LLM.
    """
    ico = state.get("ico", "UNKNOWN")
    log.info(f"[ContextBuilder] Zahajuji | ico={ico}")

    extraction = state.get("extraction_result")
    if not extraction:
        log.error(f"[ContextBuilder] Chybí extraction_result | ico={ico}")
        audit = _audit(
            state,
            node="ContextBuilder",
            action="context_build_failed",
            result="missing_extraction_result",
            metadata={"ico": ico},
        )
        return {**state, "audit_trail": audit}

    raw_data = extraction.get("raw_data")

    if raw_data:
        # ── Silver tabulky path ─────────────────────────────────────────────
        case_view = _build_case_view_from_raw_data(ico, extraction, raw_data)
    else:
        # ── Legacy path (backward compat — plná financial_data) ─────────────
        case_view = _build_case_view_legacy(ico, extraction)

    # ── CRIBIS obohacení (vždy — demo i prod) ──────────────────────────────
    try:
        from utils.data_connector import get_cribis_data, get_cribis_prev_period
        cribis = get_cribis_data(ico)
        if cribis:
            case_view["cribis_data"] = cribis
            case_view.setdefault("data_sources", {})["cribis"] = (
                "CRIBIS Tým 8 — silver_data_cribis_v3"
            )
            case_view["cribis_company_info"] = {
                "nazev_subjektu":              cribis.get("nazev_subjektu"),
                "hlavni_nace_popis":           cribis.get("hlavni_nace_popis"),
                "hlavni_nace_kod":             cribis.get("hlavni_nace_kod"),
                "pravni_forma":                cribis.get("pravni_forma"),
                "kategorie_poctu_zamestnancu": cribis.get("kategorie_poctu_zamestnancu"),
                "kategorie_obratu":            cribis.get("kategorie_obratu"),
                "mesto":                       cribis.get("mesto"),
                "obdobi_do":                   cribis.get("obdobi_do"),
            }
            # Předchozí období pro CAPEX výpočet
            try:
                cribis_prev = get_cribis_prev_period(ico)
                case_view["cribis_prev_period"] = cribis_prev
            except Exception:
                case_view["cribis_prev_period"] = None
            # Pokud financial_data prázdné, doplň z CRIBIS
            if not case_view.get("financial_data"):
                case_view["financial_data"] = {
                    "ebitda":              cribis.get("ebitda"),
                    "revenue":             cribis.get("revenue"),
                    "net_debt":            cribis.get("net_debt"),
                    "current_assets":      cribis.get("current_assets"),
                    "current_liabilities": None,
                    "debt_service":        None,
                    "operating_cashflow":  None,
                    "total_assets":        cribis.get("total_assets"),
                }
            log.info(
                f"[ContextBuilder] CRIBIS obohaceno | ico={ico} "
                f"leverage={cribis.get('leverage_ratio')} "
                f"has_prev={case_view.get('cribis_prev_period') is not None}"
            )
    except Exception as exc:
        log.warning(f"[ContextBuilder] CRIBIS nedostupné | ico={ico} error={exc}")

    sources_count = len(case_view.get("data_sources", {}))
    log.info(
        f"[ContextBuilder] CaseView sestaven | ico={ico} "
        f"company={case_view['company_name']} sources={sources_count} "
        f"has_raw_data={raw_data is not None}"
    )

    audit = _audit(
        state,
        node="ContextBuilder",
        action="context_built",
        result="success",
        metadata={
            "ico":                     ico,
            "company_name":            case_view["company_name"],
            "sources_count":           sources_count,
            "has_raw_data":            raw_data is not None,
            "missing_external_metrics": case_view.get("missing_external_metrics", []),
            "tx_months":               len(raw_data.get("transactions", [])) if raw_data else 0,
        },
    )

    return {**state, "case_view": case_view, "audit_trail": audit}


# DETERMINISTIC
def credit_analysis_service(state: dict) -> dict:
    """
    Vypočítá dostupné finanční metriky deterministicky.

    ABSOLUTNÍ PRAVIDLO: LLM se NIKDY nedotýká těchto výpočtů.

    Ze Silver tabulek (vždy dostupné):
      - credit_limit_utilization_pct
      - dpd_current
      - cash_flow_stability_score
      - overdraft_intensity
      - tax_compliance_rate
      - payroll_stability
      - mom_revenue_trend_pct
      - internal_rating

    Vyžadují CRIBIS (→ None pokud chybí):
      - leverage_ratio   (Net Debt / EBITDA)
      - dscr             (Operating CF / Debt Service)
      - current_ratio    (Current Assets / Current Liabilities)

    wcr_partial=True pokud některé WCR metriky nelze zkontrolovat.
    """
    ico = state.get("ico", "UNKNOWN")
    log.info(f"[CreditAnalysisService] Zahajuji výpočet metrik | ico={ico}")

    case_view = state.get("case_view")
    if not case_view:
        log.error(f"[CreditAnalysisService] Chybí case_view | ico={ico}")
        audit = _audit(
            state,
            node="CreditAnalysisService",
            action="analysis_failed",
            result="missing_case_view",
            metadata={"ico": ico},
        )
        return {**state, "audit_trail": audit}

    # ── Detekce zdroje dat ──────────────────────────────────────────────────
    silver_metrics = case_view.get("silver_metrics", {})
    fd             = case_view.get("financial_data", {})
    credit_limit   = float(case_view.get("credit_limit", 0.0) or 0.0)
    current_util   = float(case_view.get("current_utilisation", 0.0) or 0.0)
    dpd_current    = int(case_view.get("dpd_current", 0) or 0)

    # ── DETERMINISTIC: metriky dostupné ze Silver tabulek ──────────────────

    # Využití limitu — ze Silver credit_history
    if silver_metrics.get("weighted_utilisation_pct") is not None:
        utilisation_pct = float(silver_metrics["weighted_utilisation_pct"])  # DETERMINISTIC
    elif credit_limit > 0:
        utilisation_pct = (current_util / credit_limit) * 100.0              # DETERMINISTIC
    else:
        utilisation_pct = 0.0

    # Cash flow stabilita ze fin_profile
    cash_flow_volatility = float(silver_metrics.get("cash_flow_volatility", 0.0) or 0.0)
    cash_flow_stability = round(1.0 - cash_flow_volatility, 4)               # DETERMINISTIC

    # Overdraft intensity ze transactions
    overdraft_days_12m = float(silver_metrics.get("total_overdraft_days_12m", 0) or 0)
    overdraft_intensity = round(overdraft_days_12m / 365, 4)                 # DETERMINISTIC

    # Tax compliance ze transactions
    tax_payments_ok    = int(silver_metrics.get("tax_payments_ok", 0) or 0)
    tax_payments_total = int(silver_metrics.get("tax_payments_total", 12) or 12)
    tax_compliance_rate = round(
        (tax_payments_ok / tax_payments_total * 100) if tax_payments_total > 0 else 100.0,
        1,
    )  # DETERMINISTIC

    # Payroll stability a internal rating ze fin_profile
    payroll_stability = float(silver_metrics.get("payroll_stability", 0.0) or 0.0)
    internal_rating   = float(silver_metrics.get("internal_rating", 0.0) or 0.0)

    # MoM revenue trend ze transactions
    mom_revenue_trend_pct = silver_metrics.get("mom_turnover_change_pct")    # může být None

    # Další příznaky
    is_restructured = bool(case_view.get("is_restructured", False))
    cmp_monitored   = bool(case_view.get("cmp_monitored", False))
    relationship_years = float(case_view.get("relationship_years", 0.0) or 0.0)

    # Incidenty
    escalated_incidents = int(silver_metrics.get("escalated_incidents_24m", 0) or 0)
    incident_risk_flag  = escalated_incidents > 0

    # ── DETERMINISTIC: metriky vyžadující CRIBIS (přes compute_all_metrics) ──
    cribis_data  = case_view.get("cribis_data") or {}
    cribis_prev  = case_view.get("cribis_prev_period")

    leverage_ratio: float | None = None
    dscr:           float | None = None
    current_ratio:  float | None = None
    ebitda:         float | None = None
    net_debt:       float | None = None
    calc_metrics:   dict         = {}

    if cribis_data:
        # Primární cesta — compute_all_metrics() (CAPEX + daň vzorec)
        try:
            from utils.calculator import compute_all_metrics
            internal_input = {
                "ico":            ico,
                "utilisation_pct": utilisation_pct,
                "dpd_current":     dpd_current,
            }
            calc_metrics   = compute_all_metrics(cribis_data, internal_input, cribis_prev)
            leverage_ratio = calc_metrics.get("leverage_ratio")
            dscr           = calc_metrics.get("dscr")
            current_ratio  = calc_metrics.get("current_ratio")
            ebitda         = calc_metrics.get("ebitda")
            net_debt       = calc_metrics.get("net_debt")
        except Exception as calc_exc:
            log.warning(f"[CreditAnalysisService] compute_all_metrics selhalo: {calc_exc}")
            # Fallback na předpočtené hodnoty z CRIBIS
            leverage_ratio = cribis_data.get("leverage_ratio")
            dscr           = cribis_data.get("dscr")
            current_ratio  = cribis_data.get("current_ratio")
            ebitda         = cribis_data.get("ebitda")
            net_debt       = cribis_data.get("net_debt")
    else:
        # Legacy path fallback — financial_data (backward compat)
        ebitda_fd   = fd.get("ebitda")
        net_debt_fd = fd.get("net_debt")
        if ebitda_fd is not None and net_debt_fd is not None and float(ebitda_fd) != 0:
            leverage_ratio = round(float(net_debt_fd) / float(ebitda_fd), 2)   # DETERMINISTIC
            ebitda   = ebitda_fd
            net_debt = net_debt_fd

        op_cashflow_fd  = fd.get("operating_cashflow")
        debt_service_fd = fd.get("debt_service")
        if op_cashflow_fd is not None and debt_service_fd is not None and float(debt_service_fd) != 0:
            dscr = round(float(op_cashflow_fd) / float(debt_service_fd), 2)    # DETERMINISTIC

        current_assets_fd = fd.get("current_assets")
        current_liab_fd   = fd.get("current_liabilities")
        if current_assets_fd is not None and current_liab_fd is not None and float(current_liab_fd) != 0:
            current_ratio = round(float(current_assets_fd) / float(current_liab_fd), 2)  # DETERMINISTIC

    # Round for display
    if leverage_ratio is not None:
        leverage_ratio = round(float(leverage_ratio), 2)
    if dscr is not None:
        dscr = round(float(dscr), 2)
    if current_ratio is not None:
        current_ratio = round(float(current_ratio), 2)

    # Backward-compat variables
    current_assets = calc_metrics.get("current_assets") if calc_metrics else fd.get("current_assets")
    current_liab   = calc_metrics.get("current_liabilities") if calc_metrics else fd.get("current_liabilities")
    debt_service   = None if cribis_data else fd.get("debt_service")
    op_cashflow    = None if cribis_data else fd.get("operating_cashflow")

    # ── WCR Breach kontrola (pouze dostupné metriky) ────────────────────────
    wcr_breaches: list[str] = []
    wcr_skipped:  list[str] = []
    wcr_rules:    dict      = {}

    # ✅ Utilisation
    util_passed = utilisation_pct <= WCR_LIMITS["max_utilisation_pct"]
    wcr_rules["utilisation"] = {
        "value": round(utilisation_pct, 1),
        "limit": WCR_LIMITS["max_utilisation_pct"],
        "passed": util_passed,
        "source": "credit_history",
        "unit": "%",
        "skipped": False,
    }
    if not util_passed:
        wcr_breaches.append(
            f"Využití limitu {utilisation_pct:.1f} % překračuje maximum "
            f"{WCR_LIMITS['max_utilisation_pct']} %"
        )

    # ✅ DPD
    dpd_passed = dpd_current <= WCR_LIMITS["max_dpd_days"]
    wcr_rules["dpd"] = {
        "value": dpd_current,
        "limit": WCR_LIMITS["max_dpd_days"],
        "passed": dpd_passed,
        "source": "credit_history",
        "unit": " dní",
        "skipped": False,
    }
    if not dpd_passed:
        wcr_breaches.append(
            f"DPD {dpd_current} dní překračuje maximum {WCR_LIMITS['max_dpd_days']} dní"
        )

    # ⚠️ Leverage
    if leverage_ratio is not None:
        lev_passed = leverage_ratio <= WCR_LIMITS["max_leverage_ratio"]
        wcr_rules["leverage"] = {
            "value": leverage_ratio,
            "limit": WCR_LIMITS["max_leverage_ratio"],
            "passed": lev_passed,
            "source": "cribis_external",
            "unit": "x",
            "skipped": False,
        }
        if not lev_passed:
            wcr_breaches.append(
                f"Leverage Ratio {leverage_ratio:.2f}x překračuje limit "
                f"{WCR_LIMITS['max_leverage_ratio']}x"
            )
    else:
        wcr_rules["leverage"] = {
            "value": None, "limit": WCR_LIMITS["max_leverage_ratio"], "passed": None,
            "note": "Vyžaduje CRIBIS", "skipped": True, "unit": "x",
        }
        wcr_skipped.append("leverage_ratio")

    # ⚠️ DSCR
    if dscr is not None:
        dscr_passed = dscr >= WCR_LIMITS["min_dscr"]
        wcr_rules["dscr"] = {
            "value": dscr,
            "limit": WCR_LIMITS["min_dscr"],
            "passed": dscr_passed,
            "source": "cribis_external",
            "unit": "",
            "skipped": False,
        }
        if not dscr_passed:
            wcr_breaches.append(f"DSCR {dscr:.2f} je pod minimem {WCR_LIMITS['min_dscr']}")
    else:
        wcr_rules["dscr"] = {
            "value": None, "limit": WCR_LIMITS["min_dscr"], "passed": None,
            "note": "Vyžaduje CRIBIS", "skipped": True, "unit": "",
        }
        wcr_skipped.append("dscr")

    # ⚠️ Current Ratio
    if current_ratio is not None:
        cr_passed = current_ratio >= WCR_LIMITS["min_current_ratio"]
        wcr_rules["current_ratio"] = {
            "value": current_ratio,
            "limit": WCR_LIMITS["min_current_ratio"],
            "passed": cr_passed,
            "source": "cribis_external",
            "unit": "",
            "skipped": False,
        }
        if not cr_passed:
            wcr_breaches.append(
                f"Current Ratio {current_ratio:.2f} je pod minimem "
                f"{WCR_LIMITS['min_current_ratio']}"
            )
    else:
        wcr_rules["current_ratio"] = {
            "value": None, "limit": WCR_LIMITS["min_current_ratio"], "passed": None,
            "note": "Vyžaduje CRIBIS", "skipped": True, "unit": "",
        }
        wcr_skipped.append("current_ratio")

    checked_count = 5 - len(wcr_skipped)
    wcr_partial    = len(wcr_skipped) > 0
    data_completeness = (
        f"partial — {checked_count}/5 pravidel zkontrolováno z interních dat"
        if wcr_partial
        else "full — 5/5 pravidel zkontrolováno"
    )

    # ── Sestavení FinancialMetrics ──────────────────────────────────────────
    financial_metrics = {
        # Ze Silver tabulek
        "credit_limit_utilization_pct": round(utilisation_pct, 1),
        "dpd_current":                  dpd_current,
        "cash_flow_stability_score":    cash_flow_stability,
        "overdraft_intensity":          overdraft_intensity,
        "tax_compliance_rate":          tax_compliance_rate,
        "payroll_stability":            payroll_stability,
        "mom_revenue_trend_pct":        mom_revenue_trend_pct,
        "internal_rating":              internal_rating,
        "incident_risk_flag":           incident_risk_flag,
        "is_restructured":              is_restructured,
        "cmp_monitored":                cmp_monitored,
        "relationship_years":           relationship_years,
        # Ze CRIBIS (None pokud chybí)
        "leverage_ratio":               leverage_ratio,
        "dscr":                         dscr,
        "current_ratio":                current_ratio,
        "ebitda":                       ebitda,
        # Backward-compat raw inputs
        "utilisation_pct":              round(utilisation_pct, 1),
        "net_debt":                     net_debt,
        "revenue":                      fd.get("revenue"),
        "total_assets":                 fd.get("total_assets"),
        "current_assets":               current_assets,
        "current_liabilities":          current_liab,
        "debt_service":                 debt_service,
        "operating_cashflow":           op_cashflow,
        # WCR výsledek
        "wcr_breaches":       wcr_breaches,
        "wcr_skipped":        wcr_skipped,
        "wcr_partial":        wcr_partial,
        "data_completeness":  data_completeness,
        # Doplňkové metriky z calculator.py
        "icr":                calc_metrics.get("icr"),
        "quick_ratio":        calc_metrics.get("quick_ratio"),
        "debt_to_equity":     calc_metrics.get("debt_to_equity"),
        "equity_ratio":       calc_metrics.get("equity_ratio"),
        "asset_turnover":     calc_metrics.get("asset_turnover"),
        "capex":              calc_metrics.get("capex"),
        "capex_note":         calc_metrics.get("capex_note"),
        "wcr_warnings":       calc_metrics.get("wcr_warnings", []),
        "dscr_note":          calc_metrics.get("dscr_note"),
    }

    log.info(
        f"[CreditAnalysisService] Metriky vypočteny | ico={ico} "
        f"utilisation={utilisation_pct:.1f}% dpd={dpd_current} "
        f"leverage={leverage_ratio} dscr={dscr} "
        f"wcr_breaches={len(wcr_breaches)} wcr_partial={wcr_partial}"
    )

    audit = _audit(
        state,
        node="CreditAnalysisService",
        action="metrics_computed",
        result=f"utilisation={utilisation_pct:.1f}% dpd={dpd_current} breaches={len(wcr_breaches)}",
        metadata={
            "ico":                 ico,
            "utilisation_pct":     round(utilisation_pct, 1),
            "dpd_current":         dpd_current,
            "leverage_ratio":      leverage_ratio,
            "dscr":                dscr,
            "current_ratio":       current_ratio,
            "wcr_breaches":        len(wcr_breaches),
            "wcr_breach_details":  wcr_breaches,
            "wcr_partial":         wcr_partial,
            "wcr_skipped":         wcr_skipped,
            "data_completeness":   data_completeness,
        },
    )

    return {**state, "financial_metrics": financial_metrics, "audit_trail": audit}


# ── Privátní helpers ───────────────────────────────────────────────────────────


def _build_case_view_from_raw_data(ico: str, extraction: dict, raw_data: dict) -> dict:
    """Sestaví CaseView ze Silver tabulkových dat s agregacemi."""
    company     = raw_data.get("company", {})
    fin_profile = raw_data.get("fin_profile", {})
    credit      = raw_data.get("credit", [])
    transactions = raw_data.get("transactions", [])
    incidents   = raw_data.get("incidents", [])

    # ── Agregace z silver_transactions (12M) ────────────────────────────────
    credit_turnovers = [float(t.get("credit_turnover", 0) or 0) for t in transactions]
    debit_turnovers  = [float(t.get("debit_turnover", 0) or 0)  for t in transactions]
    min_balances     = [float(t.get("min_balance", 0) or 0)     for t in transactions]
    overdraft_days   = [int(t.get("overdraft_days", 0) or 0)    for t in transactions]
    payroll_amounts  = [float(t.get("payroll_amount", 0) or 0)  for t in transactions]
    payroll_counts   = [int(t.get("payroll_employees", 0) or 0) for t in transactions]
    tax_ok_list      = [t.get("tax_payment_made", "true") == "true" for t in transactions]

    avg_monthly_credit = sum(credit_turnovers) / len(credit_turnovers) if credit_turnovers else 0.0
    avg_monthly_debit  = sum(debit_turnovers) / len(debit_turnovers)   if debit_turnovers else 0.0
    min_balance_12m    = min(min_balances) if min_balances else 0.0
    total_overdraft_d  = sum(overdraft_days)
    avg_payroll_czk    = sum(payroll_amounts) / len(payroll_amounts) if payroll_amounts else 0.0
    avg_employee_count = sum(payroll_counts) / len(payroll_counts)   if payroll_counts else 0.0
    revenue_proxy_ann  = avg_monthly_credit * 12
    tax_payments_ok    = sum(1 for t in tax_ok_list if t)
    tax_payments_total = len(tax_ok_list)

    # MoM turnover change
    mom_change_pct: float | None = None
    if len(credit_turnovers) >= 2 and credit_turnovers[1] != 0:
        mom_change_pct = round((credit_turnovers[0] / credit_turnovers[1] - 1) * 100, 2)

    # ── Agregace z silver_credit_history ────────────────────────────────────
    total_limit       = sum(float(r.get("approved_limit_czk", 0) or 0) for r in credit)
    total_outstanding = sum(float(r.get("outstanding_balance_czk", 0) or 0) for r in credit)
    weighted_util_pct = (total_outstanding / total_limit * 100) if total_limit > 0 else 0.0
    max_dpd_current   = max((int(r.get("dpd_current", 0) or 0) for r in credit), default=0)
    has_cov_breach    = any(r.get("covenant_breach", "false") == "true" for r in credit)
    active_cov_status = "OK"
    for r in credit:
        if r.get("covenant_breach", "false") == "true":
            active_cov_status = r.get("covenant_status", "BREACH")
            break
    if active_cov_status == "OK" and credit:
        active_cov_status = credit[0].get("covenant_status", "OK")
    is_restructured    = any(r.get("restructured", "false") == "true" for r in credit)
    cmp_monitored      = any(r.get("cmp_flag", "false") == "true" for r in credit)
    relationship_years = max((float(r.get("relationship_years", 0) or 0) for r in credit), default=0.0)

    # ── Agregace z silver_client_incidents ──────────────────────────────────
    total_incidents    = len(incidents)
    escalated_inc      = sum(1 for i in incidents if i.get("escalated", "false") == "true")
    last_incident_date = incidents[0].get("incident_date") if incidents else None

    # Silver metriky (pro CreditAnalysisService)
    silver_metrics = {
        # Transakce 12M
        "avg_monthly_credit_turnover": round(avg_monthly_credit, 0),
        "avg_monthly_debit_turnover":  round(avg_monthly_debit, 0),
        "min_balance_12m":             round(min_balance_12m, 0),
        "total_overdraft_days_12m":    total_overdraft_d,
        "tax_compliance_rate":         round(
            (tax_payments_ok / tax_payments_total * 100) if tax_payments_total > 0 else 100.0, 1
        ),
        "tax_payments_ok":             tax_payments_ok,
        "tax_payments_total":          tax_payments_total,
        "avg_payroll_czk":             round(avg_payroll_czk, 0),
        "avg_employee_count":          round(avg_employee_count, 1),
        "mom_turnover_change_pct":     mom_change_pct,
        "revenue_proxy_annual":        round(revenue_proxy_ann, 0),
        # Credit history
        "weighted_utilisation_pct":    round(weighted_util_pct, 1),
        "max_dpd_current":             max_dpd_current,
        "has_covenant_breach":         has_cov_breach,
        "active_covenant_status":      active_cov_status,
        "is_restructured":             is_restructured,
        "cmp_monitored":               cmp_monitored,
        "relationship_years":          relationship_years,
        # Incidents 24M
        "total_incidents_24m":         total_incidents,
        "escalated_incidents_24m":     escalated_inc,
        "last_incident_date":          last_incident_date,
        # Fin profile
        "cash_flow_volatility":        fin_profile.get("cash_flow_volatility", 0.0),
        "payroll_stability":           fin_profile.get("salary_payment_stability", 0.0),
        "internal_rating":             fin_profile.get("internal_rating_score", 0.0),
    }

    data_sources = extraction.get("data_sources") or {
        "company_master":   "silver_company_master — základní info firmy",
        "fin_profile":      "silver_corporate_financial_profile — finanční profil (SCD Type 2)",
        "credit_history":   "silver_credit_history — kreditní historie a kovenanty",
        "transactions_12m": "silver_transactions — transakce posledních 12 měsíců",
        "incidents_24m":    "silver_client_incidents — incidenty posledních 24 měsíců",
        "cribis_external":  "CRIBIS — externí rating (pokud dostupný)",
    }

    return {
        "ico":                  ico,
        "company_name":         company.get("company_name", ""),
        "nace_description":     company.get("nace_description", ""),
        "archetype":            company.get("archetype", ""),
        "financial_data":       {},   # EBITDA/Net Debt chybí — vyžadují CRIBIS
        "credit_limit":         total_limit,
        "current_utilisation":  total_outstanding,
        "utilisation_pct":      round(weighted_util_pct, 1),
        "dpd_current":          max_dpd_current,
        "covenant_status":      active_cov_status,
        "cmp_monitored":        cmp_monitored,
        "is_restructured":      is_restructured,
        "relationship_years":   relationship_years,
        "portfolio_status":     extraction.get("portfolio_status", "ACTIVE"),
        "silver_metrics":       silver_metrics,
        "data_sources":         data_sources,
        "missing_external_metrics": extraction.get("missing_external_metrics", [
            "ebitda", "net_debt", "current_assets", "current_liabilities",
            "debt_service", "operating_cashflow", "cribis_rating",
        ]),
        "_source_map": {
            "credit_limit":     "credit_history",
            "utilisation_pct":  "credit_history",
            "dpd_current":      "credit_history",
            "covenant_status":  "credit_history",
            "transactions":     "transactions_12m",
            "incidents":        "incidents_24m",
            "fin_profile":      "fin_profile",
        },
    }


def _build_case_view_legacy(ico: str, extraction: dict) -> dict:
    """
    Legacy path — pokud raw_data chybí (backward compat).
    Sestaví CaseView přímo z extraction_result s financial_data.
    """
    data_sources: dict[str, str] = extraction.get("data_sources", {})
    if not data_sources:
        data_sources = {
            "cbs_2024":     "CBS finanční výkazy FY2024",
            "cribis_q3":    "CRIBIS rating report Q3/2025",
            "helios_memos": "Historické memo v Helios",
        }

    return {
        "ico":               extraction.get("ico", ico),
        "company_name":      extraction.get("company_name", ""),
        "financial_data":    extraction.get("financial_data", {}),
        "cribis_rating":     extraction.get("cribis_rating"),
        "katastr_data":      extraction.get("katastr_data"),
        "flood_risk":        extraction.get("flood_risk"),
        "historical_memos":  extraction.get("historical_memos", []),
        "credit_limit":      extraction.get("credit_limit", 0.0),
        "current_utilisation": extraction.get("current_utilisation", 0.0),
        "utilisation_pct":   extraction.get("utilisation_pct", 0.0),
        "dpd_current":       extraction.get("dpd_current", 0),
        "covenant_status":   extraction.get("covenant_status", "OK"),
        "cmp_monitored":     extraction.get("cmp_monitored", False),
        "is_restructured":   extraction.get("is_restructured", False),
        "relationship_years": extraction.get("relationship_years", 0.0),
        "portfolio_status":  extraction.get("portfolio_status", "ACTIVE"),
        "silver_metrics":    {},   # prázdné — legacy data
        "data_sources":      data_sources,
        "missing_external_metrics": [],  # legacy má plná data
        "_source_map": {
            "financial_data":   "cbs_2024",
            "cribis_rating":    "cribis_q3",
            "katastr_data":     "katastr",
            "historical_memos": "helios_memos",
        },
    }


if __name__ == "__main__":
    # Smoke test A — Silver path (bez CRIBIS dat)
    from pipeline.state import ProcessStatus

    mock_state_silver = {
        "ico": "27082440",
        "status": ProcessStatus.RUNNING,
        "audit_trail": [],
        "extraction_result": {
            "ico":          "27082440",
            "company_name": "Stavební holding Praha a.s.",
            "financial_data": {},   # bez CRIBIS
            "credit_limit":       500_000_000.0,
            "current_utilisation": 325_000_000.0,
            "utilisation_pct":    65.0,
            "dpd_current":        0,
            "is_restructured":    False,
            "cmp_monitored":      False,
            "relationship_years": 3.0,
            "raw_data": {
                "company": {"company_name": "Stavební holding Praha a.s.", "nace_description": "Stavebnictví"},
                "fin_profile": {
                    "avg_monthly_turnover": 100_000_000.0,
                    "cash_flow_volatility": 0.12,
                    "credit_limit_utilization": 0.65,
                    "salary_payment_stability": 0.97,
                    "internal_rating_score": 7.2,
                },
                "credit": [{
                    "approved_limit_czk": "500000000",
                    "outstanding_balance_czk": "325000000",
                    "utilisation_pct": "65.0",
                    "dpd_current": "0",
                    "restructured": "false",
                    "cmp_flag": "false",
                    "covenant_breach": "false",
                    "covenant_status": "OK",
                    "relationship_years": "3",
                }],
                "transactions": [
                    {"year_month": "2026-03", "credit_turnover": 102_000_000, "debit_turnover": 87_000_000,
                     "min_balance": 5_000_000, "avg_balance": 12_000_000, "overdraft_days": 0,
                     "tax_payment_made": "true", "payroll_amount": 18_000_000, "payroll_employees": 45},
                    {"year_month": "2026-02", "credit_turnover": 99_000_000, "debit_turnover": 85_000_000,
                     "min_balance": 4_800_000, "avg_balance": 11_500_000, "overdraft_days": 0,
                     "tax_payment_made": "true", "payroll_amount": 17_800_000, "payroll_employees": 44},
                ],
                "incidents": [],
            },
            "data_sources": {
                "company_master": "silver_company_master",
                "fin_profile": "silver_corporate_financial_profile",
                "credit_history": "silver_credit_history",
                "transactions_12m": "silver_transactions",
                "incidents_24m": "silver_client_incidents",
                "cribis_external": "CRIBIS",
            },
            "missing_external_metrics": ["ebitda", "net_debt", "current_assets", "current_liabilities"],
        },
    }

    sv = context_builder(mock_state_silver)
    assert sv["case_view"] is not None
    assert sv["case_view"]["company_name"] == "Stavební holding Praha a.s."
    assert sv["case_view"]["silver_metrics"]["weighted_utilisation_pct"] == 65.0
    print(f"  Silver CaseView: {sv['case_view']['company_name']}")
    print(f"  utilisation_pct: {sv['case_view']['silver_metrics']['weighted_utilisation_pct']}")

    sm = credit_analysis_service(sv)
    m = sm["financial_metrics"]
    # Demo mode: CRIBIS mock vždy dostupný → leverage/dscr jsou vyplněny
    assert abs(m["credit_limit_utilization_pct"] - 65.0) < 0.5
    print(f"  leverage_ratio: {m['leverage_ratio']} (CRIBIS mock v demo mode)")
    print(f"  dscr: {m['dscr']}")
    print(f"  wcr_partial: {m['wcr_partial']}")
    print(f"  utilisation: {m['credit_limit_utilization_pct']}")
    print(f"  data_completeness: {m['data_completeness']}")
    print(f"  icr: {m.get('icr')} | quick_ratio: {m.get('quick_ratio')}")

    # Smoke test B — Legacy path (s CRIBIS daty)
    mock_state_legacy = {
        "ico": "27082440",
        "status": ProcessStatus.RUNNING,
        "audit_trail": [],
        "extraction_result": {
            "ico":          "27082440",
            "company_name": "Stavební holding Praha a.s.",
            "financial_data": {
                "revenue":             1_200_000_000.0,
                "ebitda":              180_000_000.0,
                "net_debt":            684_000_000.0,
                "total_assets":        2_100_000_000.0,
                "current_assets":      650_000_000.0,
                "current_liabilities": 420_000_000.0,
                "debt_service":         90_000_000.0,
                "operating_cashflow":  130_500_000.0,
            },
            "credit_limit":       500_000_000.0,
            "current_utilisation": 325_000_000.0,
            "dpd_current":        0,
        },
    }

    lv = context_builder(mock_state_legacy)
    assert lv["case_view"] is not None
    lm = credit_analysis_service(lv)
    m2 = lm["financial_metrics"]
    assert abs(m2["leverage_ratio"] - 3.8) < 0.1, f"Expected ~3.8, got {m2['leverage_ratio']}"
    # DSCR s CAPEX vzorcem (ΔFA + odpisy): nižší než prosté op_cf/debt_service
    assert m2["dscr"] is not None and m2["dscr"] >= WCR_LIMITS["min_dscr"], \
        f"DSCR {m2['dscr']} musí být >= {WCR_LIMITS['min_dscr']}"
    assert m2["wcr_partial"] is False, "Legacy path: wcr_partial by měl být False"
    assert m2["wcr_breaches"] == [], f"Expected no breaches, got {m2['wcr_breaches']}"
    print(f"\n  Legacy leverage: {m2['leverage_ratio']} (expected ~3.8)")
    print(f"  Legacy dscr: {m2['dscr']} (CAPEX-adjusted, WCR >= {WCR_LIMITS['min_dscr']})")
    print(f"  Legacy wcr_partial: {m2['wcr_partial']} (expected False)")
    print(f"  Legacy icr: {m2.get('icr')} | capex: {m2.get('capex_note')}")

    print("OK — phase2_analysis.py smoke test passed")
