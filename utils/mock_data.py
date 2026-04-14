"""
Mock portfolio dat — utils/mock_data.py
6 klientů s různými profily rizik pro demo/testování.
DETERMINISTIC — žádný LLM.
"""

import hashlib
import logging
from datetime import datetime, timezone

from utils.wcr_rules import WCR_LIMITS, check_wcr_breaches, build_wcr_report

log = logging.getLogger(__name__)

# ── 6 mock klientů ─────────────────────────────────────────────────────────────

_PORTFOLIO: list[dict] = [
    {
        # 1 — Zdravé portfolio, EW: GREEN
        "ico":              "27082440",
        "company_name":     "Stavební holding Praha a.s.",
        "sector":           "Stavebnictví",
        "ew_alert_level":   "GREEN",
        "covenant_status":  "OK",
        "cribis_rating":    "A2",
        "esg_score":        68.2,
        "credit_limit":     500_000_000.0,       # 500 M CZK
        "current_utilisation": 325_000_000.0,    # 65 %
        "dpd_current":      0,
        "financial_data": {
            "revenue":             1_200_000_000.0,
            "ebitda":              180_000_000.0,
            "net_debt":            684_000_000.0,  # leverage 3.8
            "total_assets":        2_100_000_000.0,
            "current_assets":      650_000_000.0,
            "current_liabilities": 420_000_000.0,
            "debt_service":         90_000_000.0,
            "operating_cashflow":  130_500_000.0,  # dscr 1.45
        },
        "katastr_data": {
            "parcely": ["1234/5", "6789/2"],
            "LV": "1042",
            "katastralni_uzemi": "Praha 5 — Smíchov",
        },
        "flood_risk":        "Nízké",
        "last_memo_date":    "2026-01-15",
        "portfolio_status":  "ACTIVE",
        "data_sources": {
            "cbs_2024":   "CBS finanční výkazy FY2024",
            "cribis_q3":  "CRIBIS rating report Q3/2025",
            "helios_memos": "Historické memo v Helios (2023-2025)",
            "katastr":    "Katastr nemovitostí ČR — výpis LV",
        },
    },
    {
        # 2 — Problémový klient, EW: RED
        "ico":              "45274649",
        "company_name":     "Logistika Morava s.r.o.",
        "sector":           "Logistika & Doprava",
        "ew_alert_level":   "RED",
        "covenant_status":  "WARNING",
        "cribis_rating":    "B1",
        "esg_score":        51.0,
        "credit_limit":     200_000_000.0,       # 200 M CZK
        "current_utilisation": 180_000_000.0,    # 90 %
        "dpd_current":      12,
        "financial_data": {
            "revenue":              850_000_000.0,
            "ebitda":               68_000_000.0,
            "net_debt":            319_600_000.0,  # leverage 4.7
            "total_assets":        640_000_000.0,
            "current_assets":      210_000_000.0,
            "current_liabilities": 175_000_000.0,
            "debt_service":         65_000_000.0,
            "operating_cashflow":   76_700_000.0,  # dscr 1.18
        },
        "katastr_data":     None,
        "flood_risk":        "Střední",
        "last_memo_date":    "2025-11-30",
        "portfolio_status":  "ACTIVE",
        "data_sources": {
            "cbs_2024":   "CBS finanční výkazy FY2024",
            "cribis_q3":  "CRIBIS rating report Q3/2025",
            "helios_memos": "Historické memo v Helios (2022-2025)",
        },
    },
    {
        # 3 — Silný klient, EW: GREEN
        "ico":              "00514152",
        "company_name":     "Energetika Brno a.s.",
        "sector":           "Energetika",
        "ew_alert_level":   "GREEN",
        "covenant_status":  "OK",
        "cribis_rating":    "A1",
        "esg_score":        82.5,
        "credit_limit":     1_000_000_000.0,     # 1 mld CZK
        "current_utilisation": 500_000_000.0,    # 50 %
        "dpd_current":      0,
        "financial_data": {
            "revenue":             3_500_000_000.0,
            "ebitda":              490_000_000.0,
            "net_debt":          1_421_000_000.0,  # leverage 2.9
            "total_assets":      5_200_000_000.0,
            "current_assets":    1_100_000_000.0,
            "current_liabilities": 620_000_000.0,
            "debt_service":        190_000_000.0,
            "operating_cashflow":  326_800_000.0,  # dscr 1.72
        },
        "katastr_data": {
            "parcely": ["0045/1", "0046/1", "0047/3"],
            "LV": "0012",
            "katastralni_uzemi": "Brno-město — Špitálka",
        },
        "flood_risk":        "Velmi nízké",
        "last_memo_date":    "2026-02-28",
        "portfolio_status":  "ACTIVE",
        "data_sources": {
            "cbs_2024":   "CBS finanční výkazy FY2024",
            "cribis_q3":  "CRIBIS rating report Q3/2025",
            "helios_memos": "Historické memo v Helios (2020-2025)",
            "esg_report": "ESG Due Diligence Report 2025",
            "katastr":    "Katastr nemovitostí ČR — výpis LV",
        },
    },
    {
        # 4 — Středně rizikový, EW: AMBER
        "ico":              "26467054",
        "company_name":     "Retail Group CZ s.r.o.",
        "sector":           "Maloobchod",
        "ew_alert_level":   "AMBER",
        "covenant_status":  "WARNING",
        "cribis_rating":    "B2",
        "esg_score":        44.0,
        "credit_limit":     350_000_000.0,       # 350 M CZK
        "current_utilisation": 310_100_000.0,    # 88.6 %
        "dpd_current":      5,
        "financial_data": {
            "revenue":             1_800_000_000.0,
            "ebitda":              126_000_000.0,
            "net_debt":            529_200_000.0,  # leverage 4.2
            "total_assets":        980_000_000.0,
            "current_assets":      340_000_000.0,
            "current_liabilities": 280_000_000.0,
            "debt_service":        108_000_000.0,
            "operating_cashflow":  135_000_000.0,  # dscr 1.25
        },
        "katastr_data":     None,
        "flood_risk":        "Nízké",
        "last_memo_date":    "2025-12-10",
        "portfolio_status":  "ACTIVE",
        "data_sources": {
            "cbs_2024":   "CBS finanční výkazy FY2024",
            "cribis_q3":  "CRIBIS rating report Q3/2025",
            "helios_memos": "Historické memo v Helios (2021-2025)",
        },
    },
    {
        # 5 — Výborný klient, EW: GREEN
        "ico":              "63999714",
        "company_name":     "Farmaceutika Nord a.s.",
        "sector":           "Farmacie & Healthcare",
        "ew_alert_level":   "GREEN",
        "covenant_status":  "OK",
        "cribis_rating":    "AA",
        "esg_score":        79.0,
        "credit_limit":     800_000_000.0,       # 800 M CZK
        "current_utilisation": 261_600_000.0,    # 32.7 %
        "dpd_current":      0,
        "financial_data": {
            "revenue":             4_200_000_000.0,
            "ebitda":              756_000_000.0,
            "net_debt":          1_360_800_000.0,  # leverage 1.8
            "total_assets":      6_800_000_000.0,
            "current_assets":    2_100_000_000.0,
            "current_liabilities": 890_000_000.0,
            "debt_service":        240_000_000.0,
            "operating_cashflow":  504_000_000.0,  # dscr 2.10
        },
        "katastr_data": {
            "parcely": ["1122/1", "1122/2"],
            "LV": "4521",
            "katastralni_uzemi": "Ostrava — Přívoz",
        },
        "flood_risk":        "Nízké",
        "last_memo_date":    "2026-03-01",
        "portfolio_status":  "ACTIVE",
        "data_sources": {
            "cbs_2024":   "CBS finanční výkazy FY2024",
            "cribis_q3":  "CRIBIS rating report Q3/2025",
            "helios_memos": "Historické memo v Helios (2019-2025)",
            "esg_report": "ESG Due Diligence Report 2025",
            "katastr":    "Katastr nemovitostí ČR — výpis LV",
        },
    },
    {
        # 6 — Kritický klient, EW: RED, Covenant: BREACH
        "ico":              "49551895",
        "company_name":     "Textil Liberec s.r.o.",
        "sector":           "Textilní průmysl",
        "ew_alert_level":   "RED",
        "covenant_status":  "BREACH",
        "cribis_rating":    "C1",
        "esg_score":        38.0,
        "credit_limit":     150_000_000.0,       # 150 M CZK
        "current_utilisation": 142_050_000.0,    # 94.7 %
        "dpd_current":      45,
        "financial_data": {
            "revenue":              420_000_000.0,
            "ebitda":               29_400_000.0,
            "net_debt":            170_520_000.0,  # leverage 5.8
            "total_assets":        380_000_000.0,
            "current_assets":       95_000_000.0,
            "current_liabilities": 128_000_000.0,
            "debt_service":         35_000_000.0,
            "operating_cashflow":   33_250_000.0,  # dscr 0.95
        },
        "katastr_data":     None,
        "flood_risk":        "Vysoké",
        "last_memo_date":    "2025-09-15",
        "portfolio_status":  "ACTIVE",
        "data_sources": {
            "cbs_2024":   "CBS finanční výkazy FY2024",
            "cribis_q3":  "CRIBIS rating report Q3/2025",
            "helios_memos": "Historické memo v Helios (2022-2025)",
        },
    },
]


