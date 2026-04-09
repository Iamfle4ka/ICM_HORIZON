"""
Fáze 2 — Deterministická analýza — pipeline/nodes/phase2_analysis.py

Uzly:
  - context_builder            ← sestaví CaseView z extrahovaných dat
  - credit_analysis_service    ← vypočítá finanční metriky (ČISTÝ PYTHON)

DETERMINISTIC — žádný LLM v této fázi.
"""

import logging

from utils.audit import _audit
from utils.wcr_rules import check_wcr_breaches

log = logging.getLogger(__name__)


# DETERMINISTIC
def context_builder(state: dict) -> dict:
    """
    Sestaví CaseView z Gold Layer dat (výsledek Phase 1 extraction).

    - Každé pole má přiřazený source_id (pro citace v memu)
    - Čistý Python, žádný LLM
    - Loguje začátek a konec
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

    # Sestavení data_sources mapy ze zdrojů extraction
    data_sources: dict[str, str] = extraction.get("data_sources", {})
    if not data_sources:
        # Výchozí zdroje pokud extraction neuvádí
        data_sources = {
            "cbs_2024":     "CBS finanční výkazy FY2024",
            "cribis_q3":    "CRIBIS rating report Q3/2025",
            "helios_memos": "Historické memo v Helios",
        }

    # Sestavení CaseView — každé pole má source_id
    case_view = {
        "ico":               extraction.get("ico", ico),
        "company_name":      extraction.get("company_name", ""),
        "financial_data":    extraction.get("financial_data", {}),
        "esg_score":         extraction.get("esg_score"),
        "cribis_rating":     extraction.get("cribis_rating"),
        "katastr_data":      extraction.get("katastr_data"),
        "flood_risk":        extraction.get("flood_risk"),
        "historical_memos":  extraction.get("historical_memos", []),
        "credit_limit":      extraction.get("credit_limit", 0.0),
        "current_utilisation": extraction.get("current_utilisation", 0.0),
        "portfolio_status":  extraction.get("portfolio_status", "ACTIVE"),
        "data_sources":      data_sources,
        # Metadata
        "_source_map": {
            "financial_data":    "cbs_2024",
            "cribis_rating":     "cribis_q3",
            "esg_score":         "esg_report",
            "katastr_data":      "katastr",
            "historical_memos":  "helios_memos",
        },
    }

    sources_count = len(data_sources)
    log.info(
        f"[ContextBuilder] CaseView sestaven | ico={ico} "
        f"company={case_view['company_name']} sources={sources_count}"
    )

    audit = _audit(
        state,
        node="ContextBuilder",
        action="context_built",
        result="success",
        metadata={
            "ico":           ico,
            "company_name":  case_view["company_name"],
            "sources_count": sources_count,
            "has_esg":       case_view["esg_score"] is not None,
            "has_katastr":   case_view["katastr_data"] is not None,
        },
    )

    return {**state, "case_view": case_view, "audit_trail": audit}


# DETERMINISTIC
def credit_analysis_service(state: dict) -> dict:
    """
    Vypočítá všechny finanční metriky deterministicky.

    ABSOLUTNÍ PRAVIDLO: LLM se NIKDY nedotýká těchto výpočtů.
    Každý výpočet je komentován # DETERMINISTIC.

    Metriky:
      - leverage_ratio = Net Debt / EBITDA
      - dscr           = Operating CF / Debt Service
      - current_ratio  = Current Assets / Current Liabilities
      - utilisation_pct = (current_util / credit_limit) * 100

    WCR breaches jsou také zde vypočteny.
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

    fd = case_view.get("financial_data", {})
    credit_limit     = case_view.get("credit_limit", 0.0)
    current_util     = case_view.get("current_utilisation", 0.0)

    # ── Ochrana před dělením nulou ──────────────────────────────────────────
    ebitda        = fd.get("ebitda") or 1.0
    debt_service  = fd.get("debt_service") or 1.0
    current_liab  = fd.get("current_liabilities") or 1.0
    credit_lim_safe = credit_limit or 1.0

    # ── DETERMINISTICKÉ VÝPOČTY ─────────────────────────────────────────────

    # DETERMINISTIC — Leverage Ratio: čím nižší, tím lepší (limit ≤ 5.0x)
    leverage_ratio: float = fd.get("net_debt", 0.0) / ebitda

    # DETERMINISTIC — DSCR: čím vyšší, tím lepší (min ≥ 1.2)
    dscr: float = fd.get("operating_cashflow", 0.0) / debt_service

    # DETERMINISTIC — Current Ratio: schopnost hradit krátkodobé závazky (min ≥ 1.0)
    current_ratio: float = fd.get("current_assets", 0.0) / current_liab

    # DETERMINISTIC — Využití limitu v % (max ≤ 85 %)
    utilisation_pct: float = (current_util / credit_lim_safe) * 100.0

    dpd_current: int = int(case_view.get("dpd_current", 0) or 0)

    # ── WCR Breach kontrola (DETERMINISTIC) ────────────────────────────────
    wcr_breaches = check_wcr_breaches(
        leverage_ratio=round(leverage_ratio, 2),
        dscr=round(dscr, 2),
        utilisation_pct=round(utilisation_pct, 1),
        current_ratio=round(current_ratio, 2),
        dpd_current=dpd_current,
    )

    # ── Sestavení FinancialMetrics ──────────────────────────────────────────
    financial_metrics = {
        # Raw inputs
        "ebitda":              fd.get("ebitda", 0.0),
        "net_debt":            fd.get("net_debt", 0.0),
        "revenue":             fd.get("revenue", 0.0),
        "total_assets":        fd.get("total_assets", 0.0),
        "current_assets":      fd.get("current_assets", 0.0),
        "current_liabilities": fd.get("current_liabilities", 0.0),
        "debt_service":        fd.get("debt_service", 0.0),
        "operating_cashflow":  fd.get("operating_cashflow", 0.0),
        # DETERMINISTIC Computed
        "leverage_ratio":  round(leverage_ratio, 2),
        "dscr":            round(dscr, 2),
        "current_ratio":   round(current_ratio, 2),
        "utilisation_pct": round(utilisation_pct, 1),
        "dpd_current":     dpd_current,
        # WCR výsledek
        "wcr_breaches": wcr_breaches,
    }

    log.info(
        f"[CreditAnalysisService] Metriky vypočteny | ico={ico} "
        f"leverage={leverage_ratio:.2f} dscr={dscr:.2f} "
        f"utilisation={utilisation_pct:.1f}% wcr_breaches={len(wcr_breaches)}"
    )

    audit = _audit(
        state,
        node="CreditAnalysisService",
        action="metrics_computed",
        result=f"leverage={leverage_ratio:.2f} dscr={dscr:.2f} breaches={len(wcr_breaches)}",
        metadata={
            "ico":              ico,
            "leverage_ratio":   round(leverage_ratio, 2),
            "dscr":             round(dscr, 2),
            "current_ratio":    round(current_ratio, 2),
            "utilisation_pct":  round(utilisation_pct, 1),
            "dpd_current":      dpd_current,
            "wcr_breaches":     len(wcr_breaches),
            "wcr_breach_details": wcr_breaches,
        },
    )

    return {**state, "financial_metrics": financial_metrics, "audit_trail": audit}


