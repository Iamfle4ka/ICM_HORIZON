# DETERMINISTIC
"""
Financial Metrics Calculator — utils/calculator.py
Deterministický výpočet všech úvěrových metrik.

ABSOLUTNÍ PRAVIDLO: LLM se NIKDY nedotýká těchto výpočtů.
Všechny vzorce jsou auditovatelné, reprodukovatelné a nezávislé na API.

Funkce:
  compute_all_metrics(cribis, internal, cribis_prev=None) -> dict
  calc_dscr(...)
  calc_capex(...)
  calc_leverage(...)
  calc_icr(...)
  calc_current_ratio(...)
  calc_quick_ratio(...)
  calc_debt_to_equity(...)
  calc_equity_ratio(...)
  calc_asset_turnover(...)
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

# ── Safe arithmetic helpers ───────────────────────────────────────────────────


def _f(v) -> Optional[float]:
    """Bezpečná konverze na float; None pokud chybí nebo nelze převést."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _div(a, b, decimals: int = 3) -> Optional[float]:
    """Bezpečné dělení; None pokud b=0 nebo chybí vstupy."""
    fa, fb = _f(a), _f(b)
    if fa is None or fb is None or fb == 0.0:
        return None
    return round(fa / fb, decimals)


def _pct(a, b, decimals: int = 1) -> Optional[float]:
    """Bezpečná procentuální hodnota (a/b * 100)."""
    result = _div(a, b, decimals + 2)
    return round(result * 100, decimals) if result is not None else None


# ── Dílčí výpočty ────────────────────────────────────────────────────────────


def calc_capex(
    fixed_assets_curr: Optional[float],
    fixed_assets_prev: Optional[float],
    depreciation: Optional[float],
) -> tuple[Optional[float], str]:
    """
    CAPEX = max(0, stala_aktiva_curr - stala_aktiva_prev) + odpisy

    Pokud fixed_assets_prev chybí:
      CAPEX_proxy = odpisy  (konzervativnější, pouze D&A)

    Returns:
        (capex_value, note)
    """
    depr = _f(depreciation) or 0.0
    curr = _f(fixed_assets_curr)
    prev = _f(fixed_assets_prev)

    if curr is not None and prev is not None:
        capex = max(0.0, curr - prev) + depr
        note = "CAPEX: Δ(stálá aktiva) + odpisy"
    else:
        capex = depr
        note = "CAPEX proxy: použity pouze odpisy (prev_period chybí)"

    return round(capex, 0), note


def calc_dscr(
    ebitda: Optional[float],
    capex: Optional[float],
    income_tax: Optional[float],
    interest_expense: Optional[float],
    bank_liabilities_st: Optional[float],
) -> tuple[Optional[float], str]:
    """
    DSCR = (EBITDA - CAPEX - Daň) / (úroky + splátky hlavy)

    splátky hlavy = bank_liabilities_st / 12

    Returns:
        (dscr_value, note)
    """
    ebitda_f  = _f(ebitda)
    capex_f   = _f(capex) or 0.0
    tax_f     = _f(income_tax) or 0.0
    int_f     = _f(interest_expense) or 0.0
    bank_st_f = _f(bank_liabilities_st) or 0.0

    if ebitda_f is None:
        return None, "DSCR: chybí EBITDA"

    numerator = ebitda_f - capex_f - tax_f
    debt_service = int_f + (bank_st_f / 12.0)

    if debt_service <= 0.0:
        return None, "DSCR: debt service = 0 (nelze vypočítat)"

    dscr = round(numerator / debt_service, 3)
    note = f"DSCR = (EBITDA {ebitda_f/1e6:.1f}M - CAPEX {capex_f/1e6:.1f}M - daň {tax_f/1e6:.1f}M) / debt_service {debt_service/1e6:.1f}M"
    return dscr, note


def calc_leverage(
    bank_liabilities_st: Optional[float],
    bank_liabilities_lt: Optional[float],
    cash: Optional[float],
    ebitda: Optional[float],
) -> Optional[float]:
    """Net Debt / EBITDA. None pokud ebitda=0 nebo chybí."""
    st  = _f(bank_liabilities_st) or 0.0
    lt  = _f(bank_liabilities_lt) or 0.0
    c   = _f(cash) or 0.0
    eb  = _f(ebitda)
    if eb is None or eb <= 0.0:
        return None
    net_debt = (st + lt) - c
    raw_lev = net_debt / eb
    return round(raw_lev, 3) if abs(raw_lev) <= 100 else None