# ── Public API ─────────────────────────────────────────────────────────────────

# DETERMINISTIC
def get_portfolio() -> list[dict]:
    """Vrátí kompletní portfolio (6 klientů) s vypočtenými metrikami."""
    result = []
    for client in _PORTFOLIO:
        enriched = dict(client)
        enriched["metrics"] = _compute_metrics(client)
        enriched["wcr_breaches"] = _compute_breaches(client)
        result.append(enriched)
    return result


# DETERMINISTIC
def get_client(ico: str) -> dict | None:
    """
    Vrátí klienta podle IČO s vypočtenými metrikami.
    Returns None pokud IČO nenalezeno.
    """
    for client in _PORTFOLIO:
        if client["ico"] == ico:
            enriched = dict(client)
            enriched["metrics"] = _compute_metrics(client)
            enriched["wcr_breaches"] = _compute_breaches(client)
            return enriched
    log.warning(f"[MockData] Klient IČO={ico} nenalezen")
    return None


# DETERMINISTIC
def get_mock_agent_result(ico: str) -> dict:
    """
    Vrátí simulovaný výsledek pipeline pro demo mode.
    Obsahuje plný audit_trail s mock prompt_hash hodnotami.
    """
    client = get_client(ico)
    if client is None:
        return {"error": f"Klient IČO={ico} nenalezen"}

    metrics = client["metrics"]
    breaches = client["wcr_breaches"]
    wcr_report = build_wcr_report(
        leverage_ratio=metrics["leverage_ratio"],
        dscr=metrics["dscr"],
        utilisation_pct=metrics["utilisation_pct"],
        current_ratio=metrics["current_ratio"],
        dpd_current=client["dpd_current"],
        breaches=breaches,
    )

    memo = _mock_memo(client, metrics)
    audit_trail = _mock_audit_trail(client, metrics, breaches, memo)

    return {
        "ico":               ico,
        "request_id":        f"DEMO-{ico[:4]}-{_short_hash(ico)}",
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "company_name":      client["company_name"],
        "status":            "awaiting_human",
        "draft_memo":        memo,
        "citation_coverage": 0.93,
        "hallucination_report": [],
        "maker_iteration":   1,
        "checker_verdict":   "pass",
        "wcr_passed":        not breaches,
        "wcr_report":        wcr_report,
        "financial_metrics": {
            **metrics,
            "wcr_breaches": breaches,
            "dpd_current":  client["dpd_current"],
        },
        "case_view": {
            "ico":               ico,
            "company_name":      client["company_name"],
            "financial_data":    client["financial_data"],
            "esg_score":         client["esg_score"],
            "cribis_rating":     client["cribis_rating"],
            "katastr_data":      client.get("katastr_data"),
            "flood_risk":        client.get("flood_risk"),
            "historical_memos":  [f"Memo {client['last_memo_date']} — viz Helios"],
            "credit_limit":      client["credit_limit"],
            "current_utilisation": client["current_utilisation"],
            "portfolio_status":  client["portfolio_status"],
            "data_sources":      client["data_sources"],
        },
        "human_decision":    None,
        "human_comments":    None,
        "underwriter_diff":  None,
        "audit_trail":       audit_trail,
    }


