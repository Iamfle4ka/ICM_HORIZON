# DETERMINISTIC
"""
WCR (Working Capital Requirements) Rules Engine — utils/wcr_rules.py
Konstanty a deterministická kontrola limitů.
ŽÁDNÝ LLM — čistý Python.
"""

import logging

log = logging.getLogger(__name__)

# ── WCR limity (Risk Management approved) ─────────────────────────────────────

WCR_LIMITS: dict[str, float | int] = {
    "max_leverage_ratio":  5.0,   # Net Debt / EBITDA ≤ 5.0x
    "min_dscr":            1.2,   # DSCR ≥ 1.2
    "max_utilisation_pct": 85.0,  # Využití limitu ≤ 85%
    "min_current_ratio":   1.2,   # Current Ratio ≥ 1.2  (updated from 1.0)
    "max_dpd_days":        30,    # DPD ≤ 30 dní
}

# ── WCR varování (soft limity — ne breach, ale sledovat) ─────────────────────

WCR_WARNINGS: dict[str, float] = {
    "icr_warning_threshold": 3.0,   # ICR < 3.0x → varování (dříve 2.0)
    "max_debt_to_equity":    3.0,   # D/E > 3.0x → varování
    "min_equity_ratio":      0.20,  # Equity Ratio < 20 % → varování
    "min_quick_ratio":       1.0,   # Quick Ratio < 1.0 → varování
}

# ── Oborové benchmarky (orientační) ──────────────────────────────────────────

WCR_BENCHMARKS: dict[str, dict[str, float]] = {
    "stavebnictvi": {
        "leverage_median": 3.5,
        "dscr_median":     1.5,
        "current_ratio":   1.3,
        "equity_ratio":    0.30,
    },
    "logistika": {
        "leverage_median": 4.0,
        "dscr_median":     1.3,
        "current_ratio":   1.1,
        "equity_ratio":    0.25,
    },
    "energetika": {
        "leverage_median": 4.5,
        "dscr_median":     1.4,
        "current_ratio":   1.2,
        "equity_ratio":    0.35,
    },
    "retail": {
        "leverage_median": 3.0,
        "dscr_median":     1.6,
        "current_ratio":   1.4,
        "equity_ratio":    0.28,
    },
    "default": {
        "leverage_median": 3.8,
        "dscr_median":     1.4,
        "current_ratio":   1.2,
        "equity_ratio":    0.28,
    },
}

# ── Pipeline guardy ───────────────────────────────────────────────────────────

MIN_CONFIDENCE_SCORE  = 0.85   # OCR/extraction threshold
MIN_CITATION_COVERAGE = 0.90   # 90 % čísel musí mít [CITATION:]
MAX_MAKER_ITERATIONS  = 3      # Maker-Checker loop guard
API_RETRY_COUNT       = 3
API_RETRY_DELAY_SEC   = 30
MAX_SUBAGENTS         = 10     # Guard pro případný budoucí spawning

# ── Early Warning System prahy ─────────────────────────────────────────────────

EW_THRESHOLDS: dict[str, float] = {
    "utilisation_red_pct":    85.0,   # Využití ≥ 85 % → RED
    "utilisation_amber_pct":  75.0,   # Využití ≥ 75 % → AMBER
    "utilisation_trend_30d":  15.0,   # Nárůst > 15 pp za 30 dní → AMBER
    "dpd_red_days":           30.0,   # DPD ≥ 30 dní → RED
    "dpd_amber_days":         15.0,   # DPD ≥ 15 dní → AMBER
    "revenue_drop_red_pct":   20.0,   # Pokles obratu > 20 % MoM → RED
    "revenue_drop_amber_pct": 10.0,   # Pokles obratu > 10 % MoM → AMBER
    "days_to_breach_amber":   60.0,   # < 60 dní do breach → AMBER
    "overdraft_red_pct":      50.0,   # ≥ 50 % dní v přečerpání (3M) → RED
    "overdraft_amber_pct":    20.0,   # ≥ 20 % dní v přečerpání (3M) → AMBER
    "tax_compliance_amber":   67.0,   # Tax compliance < 67 % → AMBER
    "covenant_risk_red":       0.7,   # Composite ≥ 0.7 → RED
    "covenant_risk_amber":     0.5,   # Composite ≥ 0.5 → AMBER
}

# ── Popis pravidel (pro UI) ───────────────────────────────────────────────────

WCR_RULE_DESCRIPTIONS: dict[str, str] = {
    "max_leverage_ratio":  "Leverage Ratio (Net Debt / EBITDA) ≤ 5.0x",
    "min_dscr":            "DSCR (EBITDA - CAPEX - Daň) / Debt Service ≥ 1.2",
    "max_utilisation_pct": "Využití úvěrového limitu ≤ 85 %",
    "min_current_ratio":   "Current Ratio (Oběžná aktiva / Kr. závazky) ≥ 1.2",
    "max_dpd_days":        "Days Past Due ≤ 30 dní",
}