if __name__ == "__main__":
    # Smoke test
    from pipeline.state import ProcessStatus

    mock_state = {
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
            "credit_limit":      500_000_000.0,
            "current_utilisation": 325_000_000.0,
            "dpd_current":       0,
            "cribis_rating":     "A2",
            "esg_score":         68.2,
        },
    }

    # Test context_builder
    state_with_context = context_builder(mock_state)
    assert state_with_context["case_view"] is not None
    print(f"  CaseView: {state_with_context['case_view']['company_name']}")

    # Test credit_analysis_service
    state_with_metrics = credit_analysis_service(state_with_context)
    m = state_with_metrics["financial_metrics"]
    assert abs(m["leverage_ratio"] - 3.8) < 0.1, f"Expected ~3.8, got {m['leverage_ratio']}"
    assert abs(m["dscr"] - 1.45) < 0.1, f"Expected ~1.45, got {m['dscr']}"
    assert m["wcr_breaches"] == [], f"Expected no breaches, got {m['wcr_breaches']}"
    print(f"  Leverage: {m['leverage_ratio']} (expected ~3.8)")
    print(f"  DSCR: {m['dscr']} (expected ~1.45)")
    print(f"  WCR breaches: {m['wcr_breaches']}")
    print(f"  Audit events: {len(state_with_metrics['audit_trail'])}")

    print("OK — phase2_analysis.py smoke test passed")