# ── Privátní pomocné funkce ────────────────────────────────────────────────────

# DETERMINISTIC
def _compute_metrics(client: dict) -> dict:
    """Vypočítá finanční metriky z raw dat. Čistý Python, žádný LLM."""
    fd = client["financial_data"]
    credit_limit = client["credit_limit"]
    current_util = client["current_utilisation"]

    # Ochrana před dělením nulou
    ebitda = fd["ebitda"] or 1.0
    debt_service = fd["debt_service"] or 1.0
    current_liab = fd["current_liabilities"] or 1.0
    credit_lim_safe = credit_limit or 1.0

    leverage_ratio = fd["net_debt"] / ebitda                   # DETERMINISTIC
    dscr           = fd["operating_cashflow"] / debt_service   # DETERMINISTIC
    current_ratio  = fd["current_assets"] / current_liab       # DETERMINISTIC
    utilisation_pct = (current_util / credit_lim_safe) * 100.0 # DETERMINISTIC

    return {
        "leverage_ratio":  round(leverage_ratio, 2),
        "dscr":            round(dscr, 2),
        "current_ratio":   round(current_ratio, 2),
        "utilisation_pct": round(utilisation_pct, 1),
        # Raw inputs
        "ebitda":              fd["ebitda"],
        "net_debt":            fd["net_debt"],
        "revenue":             fd["revenue"],
        "total_assets":        fd["total_assets"],
        "current_assets":      fd["current_assets"],
        "current_liabilities": fd["current_liabilities"],
        "debt_service":        fd["debt_service"],
        "operating_cashflow":  fd["operating_cashflow"],
    }