# DETERMINISTIC
def check_wcr_breaches(
    leverage_ratio:   float,
    dscr:             float,
    utilisation_pct:  float,
    current_ratio:    float,
    dpd_current:      int,
) -> list[str]:
    """
    Zkontroluje všechny WCR limity a vrátí seznam porušení.
    Čistý Python, žádný LLM.

    Returns:
        list[str]: Prázdný seznam = vše OK. Neprázdný = porušení.
    """
    breaches: list[str] = []

    log.info(
        f"[WCRChecker] Kontrola limitů | leverage={leverage_ratio:.2f} "
        f"dscr={dscr:.2f} util={utilisation_pct:.1f}% "
        f"current_ratio={current_ratio:.2f} dpd={dpd_current}"
    )

    if leverage_ratio > WCR_LIMITS["max_leverage_ratio"]:
        breaches.append(
            f"Leverage Ratio {leverage_ratio:.2f}x překračuje limit "
            f"{WCR_LIMITS['max_leverage_ratio']}x"
        )

    if dscr < WCR_LIMITS["min_dscr"]:
        breaches.append(
            f"DSCR {dscr:.2f} je pod minimem {WCR_LIMITS['min_dscr']}"
        )

    if utilisation_pct > WCR_LIMITS["max_utilisation_pct"]:
        breaches.append(
            f"Využití limitu {utilisation_pct:.1f} % překračuje maximum "
            f"{WCR_LIMITS['max_utilisation_pct']} %"
        )

    if current_ratio < WCR_LIMITS["min_current_ratio"]:
        breaches.append(
            f"Current Ratio {current_ratio:.2f} je pod minimem "
            f"{WCR_LIMITS['min_current_ratio']}"
        )

    if dpd_current > WCR_LIMITS["max_dpd_days"]:
        breaches.append(
            f"DPD {dpd_current} dní překračuje maximum "
            f"{WCR_LIMITS['max_dpd_days']} dní"
        )

    log.info(
        f"[WCRChecker] Výsledek | breaches={len(breaches)} | "
        f"{'OK' if not breaches else ', '.join(breaches)}"
    )
    return breaches


# DETERMINISTIC
def build_wcr_report(
    leverage_ratio:  float,
    dscr:            float,
    utilisation_pct: float,
    current_ratio:   float,
    dpd_current:     int,
    breaches:        list[str],
) -> dict:
    """
    Sestaví strukturovaný WCR report pro každé pravidlo zvlášť.
    Používá se pro UI zobrazení a audit trail.
    """
    rules = [
        {
            "rule":        "max_leverage_ratio",
            "description": WCR_RULE_DESCRIPTIONS["max_leverage_ratio"],
            "value":       leverage_ratio,
            "limit":       WCR_LIMITS["max_leverage_ratio"],
            "passed":      leverage_ratio <= WCR_LIMITS["max_leverage_ratio"],
            "unit":        "x",
        },
        {
            "rule":        "min_dscr",
            "description": WCR_RULE_DESCRIPTIONS["min_dscr"],
            "value":       dscr,
            "limit":       WCR_LIMITS["min_dscr"],
            "passed":      dscr >= WCR_LIMITS["min_dscr"],
            "unit":        "",
        },
        {
            "rule":        "max_utilisation_pct",
            "description": WCR_RULE_DESCRIPTIONS["max_utilisation_pct"],
            "value":       utilisation_pct,
            "limit":       WCR_LIMITS["max_utilisation_pct"],
            "passed":      utilisation_pct <= WCR_LIMITS["max_utilisation_pct"],
            "unit":        "%",
        },
        {
            "rule":        "min_current_ratio",
            "description": WCR_RULE_DESCRIPTIONS["min_current_ratio"],
            "value":       current_ratio,
            "limit":       WCR_LIMITS["min_current_ratio"],
            "passed":      current_ratio >= WCR_LIMITS["min_current_ratio"],
            "unit":        "",
        },
        {
            "rule":        "max_dpd_days",
            "description": WCR_RULE_DESCRIPTIONS["max_dpd_days"],
            "value":       dpd_current,
            "limit":       WCR_LIMITS["max_dpd_days"],
            "passed":      dpd_current <= WCR_LIMITS["max_dpd_days"],
            "unit":        " dní",
        },
    ]

    return {
        "rules":           rules,
        "total_rules":     len(rules),
        "passed_rules":    sum(1 for r in rules if r["passed"]),
        "failed_rules":    sum(1 for r in rules if not r["passed"]),
        "overall_passed":  not breaches,
        "breaches":        breaches,
    }


if __name__ == "__main__":
    # Smoke test
    breaches = check_wcr_breaches(
        leverage_ratio=5.8,
        dscr=0.95,
        utilisation_pct=94.7,
        current_ratio=0.8,
        dpd_current=45,
    )
    report = build_wcr_report(5.8, 0.95, 94.7, 0.8, 45, breaches)
    print(f"Breaches: {len(breaches)}")
    for b in breaches:
        print(f"  ❌ {b}")
    print("OK — wcr_rules smoke test passed")