def calc_icr(
    ebitda: Optional[float],
    interest_expense: Optional[float],
) -> Optional[float]:
    """Interest Coverage Ratio = EBITDA / interest_expense."""
    return _div(ebitda, interest_expense, 2)


def calc_current_ratio(
    current_assets: Optional[float],
    current_liabilities: Optional[float],
    current_ratio_direct: Optional[float] = None,
) -> Optional[float]:
    """
    Current Ratio = oběžná aktiva / krátkodobé závazky.
    Pokud dostupná direktní hodnota z CRIBIS (likvidita_bezna), použije ji.
    """
    if current_ratio_direct is not None:
        f = _f(current_ratio_direct)
        return round(f, 3) if f is not None else None
    return _div(current_assets, current_liabilities, 3)


def calc_quick_ratio(
    current_assets: Optional[float],
    inventories: Optional[float],
    current_liabilities: Optional[float],
) -> Optional[float]:
    """Quick Ratio = (oběžná aktiva - zásoby) / krátkodobé závazky."""
    ca  = _f(current_assets)
    inv = _f(inventories) or 0.0
    cl  = _f(current_liabilities)
    if ca is None or cl is None or cl == 0.0:
        return None
    return round((ca - inv) / cl, 3)


def calc_debt_to_equity(
    total_debt: Optional[float],
    equity: Optional[float],
) -> Optional[float]:
    """D/E Ratio = cizí zdroje / vlastní kapitál."""
    return _div(total_debt, equity, 3)


def calc_equity_ratio(
    equity: Optional[float],
    total_assets: Optional[float],
) -> Optional[float]:
    """Equity Ratio = vlastní kapitál / aktiva celkem."""
    return _div(equity, total_assets, 4)


def calc_asset_turnover(
    revenue: Optional[float],
    total_assets: Optional[float],
) -> Optional[float]:
    """Asset Turnover = tržby / aktiva celkem."""
    return _div(revenue, total_assets, 3)


# ── Hlavní výpočetní funkce ──────────────────────────────────────────────────