# DETERMINISTIC
def _compute_breaches(client: dict) -> list[str]:
    """Spočítá WCR porušení. Čistý Python, žádný LLM."""
    metrics = _compute_metrics(client)
    return check_wcr_breaches(
        leverage_ratio=metrics["leverage_ratio"],
        dscr=metrics["dscr"],
        utilisation_pct=metrics["utilisation_pct"],
        current_ratio=metrics["current_ratio"],
        dpd_current=client["dpd_current"],
    )


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:6].upper()


def _mock_memo(client: dict, metrics: dict | None = None) -> str:
    """Generuje mock Credit Memo s [CITATION:] tagy. ESG NENÍ součástí Credit Memo."""
    if metrics is None:
        metrics = _compute_metrics(client)
    name = client["company_name"]
    ico = client["ico"]
    rating = client.get("cribis_rating", "N/A")
    limit_m = client["credit_limit"] / 1_000_000
    util_m = client["current_utilisation"] / 1_000_000
    revenue_m = client["financial_data"]["revenue"] / 1_000_000
    ebitda_m = client["financial_data"]["ebitda"] / 1_000_000
    sources = client.get("data_sources", {})
    src1 = list(sources.keys())[0] if sources else "cbs_2024"
    src2 = list(sources.keys())[1] if len(sources) > 1 else src1

    ew = client["ew_alert_level"]
    ew_note = {
        "GREEN": "bez výrazných varovných signálů",
        "AMBER": "mírné varovné signály vyžadují monitoring",
        "RED":   "kritické varovné signály — eskalace doporučena",
    }.get(ew, "")

    return f"""# Credit Memo — {name} ({ico})
**Datum:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}  |  **Stupeň důvěrnosti:** INTERNÍ  |  **Generováno:** ICM GenAI Platform · Tým 7

---

## 1. Executive Summary

Společnost {name} (IČO: {ico}) [CITATION:{src1}] je aktivním klientem Citi Bank
s úvěrovým limitem {limit_m:.0f} M CZK [CITATION:{src1}] a aktuálním čerpáním
{util_m:.1f} M CZK [CITATION:{src1}] ({metrics['utilisation_pct']:.1f} % limitu).

Early Warning úroveň: **{ew}** — {ew_note}.
CRIBIS rating: **{rating}** [CITATION:{src2}].

Doporučení: {"Schválit s monitoringem" if ew == "GREEN" else "Podmínečně schválit — vyžaduje zvýšený dohled" if ew == "AMBER" else "Předložit k eskalaci Risk Committee"}.

## 2. Informace o společnosti

- **Název:** {name}
- **IČO:** {ico} [CITATION:{src1}]
- **Sektor:** {client['sector']}
- **Status portfolia:** {client['portfolio_status']} [CITATION:{src1}]

## 3. Finanční analýza

### 3.1 Klíčové ukazatele

| Ukazatel | Hodnota | Limit WCR | Status |
|----------|---------|-----------|--------|
| Leverage Ratio (Net Debt/EBITDA) | {metrics['leverage_ratio']:.2f}x [CITATION:{src1}] | ≤ 5.0x | {"✅" if metrics['leverage_ratio'] <= 5.0 else "❌"} |
| DSCR | {metrics['dscr']:.2f} [CITATION:{src1}] | ≥ 1.2 | {"✅" if metrics['dscr'] >= 1.2 else "❌"} |
| Current Ratio | {metrics['current_ratio']:.2f} [CITATION:{src1}] | ≥ 1.0 | {"✅" if metrics['current_ratio'] >= 1.0 else "❌"} |
| Využití limitu | {metrics['utilisation_pct']:.1f} % [CITATION:{src1}] | ≤ 85 % | {"✅" if metrics['utilisation_pct'] <= 85 else "❌"} |
| DPD | {client['dpd_current']} dní [CITATION:{src1}] | ≤ 30 dní | {"✅" if client['dpd_current'] <= 30 else "❌"} |

### 3.2 Výnosnost

- Roční obrat: **{revenue_m:.0f} M CZK** [CITATION:{src1}]
- EBITDA: **{ebitda_m:.0f} M CZK** [CITATION:{src1}]
- EBITDA marže: **{(client['financial_data']['ebitda']/client['financial_data']['revenue']*100):.1f} %** [CITATION:{src1}]

## 4. Doporučení

Na základě dostupných dat a předem vypočtených metrik [CITATION:{src1}] doporučujeme:

{"**SCHVÁLIT** — klient splňuje všechna WCR kritéria." if not _compute_breaches(client) else f"**PODMÍNEČNĚ SCHVÁLIT** — klient vykazuje {len(_compute_breaches(client))} WCR porušení vyžadujících pozornost underwritera."}

---
*Generováno: ICM GenAI Platform · Tým 7 · Citi Bank*
*Tento dokument vyžaduje schválení underwritera (4-Eyes Rule)*
*Veškerá čísla pocházejí z deterministicky vypočtených metrik — LLM matematiku nepočítal.*
"""


def _mock_audit_trail(
    client: dict,
    metrics: dict,
    breaches: list[str],
    memo: str,
) -> list[dict]:
    """Generuje mock audit trail pro demo mode."""
    now = datetime.now(timezone.utc)
    ico = client["ico"]

    def ts(offset_sec: int = 0) -> str:
        from datetime import timedelta
        return (now.replace(microsecond=0).replace(
            second=now.second + offset_sec
        )).isoformat() if offset_sec == 0 else \
            (now.replace(microsecond=0)).isoformat()

    return [
        {
            "timestamp":      ts(),
            "node":           "DataExtractorAgent",
            "action":         "extraction_started",
            "result":         "success",
            "prompt_hash":    _short_hash(f"extractor_{ico}").lower(),
            "prompt_version": "2.3",
            "tokens_used":    842,
            "metadata":       {"sources_count": len(client["data_sources"]), "ico": ico},
        },
        {
            "timestamp":      ts(),
            "node":           "ExtractionValidator",
            "action":         "validation",
            "result":         "passed",
            "prompt_hash":    None,
            "prompt_version": None,
            "tokens_used":    None,
            "metadata":       {"confidence_score": 0.92, "fields_validated": 6},
        },
        {
            "timestamp":      ts(),
            "node":           "ContextBuilder",
            "action":         "context_built",
            "result":         "success",
            "prompt_hash":    None,
            "prompt_version": None,
            "tokens_used":    None,
            "metadata":       {"sources_count": len(client["data_sources"])},
        },
        {
            "timestamp":      ts(),
            "node":           "CreditAnalysisService",
            "action":         "metrics_computed",
            "result":         f"leverage={metrics['leverage_ratio']} dscr={metrics['dscr']}",
            "prompt_hash":    None,
            "prompt_version": None,
            "tokens_used":    None,
            "metadata":       {"wcr_breaches": len(breaches)},
        },
        {
            "timestamp":      ts(),
            "node":           "MemoPreparationAgent",
            "action":         "memo_drafted",
            "result":         "success",
            "prompt_hash":    _short_hash(f"maker_{ico}").lower(),
            "prompt_version": "3.1",
            "tokens_used":    1205,
            "metadata":       {"iteration": 1, "memo_length": len(memo)},
        },
        {
            "timestamp":      ts(),
            "node":           "QualityControlChecker",
            "action":         "quality_check",
            "result":         "pass",
            "prompt_hash":    _short_hash(f"checker_{ico}").lower(),
            "prompt_version": "2.0",
            "tokens_used":    623,
            "metadata":       {"citation_coverage": 0.93, "hallucinations": 0},
        },
        {
            "timestamp":      ts(),
            "node":           "PolicyRulesEngine",
            "action":         "wcr_check",
            "result":         "passed" if not breaches else f"{len(breaches)}_breaches",
            "prompt_hash":    None,
            "prompt_version": None,
            "tokens_used":    None,
            "metadata":       {"breaches": breaches},
        },
        {
            "timestamp":      ts(),
            "node":           "HumanReview",
            "action":         "awaiting_decision",
            "result":         "awaiting_human",
            "prompt_hash":    None,
            "prompt_version": None,
            "tokens_used":    None,
            "metadata":       {"ew_alert_level": client["ew_alert_level"]},
        },
    ]