def compute_all_metrics(
    cribis: dict,
    internal: dict,
    cribis_prev: Optional[dict] = None,
) -> dict:
    """
    Vypočítá všechny dostupné finanční metriky.

    Args:
        cribis:      Data z CRIBIS (silver_data_cribis_v3) — aktuální období.
        internal:    Interní Silver data (utilisation, dpd, atd.).
        cribis_prev: CRIBIS data za předchozí období (pro CAPEX). Může být None.

    Returns:
        dict s vypočtenými metrikami. None pokud data chybí.
    """
    # ── Extrakce z CRIBIS ────────────────────────────────────────────────────
    ebitda          = _f(cribis.get("ebitda"))
    revenue         = _f(cribis.get("revenue"))
    total_assets    = _f(cribis.get("total_assets"))
    current_assets  = _f(cribis.get("current_assets"))
    fixed_assets    = _f(cribis.get("fixed_assets") or cribis.get("stala_aktiva"))
    inventories     = _f(cribis.get("inventories") or cribis.get("zasoby"))
    cash            = _f(cribis.get("cash"))
    equity          = _f(cribis.get("equity"))
    total_debt      = _f(cribis.get("total_debt"))
    bank_liab_st    = _f(cribis.get("bank_liabilities_st"))
    bank_liab_lt    = _f(cribis.get("bank_liabilities_lt"))
    interest_exp    = _f(cribis.get("interest_expense"))
    depreciation    = _f(cribis.get("depreciation") or cribis.get("odpisy"))
    income_tax      = _f(cribis.get("income_tax") or cribis.get("dan_z_prijmu_1"))
    current_ratio_d = _f(cribis.get("current_ratio") or cribis.get("current_ratio_direct"))
    net_working_cap = _f(cribis.get("net_working_capital_k"))

    # Předchozí období pro CAPEX
    fixed_assets_prev = _f(cribis_prev.get("fixed_assets") or cribis_prev.get("stala_aktiva")) \
        if cribis_prev else None

    # ── Interní Silver data ──────────────────────────────────────────────────
    utilisation_pct = _f(internal.get("utilisation_pct")) or 0.0
    dpd_current     = int(_f(internal.get("dpd_current")) or 0)

    # ── Výpočty ──────────────────────────────────────────────────────────────

    # CAPEX
    capex_val, capex_note = calc_capex(fixed_assets, fixed_assets_prev, depreciation)

    # DSCR (s CAPEX a daní)
    dscr_val, dscr_note = calc_dscr(ebitda, capex_val, income_tax, interest_exp, bank_liab_st)

    # Leverage
    leverage = calc_leverage(bank_liab_st, bank_liab_lt, cash, ebitda)

    # ICR
    icr = calc_icr(ebitda, interest_exp)

    # Current Ratio + krátkodobé závazky
    # Priorita: pokud máme přímou hodnotu likvidita_bezna, odvoďme CL z ní.
    # Fallback: total_debt - bank_liab_lt (hrubá aproximace).
    current_liab = None
    if current_ratio_d is not None and current_assets is not None and current_ratio_d > 0:
        current_liab = round(current_assets / current_ratio_d, 0)   # odvozeno z CR přímé
    elif total_debt is not None and bank_liab_lt is not None:
        current_liab = max(0.0, total_debt - (bank_liab_lt or 0.0))
    cr = calc_current_ratio(current_assets, current_liab, current_ratio_d)

    # Quick Ratio
    qr = calc_quick_ratio(current_assets, inventories, current_liab)

    # D/E
    de = calc_debt_to_equity(total_debt, equity)

    # Equity Ratio
    er = calc_equity_ratio(equity, total_assets)

    # Asset Turnover
    at_ = calc_asset_turnover(revenue, total_assets)

    # Net debt (pro audit)
    net_debt = None
    if bank_liab_st is not None or bank_liab_lt is not None:
        net_debt = ((bank_liab_st or 0.0) + (bank_liab_lt or 0.0)) - (cash or 0.0)

    # ── WCR Warnings (ne breaches) ──────────────────────────────────────────
    from utils.wcr_rules import WCR_WARNINGS
    warnings: list[str] = []
    if icr is not None and icr < WCR_WARNINGS["icr_warning_threshold"]:
        warnings.append(f"ICR {icr:.2f}x pod varovnou hranicí {WCR_WARNINGS['icr_warning_threshold']}x")
    if de is not None and de > WCR_WARNINGS["max_debt_to_equity"]:
        warnings.append(f"D/E {de:.2f}x nad varovnou hranicí {WCR_WARNINGS['max_debt_to_equity']}x")
    if er is not None and er < WCR_WARNINGS["min_equity_ratio"]:
        warnings.append(f"Equity Ratio {er*100:.1f}% pod varovnou hranicí {WCR_WARNINGS['min_equity_ratio']*100:.0f}%")
    if qr is not None and qr < WCR_WARNINGS["min_quick_ratio"]:
        warnings.append(f"Quick Ratio {qr:.2f} pod varovnou hranicí {WCR_WARNINGS['min_quick_ratio']}")

    log.info(
        f"[Calculator] ico={internal.get('ico','?')} "
        f"leverage={leverage} dscr={dscr_val} cr={cr} "
        f"icr={icr} qr={qr} de={de} warnings={len(warnings)}"
    )

    return {
        # WCR metriky
        "leverage_ratio":       leverage,
        "dscr":                 dscr_val,
        "dscr_note":            dscr_note,
        "current_ratio":        cr,
        "utilisation_pct":      round(utilisation_pct, 1),
        "dpd_current":          dpd_current,
        # Doplňkové metriky
        "icr":                  icr,
        "quick_ratio":          qr,
        "debt_to_equity":       de,
        "equity_ratio":         er,
        "asset_turnover":       at_,
        # Raw hodnoty
        "ebitda":               ebitda,
        "revenue":              revenue,
        "net_debt":             round(net_debt, 0) if net_debt is not None else None,
        "current_assets":       current_assets,
        "current_liabilities":  current_liab,
        "inventories":          inventories,
        "total_assets":         total_assets,
        "equity":               equity,
        "total_debt":           total_debt,
        "capex":                capex_val,
        "capex_note":           capex_note,
        # WCR varování
        "wcr_warnings":         warnings,
        # YoY signály z CRIBIS
        "yoy_revenue_change_pct": _f(cribis.get("yoy_revenue_change_pct")),
        "yoy_ebitda_change_pct":  _f(cribis.get("yoy_ebitda_change_pct")),
    }


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.wcr_rules import WCR_LIMITS

    # Mock Stavební holding Praha a.s. (27082440)
    mock_cribis = {
        "ebitda":              180_000_000.0,
        "revenue":           1_200_000_000.0,
        "total_assets":      2_100_000_000.0,
        "current_assets":      650_000_000.0,
        "fixed_assets":      1_100_000_000.0,
        "inventories":         200_000_000.0,   # zásoby
        "cash":                 96_000_000.0,
        "equity":              700_000_000.0,
        "total_debt":        1_400_000_000.0,
        "bank_liabilities_st": 360_000_000.0,  # 30M/měsíc
        "bank_liabilities_lt": 420_000_000.0,
        "interest_expense":     30_000_000.0,
        "depreciation":         30_000_000.0,  # odpisy
        "dan_z_prijmu_1":       15_000_000.0,  # daň
        "current_ratio":         1.548,         # likvidita_bezna z CRIBIS
        "yoy_revenue_change_pct": 8.2,
        "yoy_ebitda_change_pct":  5.1,
    }
    # net_debt = (360 + 420) - 96 = 684M → leverage = 684/180 = 3.80x ✓

    mock_internal = {
        "ico":            "27082440",
        "utilisation_pct": 65.0,
        "dpd_current":     0,
    }

    metrics = compute_all_metrics(mock_cribis, mock_internal, cribis_prev=None)

    lev = metrics["leverage_ratio"]
    dscr = metrics["dscr"]
    cr  = metrics["current_ratio"]
    qr  = metrics["quick_ratio"]
    icr = metrics["icr"]
    de  = metrics["debt_to_equity"]
    er  = metrics["equity_ratio"]
    breaches = []
    if lev is not None and lev > WCR_LIMITS["max_leverage_ratio"]:
        breaches.append(f"Leverage {lev:.2f}x > {WCR_LIMITS['max_leverage_ratio']}x")
    if dscr is not None and dscr < WCR_LIMITS["min_dscr"]:
        breaches.append(f"DSCR {dscr:.2f} < {WCR_LIMITS['min_dscr']}")
    if cr is not None and cr < WCR_LIMITS["min_current_ratio"]:
        breaches.append(f"Current Ratio {cr:.2f} < {WCR_LIMITS['min_current_ratio']}")
    if metrics["utilisation_pct"] > WCR_LIMITS["max_utilisation_pct"]:
        breaches.append(f"Util {metrics['utilisation_pct']:.1f}% > {WCR_LIMITS['max_utilisation_pct']}%")
    if metrics["dpd_current"] > WCR_LIMITS["max_dpd_days"]:
        breaches.append(f"DPD {metrics['dpd_current']}d > {WCR_LIMITS['max_dpd_days']}d")

    print(f"Leverage:      {lev:.2f}x  (WCR ≤ {WCR_LIMITS['max_leverage_ratio']}x)")
    print(f"DSCR:          {dscr:.2f}   (WCR ≥ {WCR_LIMITS['min_dscr']}) | {metrics['dscr_note']}")
    print(f"Current Ratio: {cr:.2f}   (WCR ≥ {WCR_LIMITS['min_current_ratio']})")
    print(f"Quick Ratio:   {qr:.2f}   (norma > 1.0)")
    print(f"ICR:           {icr:.2f}x  (warning < 3.0x)")
    print(f"D/E:           {de:.2f}x  (warning > 3.0x)")
    print(f"Equity Ratio:  {er*100:.1f}%  (warning < 20%)")
    print(f"CAPEX note:    {metrics['capex_note']}")
    print(f"WCR Breaches:  {breaches}")
    print(f"WCR Warnings:  {metrics['wcr_warnings']}")

    assert lev is not None and abs(lev - 3.80) < 0.01, f"Leverage expected ~3.80, got {lev}"
    assert dscr is not None and dscr > 1.2, f"DSCR expected > 1.2, got {dscr}"
    assert cr is not None and abs(cr - 1.548) < 0.01, f"Current ratio expected ~1.548, got {cr}"
    assert qr is not None and qr > 1.0, f"Quick ratio expected > 1.0, got {qr}"
    assert icr is not None and icr > 3.0, f"ICR expected > 3.0, got {icr}"
    assert breaches == [], f"Expected no WCR breaches, got {breaches}"

    print("Calculator OK ✓")