# DETERMINISTIC
def _mock_transactions_12m(ico: str) -> list[dict]:
    """Generuje 12 měsíců mock transakčních dat pro demo mode."""
    import random
    from datetime import timedelta

    client = get_client(ico)
    is_red = client and client.get("ew_alert_level") == "RED"
    base_turnover = (
        client["financial_data"]["revenue"] / 12
        if client
        else 8_500_000.0
    )
    trend = 0.98 if is_red else 1.01
    months = []
    now = datetime.now(timezone.utc)
    for i in range(12):
        month = (now - timedelta(days=30 * i)).strftime("%Y-%m")
        turnover = base_turnover * (trend ** i) * random.uniform(0.92, 1.08)
        months.append({
            "year_month":       month,
            "credit_turnover":  round(turnover, 0),
            "debit_turnover":   round(turnover * 0.85, 0),
            "min_balance":      round(turnover * 0.05, 0),
            "avg_balance":      round(turnover * 0.12, 0),
            "overdraft_days":   0 if not is_red else random.randint(0, 8),
            "overdraft_depth":  0,
            "tax_payment_made": "true",
            "tax_delay_days":   0,
            "payroll_amount":   round(turnover * 0.18, 0),
            "payroll_employees": 45,
            "deposit_balance":  round(turnover * 0.08, 0),
            "savings_balance":  round(turnover * 0.03, 0),
        })
    return months


def _mock_cribis(ico: str) -> dict | None:
    """Mock CRIBIS data pro demo mode — silver_data_cribis_v3."""
    client = get_client(ico)
    if not client:
        return None

    fd = client.get("financial_data", {})
    ebitda      = float(fd.get("ebitda", 0) or 0)
    revenue     = float(fd.get("revenue", 0) or 0)
    net_debt    = float(fd.get("net_debt", 0) or 0)
    curr_assets = float(fd.get("current_assets", 0) or 0)
    curr_liab   = float(fd.get("current_liabilities", 0) or 0)
    total_assets = float(fd.get("total_assets", 0) or 0)

    # Aproximace bankovních závazků z net_debt
    bank_lt      = round(net_debt * 0.65 + ebitda * 0.1, 0) if net_debt else 0
    bank_st      = round(net_debt * 0.35 - ebitda * 0.1, 0) if net_debt else 0
    cash         = max(0.0, round(bank_st + bank_lt - net_debt, 0))
    interest_exp = round(net_debt * 0.045, 0) if net_debt else 0
    total_debt   = bank_st + bank_lt

    # Odvozené hodnoty pro calculator.py
    fixed_assets = max(0.0, total_assets - curr_assets)
    inventories  = round(curr_assets * 0.30, 0)          # ~30 % oběžných aktiv
    depreciation = round(ebitda * 0.15, 0)               # ~15 % EBITDA (D&A proxy)
    income_tax   = round(ebitda * 0.55 * 0.19, 0)        # daň 19 % ze zisku před daní
    equity       = max(0.0, total_assets - total_debt)

    # WCR metriky
    leverage_ratio = round(net_debt / ebitda, 3) if ebitda else None
    current_ratio  = round(curr_assets / curr_liab, 3) if curr_liab else None

    ew = client.get("ew_alert_level", "GREEN")

    return {
        "ic":                    ico,
        "nazev_subjektu":        client.get("company_name", ""),
        "revenue":               revenue,
        "ebitda":                ebitda,
        "ebit":                  round(ebitda * 0.85, 0),
        "net_income":            round(ebitda * 0.55, 0),
        "current_ratio":         current_ratio,
        "roa":                   round(ebitda / (total_assets or 1) * 100, 1),
        "roe":                   round(ebitda * 0.55 / (equity or 1) * 100, 1),
        "ros":                   round(ebitda / revenue * 100, 1) if revenue else None,
        "total_leverage_pct":    round(total_debt / (total_assets or 1) * 100, 1),
        "bank_liabilities_st":   bank_st,
        "bank_liabilities_lt":   bank_lt,
        "cash":                  cash,
        "interest_expense":      interest_exp,
        "total_assets":          total_assets or None,
        "current_assets":        curr_assets,
        "fixed_assets":          fixed_assets,
        "inventories":           inventories,
        "depreciation":          depreciation,
        "income_tax":            income_tax,
        "total_debt":            total_debt,
        "equity":                equity,
        "net_debt":              net_debt,
        "leverage_ratio":        leverage_ratio,
        # dscr se přepočítá v calculator.py (CAPEX+daň vzorec)
        "dscr":                  None,
        "dscr_note":             "Počítáno v calculator.py (EBITDA-CAPEX-daň / DS)",
        "net_working_capital_k": round((curr_assets - curr_liab) / 1000, 0),
        "yoy_revenue_change_pct": -5.0 if ew == "RED" else 3.5,
        "yoy_ebitda_change_pct":  -8.0 if ew == "RED" else 2.0,
        "is_suspicious":         False,
        "missing_key_kpi":       False,
        "periods_count":         4,
    }


def _mock_cribis_prev(ico: str) -> dict | None:
    """Mock CRIBIS data za předchozí účetní období (pro CAPEX výpočet)."""
    client = get_client(ico)
    if not client:
        return None

    fd = client.get("financial_data", {})
    total_assets = float(fd.get("total_assets", 0) or 0)
    curr_assets  = float(fd.get("current_assets", 0) or 0)
    fixed_assets = max(0.0, total_assets - curr_assets)

    # Předchozí rok: stálá aktiva přibližně o 5 % nižší (bez nových investic)
    return {
        "ic":          ico,
        "stala_aktiva": round(fixed_assets * 0.95, 0),
        "fixed_assets": round(fixed_assets * 0.95, 0),
        "odpisy":       round(float(fd.get("ebitda", 0) or 0) * 0.14, 0),
        "depreciation": round(float(fd.get("ebitda", 0) or 0) * 0.14, 0),
        "ebitda":       round(float(fd.get("ebitda", 0) or 0) * 0.92, 0),
        "revenue":      round(float(fd.get("revenue", 0) or 0) * 0.93, 0),
    }


if __name__ == "__main__":
    # Smoke test
    portfolio = get_portfolio()
    assert len(portfolio) == 6

    client = get_client("27082440")
    assert client is not None
    assert client["company_name"] == "Stavební holding Praha a.s."
    assert abs(client["metrics"]["leverage_ratio"] - 3.8) < 0.1

    result = get_mock_agent_result("49551895")
    assert result["wcr_passed"] is False
    assert len(result["wcr_report"]["breaches"]) > 0

    print(f"OK — mock_data.py smoke test passed ({len(portfolio)} klientů)")
    for c in portfolio:
        breaches = c["wcr_breaches"]
        print(f"  {c['ew_alert_level']:5s} {c['company_name']} ({c['ico']}) — {len(breaches)} breaches")
