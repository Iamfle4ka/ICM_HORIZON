"""
Mock portfolio dat — utils/mock_data.py
~97 klientů s různými profily rizik pro demo/testování.
DETERMINISTIC — žádný LLM.
"""

import hashlib
import logging
import random
import os
import pandas as pd
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from utils.wcr_rules import WCR_LIMITS, check_wcr_breaches, build_wcr_report

log = logging.getLogger(__name__)

_CSV_DATA = None

def _get_csv_data() -> dict:
    global _CSV_DATA
    if _CSV_DATA is not None:
        return _CSV_DATA

    base_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    try:
        df_company = pd.read_csv(os.path.join(base_dir, "company_master.csv"), dtype={"ico": str})
        df_tx = pd.read_csv(os.path.join(base_dir, "transactions.csv"), dtype={"ico": str})
        df_ch = pd.read_csv(os.path.join(base_dir, "credit_history.csv"), dtype={"ico": str})

        company_lookup = {row["ico"]: row for _, row in df_company.iterrows()}
        
        tx_lookup = {}
        for ico, g in df_tx.groupby("ico"):
            avg_credit_turnover = g["credit_turnover_czk"].mean() * 1_000_000
            avg_debit_turnover = g["debit_turnover_czk"].mean() * 1_000_000
            overdraft_occurrences = int((g["overdraft_days"] > 0).sum())
            tx_lookup[ico] = {
                "avg_credit_turnover": round(avg_credit_turnover, 0),
                "avg_debit_turnover": round(avg_debit_turnover, 0),
                "overdraft_occurrences": overdraft_occurrences
            }

        ch_lookup = {}
        for ico, g in df_ch.groupby("ico"):
            ch_lookup[ico] = {
                "loans": [row.to_dict() for _, row in g.iterrows()],
                "total_limit": float(g["approved_limit_czk"].sum() * 1_000_000),
                "total_outstanding": float(g["outstanding_balance_czk"].sum() * 1_000_000),
                "max_historical_dpd": int(g["dpd_max_historical"].max()),
                "current_dpd": int(g["dpd_current"].max()),
                "has_breach": bool((g["covenant_status"] == "breach").any()),
                "has_restructuring": bool(g["restructured"].any()),
            }

        _CSV_DATA = {
            "companies": company_lookup,
            "transactions": tx_lookup,
            "credit_history": ch_lookup,
        }
    except Exception as e:
        log.warning(f"Chyba naćtení CSV dat: {e}")
        _CSV_DATA = {"companies": {}, "transactions": {}, "credit_history": {}}

    return _CSV_DATA



# ── Zdrojová data firem ────────────────────────────────────────────────────────
# (name, ico, city)
_COMPANY_DEFS: list[tuple[str, str, str]] = [
    # Stavebnictví (8)
    ("Stavební holding Praha a.s.",      "27082440", "Praha"),
    ("Stavby Morava s.r.o.",             "28145633", "Brno"),
    ("Construkt CZ a.s.",                "25643789", "Ostrava"),
    ("Inženýrské stavby Plzeň s.r.o.",   "47821036", "Plzeň"),
    ("Pozemní stavby Zlín a.s.",         "60123456", "Zlín"),
    ("Betonstav Jihlava s.r.o.",         "48905712", "Jihlava"),
    ("Silniční stavby ČR a.s.",          "35967841", "Praha"),
    ("Modular Build s.r.o.",             "72345618", "Hradec Králové"),
    # Logistika & Doprava (7)
    ("Logistika Morava s.r.o.",          "45274649", "Brno"),
    ("TransCargo CZ a.s.",               "52187430", "Ostrava"),
    ("Expres Logistik s.r.o.",           "63812745", "Praha"),
    ("Rychlá Přeprava a.s.",             "41789023", "Plzeň"),
    ("Dopravní holding s.r.o.",          "38904512", "Liberec"),
    ("CoolChain CZ a.s.",                "74512389", "České Budějovice"),
    ("Intermodal Trans s.r.o.",          "56723091", "Pardubice"),
    # Energetika (7)
    ("Energetika Brno a.s.",             "00514152", "Brno"),
    ("Solar Power CZ s.r.o.",            "29817345", "Praha"),
    ("Wind Energy Morava a.s.",          "68234571", "Ostrava"),
    ("Tepelné sítě ČR s.r.o.",           "43129867", "Plzeň"),
    ("Elektro Distribuce a.s.",          "57890123", "Olomouc"),
    ("GreenEnergy s.r.o.",               "81234567", "Liberec"),
    ("Bioplynové stanice CZ a.s.",       "34567890", "Zlín"),
    # Maloobchod (6)
    ("Retail Group CZ s.r.o.",           "26467054", "Praha"),
    ("MegaMart a.s.",                    "53902817", "Brno"),
    ("Fashion Retail s.r.o.",            "37891245", "Ostrava"),
    ("HomeDeco CZ a.s.",                 "61823904", "Plzeň"),
    ("TechShop s.r.o.",                  "44918273", "Praha"),
    ("Supermarket Holding a.s.",         "79012345", "Olomouc"),
    # Farmacie & Healthcare (6)
    ("Farmaceutika Nord a.s.",           "63999714", "Ostrava"),
    ("BioPharm CZ s.r.o.",               "31847509", "Praha"),
    ("MedTech Solutions a.s.",           "75239018", "Brno"),
    ("Lékárna Plus s.r.o.",              "48701234", "Liberec"),
    ("ClinLab CZ a.s.",                  "92345678", "Praha"),
    ("HealthCare Holding s.r.o.",        "55678901", "Hradec Králové"),
    # Výroba & Průmysl (7)
    ("Průmyslový holding CZ a.s.",       "22345678", "Ostrava"),
    ("Kovárna Plzeň s.r.o.",             "18923456", "Plzeň"),
    ("Plastikárna Morava a.s.",          "87654321", "Zlín"),
    ("CNC Výroba Brno s.r.o.",           "14567890", "Brno"),
    ("SteelWork CZ a.s.",                "68901234", "Ostrava"),
    ("Pneu Pro s.r.o.",                  "33490125", "Praha"),
    ("Elektronika Výroba a.s.",          "50123789", "Pardubice"),
    # IT & Technologie (7)
    ("SoftCo Praha a.s.",                "91234567", "Praha"),
    ("DataCloud CZ s.r.o.",              "16789012", "Brno"),
    ("CyberSec Solutions a.s.",          "78901234", "Praha"),
    ("AI Platform s.r.o.",               "43218765", "Praha"),
    ("ERP Systems CZ a.s.",              "67890123", "Brno"),
    ("IoT Connect s.r.o.",               "25890134", "Ostrava"),
    ("Fintech Labs a.s.",                "84321098", "Praha"),
    # Potravinářství (6)
    ("Potravinářský závod CZ a.s.",      "19876543", "Olomouc"),
    ("Mlékárna Morava s.r.o.",           "56019283", "České Budějovice"),
    ("Pivovar Bohemia a.s.",             "32107654", "Plzeň"),
    ("Cukrovary CZ s.r.o.",              "71234509", "Pardubice"),
    ("Pekárny a Cukrárny a.s.",          "44321567", "Praha"),
    ("FoodGroup Holding s.r.o.",         "89012345", "Brno"),
    # Zemědělství (5)
    ("Agrohospodářství Čechy a.s.",      "23456789", "Jihlava"),
    ("Živočišná výroba CZ s.r.o.",       "67012345", "Olomouc"),
    ("Agro Morava a.s.",                 "12345098", "Zlín"),
    ("Zeleninofarma s.r.o.",             "54329876", "Hradec Králové"),
    ("Biofarm CZ a.s.",                  "98012345", "České Budějovice"),
    # Textilní průmysl (4 — rizikovější)
    ("Textil Liberec s.r.o.",            "49551895", "Liberec"),
    ("Obuv Morava a.s.",                 "37812904", "Zlín"),
    ("Konfekce CZ s.r.o.",               "61023458", "Ústí nad Labem"),
    ("Textilní holding a.s.",            "28901237", "Liberec"),
    # Strojírenství (6)
    ("Strojírna Praha a.s.",             "45678901", "Praha"),
    ("Hydraulika Brno s.r.o.",           "73012456", "Brno"),
    ("Nástrojárna Ostrava a.s.",         "19234567", "Ostrava"),
    ("Přesná Mechanika s.r.o.",          "86012345", "Plzeň"),
    ("Robotic Systems CZ a.s.",          "31209876", "Praha"),
    ("MachineGroup s.r.o.",              "54012378", "Pardubice"),
    # Chemický průmysl (5)
    ("Chemie Skupina CZ a.s.",           "20987654", "Ústí nad Labem"),
    ("Laky Barvy CZ s.r.o.",             "64012398", "Praha"),
    ("Plasty Chemie a.s.",               "47012389", "Ostrava"),
    ("Hnojiva Morava s.r.o.",            "83012478", "Olomouc"),
    ("Pharma Chemie CZ a.s.",            "36012789", "Brno"),
    # Autoprůmysl & Doprava (5)
    ("AutoDíly CZ a.s.",                 "59012456", "Praha"),
    ("Karosérie CZ s.r.o.",              "72012389", "Mladá Boleslav"),
    ("Autoservis Holding a.s.",          "41012789", "Brno"),
    ("Fleet Management s.r.o.",          "26012347", "Praha"),
    ("Moto Import CZ a.s.",              "88012367", "Ostrava"),
    # Realitní sektor (5)
    ("Realitní Holding Praha a.s.",      "13012456", "Praha"),
    ("Komerční nemovitosti s.r.o.",      "77012349", "Brno"),
    ("Industrial Park CZ a.s.",          "58012367", "Ostrava"),
    ("Office Solutions s.r.o.",          "39012456", "Praha"),
    ("Bytový Fond CZ a.s.",              "93012456", "Plzeň"),
    # Telekomunikace (5)
    ("TeleConnect CZ a.s.",              "24012789", "Praha"),
    ("BroadBand Solutions s.r.o.",       "61012789", "Brno"),
    ("FibreNet CZ a.s.",                 "48012567", "Ostrava"),
    ("DataTel s.r.o.",                   "85012456", "Praha"),
    ("Satelitní Sítě CZ a.s.",           "37012456", "Karlovy Vary"),
]

# Fixní EW override pro původních 6 klientů (dle dokumentace)
_EW_OVERRIDES: dict[str, str] = {
    "27082440": "GREEN",   # Stavební holding Praha
    "45274649": "RED",     # Logistika Morava
    "00514152": "GREEN",   # Energetika Brno
    "26467054": "AMBER",   # Retail Group CZ
    "63999714": "GREEN",   # Farmaceutika Nord
    "49551895": "RED",     # Textil Liberec
}

# ── Žadatelé o úvěr (17 firem) ────────────────────────────────────────────────
# Směs existujících klientů s historií a zcela nových žadatelů.
_APPLICANT_DEFS: list[tuple[str, str, str]] = [
    # Známí klienti banky (mají historii a data v CSV)
    ("ERILENS s.r.o.",                   "45306371", "Praha"),
    ("ADAMIK Company, s.r.o.",           "26845318", "Paskov"),
    ("B.S.Dental s.r.o.",                "60203170", "Praha"),
    ("Zlatá Bohemia s.r.o.",             "9774459", "Praha"),
    ("DEL a.s.",                         "8962669", "Praha"),
    ("SEED SERVICE s.r.o.",              "26006715", "Vysoké Mýto"),
    ("EXBIO Praha, a.s.",                "25548611", "Vestec"),
    ("ATS Praha s.r.o.",                 "27635007", "Praha"),
    ("Cyklosport RIK s.r.o.",            "29158516", "Stanovice"),
    ("CS STAV s.r.o.",                   "17461561", "Litvínovice"),

    # Noví klienti (bez existující úvěrové historie)
    ("EkoStav Holding s.r.o.",           "10200401", "Brno"),
    ("NovaTech Industries a.s.",         "10200502", "Ostrava"),
    ("Alfa Pharma Solutions s.r.o.",     "10200603", "Praha"),
    ("GreenBuild CZ a.s.",               "10200704", "Plzeň"),
    ("Baltic Logistics CZ s.r.o.",       "10200805", "Praha"),
    ("Future Software s.r.o.",           "10201310", "Praha"),
    ("Amber Construction s.r.o.",        "10201714", "Jihlava"),
]

# Fixní EW pro žadatele (simuluje rizikovost žádosti nových klientů)
_APPLICANT_EW_OVERRIDES: dict[str, str] = {
    "10200401": "GREEN",   # EkoStav — zdravé stavební
    "10200502": "GREEN",   # NovaTech — výrobní firma s dobrými metrikami
    "10200603": "GREEN",   # Alfa Pharma — pharma, nízké riziko
    "10200704": "GREEN",   # GreenBuild — zelená výstavba
    "10200805": "GREEN",   # Baltic Logistics — mezinárodní logistika
    "10201310": "AMBER",   # Future Software — nový player, bez histor.
    "10201714": "RED",     # Amber Construction — stavebnictví, DPD
}

_APPLICANT_CACHE: list[dict] | None = None


def _sector_for(name: str, ico: str) -> str:
    """Odvodí sektor z názvu firmy."""
    n = name.lower()
    if any(x in n for x in ["stav", "inž", "beton", "siln", "modul", "construct"]):
        return "Stavebnictví"
    if any(x in n for x in ["logist", "trans", "cargo", "přepr", "dopr", "chain", "modal"]):
        return "Logistika & Doprava"
    if any(x in n for x in ["energet", "solar", "wind", "tepeln", "elektro dis", "green", "biop"]):
        return "Energetika"
    if any(x in n for x in ["retail", "mart", "fashion", "homedeco", "techshop", "supermarket"]):
        return "Maloobchod"
    if any(x in n for x in ["farm", "bioph", "medtech", "lékárn", "clinlab", "health"]):
        return "Farmacie & Healthcare"
    if any(x in n for x in ["průmysl", "kovárn", "plastikárn", "cnc", "steelwork", "pneu", "elektronika výroba"]):
        return "Výroba & Průmysl"
    if any(x in n for x in ["softco", "datacloud", "cybersec", "ai platform", "erp system", "iot connect", "fintech"]):
        return "IT & Technologie"
    if any(x in n for x in ["potrav", "mlékárn", "pivovar", "cukro", "pekárn", "foodgroup"]):
        return "Potravinářství"
    if any(x in n for x in ["agro", "živočišn", "zeleninof", "biofarm"]):
        return "Zemědělství"
    if any(x in n for x in ["textil", "obuv", "konfekce"]):
        return "Textilní průmysl"
    if any(x in n for x in ["strojírn", "hydraul", "nástrojárn", "přesná", "robotic", "machinegroup"]):
        return "Strojírenství"
    if any(x in n for x in ["chemie", "laky", "plasty chemie", "hnojiv", "pharma chemie"]):
        return "Chemický průmysl"
    if any(x in n for x in ["autodíly", "karosérie", "autoservis", "fleet", "moto import"]):
        return "Autoprůmysl & Doprava"
    if any(x in n for x in ["realit", "nemovit", "industrial park", "office solutions", "bytový"]):
        return "Realitní sektor"
    if any(x in n for x in ["teleconnect", "broadband", "fibrenet", "datatel", "satelit"]):
        return "Telekomunikace"
    return "Výroba & Průmysl"


def _gen_financials(ew_level: str, rng: random.Random) -> dict:
    """
    Generuje finančně konzistentní data s pravdopondbnými metrikami.
    Zajišťuje správné WCR chování (GREEN=PASS, AMBER=1-2 breach, RED=2+ breach).
    DETERMINISTIC seed → reprodukovatelné výsledky.
    """
    # Revenue
    rev_ranges = {
        "GREEN": (300_000_000, 5_000_000_000),
        "AMBER": (150_000_000, 2_000_000_000),
        "RED":   (80_000_000,  800_000_000),
    }
    rev_lo, rev_hi = rev_ranges[ew_level]
    revenue = rng.randint(int(rev_lo / 1_000_000), int(rev_hi / 1_000_000)) * 1_000_000

    # EBITDA margin
    margin_range = {
        "GREEN": (0.10, 0.22),
        "AMBER": (0.06, 0.12),
        "RED":   (0.03, 0.08),
    }
    lo, hi = margin_range[ew_level]
    ebitda = revenue * rng.uniform(lo, hi)

    # Leverage → net_debt  (cílíme pod/nad 5.0)
    if ew_level == "GREEN":
        lev_target = rng.uniform(1.5, 4.6)   # vždy ≤ 5.0 → PASS
    elif ew_level == "AMBER":
        lev_target = rng.uniform(3.5, 5.4)   # může být mírně nad limitem
    else:
        lev_target = rng.uniform(5.0, 7.5)   # pravidelně překračuje
    net_debt = ebitda * lev_target

    # Total assets
    total_assets = net_debt * rng.uniform(1.8, 3.5)

    # Current ratio (cílíme nad/pod 1.2)
    cr_targets = {
        "GREEN": rng.uniform(1.3, 2.8),
        "AMBER": rng.uniform(0.85, 1.45),
        "RED":   rng.uniform(0.55, 1.15),
    }
    cr = cr_targets[ew_level]
    current_liab = revenue * rng.uniform(0.08, 0.22)
    current_assets = current_liab * cr

    # DSCR (cílíme nad/pod 1.2)
    dscr_targets = {
        "GREEN": rng.uniform(1.3, 2.6),
        "AMBER": rng.uniform(0.90, 1.40),
        "RED":   rng.uniform(0.65, 1.10),
    }
    dscr_target = dscr_targets[ew_level]
    debt_service = ebitda / max(dscr_target, 0.01)
    operating_cashflow = debt_service * dscr_target

    return {
        "revenue":             round(revenue, -3),
        "ebitda":              round(ebitda, -3),
        "net_debt":            round(net_debt, -3),
        "total_assets":        round(total_assets, -3),
        "current_assets":      round(current_assets, -3),
        "current_liabilities": round(current_liab, -3),
        "debt_service":        round(debt_service, -3),
        "operating_cashflow":  round(operating_cashflow, -3),
    }


def _gen_client(name: str, ico: str, city: str) -> dict:
    """Generuje plný záznam klienta z deterministic seed = ico."""
    rng = random.Random(int(ico.lstrip("0") or "1"))
    sector = _sector_for(name, ico)

    # EW level
    if ico in _EW_OVERRIDES:
        ew = _EW_OVERRIDES[ico]
    else:
        r = rng.random()
        ew = "GREEN" if r < 0.52 else ("AMBER" if r < 0.78 else "RED")
        # Textilní průmysl vždy rizikovější
        if sector == "Textilní průmysl" and ew == "GREEN":
            ew = "AMBER"

    fd = _gen_financials(ew, rng)

    # Credit limit a využití
    if ew == "GREEN":
        limit_mult = rng.uniform(0.18, 0.45)
        util_pct = rng.uniform(0.28, 0.76)
    elif ew == "AMBER":
        limit_mult = rng.uniform(0.14, 0.32)
        util_pct = rng.uniform(0.63, 0.91)
    else:
        limit_mult = rng.uniform(0.10, 0.22)
        util_pct = rng.uniform(0.85, 0.97)

    credit_limit = max(round(fd["revenue"] * limit_mult / 1_000_000) * 1_000_000, 50_000_000)
    current_util = round(credit_limit * util_pct / 100_000) * 100_000

    # DPD
    if ew == "GREEN":
        dpd = rng.choice([0, 0, 0, 0, 0, 3, 5])
    elif ew == "AMBER":
        dpd = rng.choice([0, 5, 8, 10, 12, 15, 18])
    else:
        dpd = rng.choice([15, 20, 25, 30, 40, 45, 60])

    # Covenant status
    if ew == "RED" and rng.random() < 0.55:
        cov_status = "BREACH"
    elif ew == "AMBER" and rng.random() < 0.35:
        cov_status = "WARNING"
    else:
        cov_status = "OK"

    # Last memo date
    months_ago = rng.randint(1, 20)
    memo_date = (date(2026, 4, 17) - timedelta(days=months_ago * 30)).strftime("%Y-%m-%d")

    # Data sources
    sources: dict = {
        "cbs_2024":   "CBS finanční výkazy FY2024",
        "cribis_q3":  "CRIBIS report Q3/2025",
        "helios_memos": "Historické memo v Helios (2022-2025)",
    }

    return {
        "ico":                 ico,
        "company_name":        name,
        "sector":              sector,
        "city":                city,
        "ew_alert_level":      ew,
        "covenant_status":     cov_status,
        "credit_limit":        credit_limit,
        "current_utilisation": current_util,
        "dpd_current":         dpd,
        "financial_data":      fd,
        "last_memo_date":      memo_date,
        "portfolio_status":    "ACTIVE",
        "data_sources":        sources,
    }


# ── Lazy-loaded portfolio cache ────────────────────────────────────────────────
_PORTFOLIO_CACHE: Optional[list[dict]] = None


def _get_raw_portfolio() -> list[dict]:
    """Vrátí nebo sestaví raw portfolio (bez vypočtených metrik)."""
    global _PORTFOLIO_CACHE
    if _PORTFOLIO_CACHE is None:
        _PORTFOLIO_CACHE = [_gen_client(n, ico, city) for n, ico, city in _COMPANY_DEFS]
    return _PORTFOLIO_CACHE


# ── Public API ─────────────────────────────────────────────────────────────────

# DETERMINISTIC
def get_portfolio() -> list[dict]:
    """Vrátí kompletní portfolio (~89 klientů) s vypočtenými metrikami."""
    result = []
    for client in _get_raw_portfolio():
        enriched = dict(client)
        enriched["metrics"] = _compute_metrics(client)
        enriched["wcr_breaches"] = _compute_breaches(client)
        result.append(enriched)
    return result


# DETERMINISTIC
def get_client(ico: str) -> Optional[dict]:
    """
    Vrátí klienta portfolia podle IČO s vypočtenými metrikami.
    Prohledává POUZE portfolio — NE žadatele.
    Returns None pokud IČO nenalezeno.
    """
    for client in _get_raw_portfolio():
        if client["ico"] == ico:
            enriched = dict(client)
            enriched["metrics"] = _compute_metrics(client)
            enriched["wcr_breaches"] = _compute_breaches(client)
            return enriched
    log.warning(f"[MockData] Klient IČO={ico} nenalezen v portfoliu")
    return None


def _gen_applicant(name: str, ico: str, city: str) -> dict:
    """
    Generuje záznam žadatele — firma žádá o úvěr od Horizon Bank.
    Někteří žadatelé jsou naši stávající klienti (načtou se CSV data),
    jiní jsou zcela noví (synthetic).
    """
    rng = random.Random(int(ico.lstrip("0") or "1") + 999)
    sector = _sector_for(name, ico)
    
    # Připojíme CSV data hned na začátku
    csv_data = _get_csv_data()
    is_client = ico in csv_data["companies"]

    if is_client:
        ch = csv_data["credit_history"].get(ico, {})
        tx = csv_data["transactions"].get(ico, {})
        has_breach = ch.get("has_breach", False)
        real_dpd = ch.get("current_dpd", 0)
        
        # Dynamické EW podle reálných dat z CSV
        if has_breach or real_dpd > 30:
            ew = "RED"
        elif real_dpd > 0 or ch.get("has_restructuring"):
            ew = "AMBER"
        else:
            # Trochu náhody aby nebyli všichni zelení
            r = rng.random()
            if r < 0.25:
                ew = "AMBER"
            elif r < 0.05:
                ew = "RED"
            else:
                ew = "GREEN"
    else:
        ew = _APPLICANT_EW_OVERRIDES.get(ico, "GREEN")
        ch = {}
        tx = {}

    fd = _gen_financials(ew, rng)

    # Žadatelé obvykle žádají o menší první úvěr nebo navýšení
    if ew == "GREEN":
        limit_mult = rng.uniform(0.10, 0.25)
    elif ew == "AMBER":
        limit_mult = rng.uniform(0.08, 0.18)
    else:
        limit_mult = rng.uniform(0.05, 0.12)

    # Požadovaný (nově schvalovaný) limit
    requested_limit = max(round(fd["revenue"] * limit_mult / 1_000_000) * 1_000_000, 30_000_000)

    if is_client:
        current_util = ch.get("total_outstanding", 0)
        # Celkový schvalovaný limit = Historický limit klienta u banky + Nově požadovaná částka
        existing_limit = ch.get("total_limit", 0)
        requested_limit = requested_limit + existing_limit
        
        dpd = real_dpd
        cov_status = "WARNING" if has_breach else "OK"
    else:
        current_util = 0
        dpd = 0 if ew != "RED" else rng.choice([0, 5, 10, 15])
        cov_status = "N/A"

    # Žadatelé přinášejí dokumenty z externích zdrojů
    sources = {
        "justice_cz":   f"Výpis z OR Justice.cz — {name}",
        "ares_api":     "ARES API — základní registrační data",
        "cribis_q3":    "CRIBIS report Q3/2025",
        "audit_report": f"Auditovaná účetní závěrka FY2024 — {name}",
    }

    return {
        "ico":                 ico,
        "company_name":        name,
        "sector":              sector,
        "city":                city,
        "ew_alert_level":      ew,
        "covenant_status":     cov_status,
        "credit_limit":        requested_limit,
        "current_utilisation": current_util,
        "dpd_current":         dpd,
        "financial_data":      fd,
        "last_memo_date":      "2023-11-15" if is_client else None,  # stávající má historii
        "portfolio_status":    "ŽADATEL",        
        "data_sources":        sources,
        "is_existing_client":  is_client,
        "csv_credit_history":  ch,
        "csv_transactions":    tx,
    }


def _get_raw_applicants() -> list[dict]:
    """Vrátí nebo sestaví raw seznam žadatelů (bez vypočtených metrik)."""
    global _APPLICANT_CACHE
    if _APPLICANT_CACHE is None:
        _APPLICANT_CACHE = [_gen_applicant(n, ico, city) for n, ico, city in _APPLICANT_DEFS]
    return _APPLICANT_CACHE


# DETERMINISTIC
def get_applicants() -> list[dict]:
    """
    Vrátí 17 žadatelů o úvěr s vypočtenými metrikami.
    Žadatelé nejsou v portfoliu — zobrazují se pouze na Credit Memo stránce.
    """
    result = []
    for a in _get_raw_applicants():
        enriched = dict(a)
        enriched["metrics"]      = _compute_metrics(a)
        enriched["wcr_breaches"] = _compute_breaches(a)
        result.append(enriched)
    return result


# DETERMINISTIC
def get_applicant(ico: str) -> Optional[dict]:
    """
    Vrátí žadatele podle IČO. Prohledává POUZE žadatele (ne portfolio).
    Je voláno z get_mock_agent_result() pro Credit Memo generování.
    """
    for a in _get_raw_applicants():
        if a["ico"] == ico:
            enriched = dict(a)
            enriched["metrics"]      = _compute_metrics(a)
            enriched["wcr_breaches"] = _compute_breaches(a)
            return enriched
    return None


# DETERMINISTIC
def get_mock_agent_result(ico: str) -> dict:
    """
    Vrátí simulovaný výsledek pipeline pro demo mode.
    Obsahuje plný audit_trail s mock prompt_hash hodnotami.
    Credit Memo je generováno deterministicky z finančních dat.
    Hledá nejdříve v žadatelích, pak v portfoliu.
    """
    # Nejdříve hledáme v žadatelích (Credit Memo je primárně pro ně)
    client = get_applicant(ico)
    if client is None:
        # Fallback: i z portfolia lze vygenerovat memo (Human Review apod.)
        client = get_client(ico)
    if client is None:
        return {"error": f"Klient/žadatel IČO={ico} nenalezen v demo datech"}

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

    # Citation coverage — pro RED klienty mírně nižší (ale stále nad 90%)
    citation_cov = 0.94 if client["ew_alert_level"] == "GREEN" else 0.91

    return {
        "ico":               ico,
        "request_id":        f"DEMO-{ico[:4]}-{_short_hash(ico)}",
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "company_name":      client["company_name"],
        "status":            "awaiting_human",
        "draft_memo":        memo,
        "citation_coverage": citation_cov,
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
            "ico":                 ico,
            "company_name":        client["company_name"],
            "sector":              client.get("sector", ""),
            "city":                client.get("city", ""),
            "financial_data":      client["financial_data"],
            "historical_memos":    [f"Memo {client.get('last_memo_date')} — viz Helios"] if client.get('last_memo_date') else [],
            "credit_limit":        client["credit_limit"],
            "current_utilisation": client["current_utilisation"],
            "portfolio_status":    client["portfolio_status"],
            "data_sources":        client["data_sources"],
            "cribis_data":         _mock_cribis(ico),
            "is_existing_client":  client.get("is_existing_client", False),
            "csv_credit_history":  client.get("csv_credit_history", {}),
            "csv_transactions":    client.get("csv_transactions", {}),
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

    ebitda       = fd["ebitda"]       or 1.0
    debt_service = fd["debt_service"] or 1.0
    current_liab = fd["current_liabilities"] or 1.0
    credit_lim_s = credit_limit or 1.0

    leverage_ratio  = fd["net_debt"] / ebitda                      # DETERMINISTIC
    dscr            = fd["operating_cashflow"] / debt_service       # DETERMINISTIC
    current_ratio   = fd["current_assets"] / current_liab          # DETERMINISTIC
    utilisation_pct = (current_util / credit_lim_s) * 100.0        # DETERMINISTIC

    return {
        "leverage_ratio":      round(leverage_ratio, 2),
        "dscr":                round(dscr, 2),
        "current_ratio":       round(current_ratio, 2),
        "utilisation_pct":     round(utilisation_pct, 1),
        # Raw inputs (pro UI a audit)
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
    """
    Generuje Credit Memo s [CITATION:] tagy.
    Pokrývá všechny WCR ukazatele s přesnými hodnotami.
    """
    if metrics is None:
        metrics = _compute_metrics(client)
    breaches = _compute_breaches(client)

    name     = client["company_name"]
    ico      = client["ico"]
    city     = client.get("city", "ČR")
    sector   = client.get("sector", "")
    limit_m  = client["credit_limit"] / 1_000_000
    util_m   = client["current_utilisation"] / 1_000_000
    revenue_m = client["financial_data"]["revenue"] / 1_000_000
    ebitda_m  = client["financial_data"]["ebitda"] / 1_000_000
    ebitda_margin = ebitda_m / max(revenue_m, 0.001) * 100

    sources = client.get("data_sources", {})
    src_keys = list(sources.keys())
    src1 = src_keys[0] if src_keys else "cbs_2024"
    src2 = src_keys[1] if len(src_keys) > 1 else src1
    src3 = src_keys[2] if len(src_keys) > 2 else src2

    ew = client["ew_alert_level"]
    ew_note = {
        "GREEN": "bez výrazných varovných signálů — klient v pořádku",
        "AMBER": "mírné varovné signály — doporučen zvýšený monitoring",
        "RED":   "kritické varovné signály — eskalace nutná",
    }.get(ew, "")

    recommendation = (
        "**SCHVÁLIT** — klient splňuje všechna WCR kritéria."
        if not breaches else
        f"**PODMÍNEČNĚ SCHVÁLIT** — {len(breaches)} WCR porušení vyžaduje pozornost. "
        if ew == "AMBER" else
        f"**PŘEDLOŽIT K RISK COMMITTEE** — {len(breaches)} WCR porušení, EW úroveň RED."
    )

    dpd = client["dpd_current"]
    cov = client.get("covenant_status", "OK")

    # WCR tabulka
    wcr_rows = [
        ("Leverage Ratio (Net Debt/EBITDA)",
         f"{metrics['leverage_ratio']:.2f}x", "≤ 5.0x",
         "✅" if metrics['leverage_ratio'] <= 5.0 else "❌"),
        ("DSCR",
         f"{metrics['dscr']:.2f}", "≥ 1.2",
         "✅" if metrics['dscr'] >= 1.2 else "❌"),
        ("Current Ratio",
         f"{metrics['current_ratio']:.2f}", "≥ 1.2",
         "✅" if metrics['current_ratio'] >= 1.2 else "❌"),
        ("Využití limitu",
         f"{metrics['utilisation_pct']:.1f} %", "≤ 85 %",
         "✅" if metrics['utilisation_pct'] <= 85 else "❌"),
        ("DPD",
         f"{dpd} dní", "≤ 30 dní",
         "✅" if dpd <= 30 else "❌"),
    ]
    wcr_table = "\n".join(
        f"| {ukazatel} | {hodnota} [CITATION:{src1}] | {limit} | {status} |"
        for ukazatel, hodnota, limit, status in wcr_rows
    )

    breach_section = ""
    if breaches:
        breach_section = "\n### 3.3 WCR Porušení\n\n"
        for b in breaches:
            breach_section += f"- ❌ {b} [CITATION:{src1}]\n"

    return f"""# Credit Memo — {name} ({ico})
**Datum:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}  |  **Stupeň důvěrnosti:** INTERNÍ  |  **Generováno:** GenAI pro underwriting · Horizon Bank

---

## 1. Executive Summary

Společnost {name} (IČO: {ico}) [CITATION:{src1}] působí v sektoru **{sector}** se sídlem v {city}.
Klient představuje v portfoliu Horizon Bank potenciál s požadovaným limitním rámcem **{limit_m:.0f} M CZK** [CITATION:{src1}].

Early Warning úroveň klienta: **{ew}** — {ew_note} [CITATION:{src2}].
Covenant status: **{cov}** [CITATION:{src1}].

**Doporučení:** {recommendation}

## 2. Informace o společnosti

- **Název:** {name}
- **IČO:** {ico} [CITATION:{src1}]
- **Sektor:** {sector}
- **Sídlo:** {city}
- **Status portfolia:** {client['portfolio_status']} [CITATION:{src1}]

## 3. Finanční analýza

### 3.1 WCR — Přehled limitů

| Ukazatel | Hodnota | Limit WCR | Status |
|----------|---------|-----------|--------|
{wcr_table}
{breach_section}
### 3.2 Výnosnost

- **Roční obrat:** {revenue_m:.0f} M CZK [CITATION:{src1}]
- **EBITDA:** {ebitda_m:.0f} M CZK [CITATION:{src1}]
- **EBITDA marže:** {ebitda_margin:.1f} % [CITATION:{src1}]
- **Net Debt:** {client['financial_data']['net_debt']/1_000_000:.0f} M CZK [CITATION:{src1}]
- **Operating Cash Flow:** {client['financial_data']['operating_cashflow']/1_000_000:.0f} M CZK [CITATION:{src1}]

## 4. Dodatečné informace

- **DPD (Days Past Due):** {dpd} dní [CITATION:{src1}]
- **Covenant status:** {cov} [CITATION:{src1}]

## 5. Doporučení underwritera

Na základě deterministicky vypočtených metrik [CITATION:{src1}]:

{recommendation}

{'**Podmínky schválení:**' if breaches else '**Klient splňuje všechna WCR kritéria — standardní postup.**'}
{chr(10).join(f'- Monitorovat: {b}' for b in breaches) if breaches else ''}

---
*Generováno: GenAI pro underwriting · Horizon Bank*
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
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ico = client["ico"]

    def ts(offset_s: int = 0) -> str:
        return (now + timedelta(seconds=offset_s)).isoformat()

    return [
        {
            "timestamp":      ts(0),
            "node":           "DataExtractorAgent",
            "action":         "extraction_started",
            "result":         "success",
            "prompt_hash":    _short_hash(f"extractor_{ico}").lower(),
            "prompt_version": "2.3",
            "tokens_used":    812 + (int(ico) % 200),
            "metadata":       {"sources_count": len(client["data_sources"]), "ico": ico},
        },
        {
            "timestamp":      ts(3),
            "node":           "ExtractionValidator",
            "action":         "validation",
            "result":         "passed",
            "prompt_hash":    None,
            "prompt_version": None,
            "tokens_used":    None,
            "metadata":       {"confidence_score": 0.93, "fields_validated": 7},
        },
        {
            "timestamp":      ts(5),
            "node":           "ContextBuilder",
            "action":         "context_built",
            "result":         "success",
            "prompt_hash":    None,
            "prompt_version": None,
            "tokens_used":    None,
            "metadata":       {"sources_count": len(client["data_sources"])},
        },
        {
            "timestamp":      ts(7),
            "node":           "CreditAnalysisService",
            "action":         "metrics_computed",
            "result":         f"leverage={metrics['leverage_ratio']} dscr={metrics['dscr']}",
            "prompt_hash":    None,
            "prompt_version": None,
            "tokens_used":    None,
            "metadata":       {"wcr_breaches": len(breaches)},
        },
        {
            "timestamp":      ts(12),
            "node":           "MemoPreparationAgent",
            "action":         "memo_drafted",
            "result":         "success",
            "prompt_hash":    _short_hash(f"maker_{ico}").lower(),
            "prompt_version": "3.2",
            "tokens_used":    1180 + (int(ico) % 300),
            "metadata":       {"iteration": 1, "memo_length": len(memo)},
        },
        {
            "timestamp":      ts(18),
            "node":           "QualityControlChecker",
            "action":         "quality_check",
            "result":         "pass",
            "prompt_hash":    _short_hash(f"checker_{ico}").lower(),
            "prompt_version": "2.0",
            "tokens_used":    598 + (int(ico) % 150),
            "metadata":       {
                "citation_coverage": 0.94 if client["ew_alert_level"] == "GREEN" else 0.91,
                "hallucinations": 0,
            },
        },
        {
            "timestamp":      ts(20),
            "node":           "PolicyRulesEngine",
            "action":         "wcr_check",
            "result":         "passed" if not breaches else f"{len(breaches)}_breaches",
            "prompt_hash":    None,
            "prompt_version": None,
            "tokens_used":    None,
            "metadata":       {"breaches": breaches},
        },
        {
            "timestamp":      ts(21),
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
    client = get_client(ico)
    is_red = client and client.get("ew_alert_level") == "RED"
    base_turnover = (
        client["financial_data"]["revenue"] / 12
        if client
        else 8_500_000.0
    )
    trend = 0.98 if is_red else 1.01
    rng = random.Random(int(ico.lstrip("0") or "1") + 100)
    months = []
    now = datetime.now(timezone.utc)
    for i in range(12):
        month = (now - timedelta(days=30 * i)).strftime("%Y-%m")
        turnover = base_turnover * (trend ** i) * rng.uniform(0.92, 1.08)
        months.append({
            "year_month":        month,
            "credit_turnover":   round(turnover, 0),
            "debit_turnover":    round(turnover * 0.85, 0),
            "min_balance":       round(turnover * 0.05, 0),
            "avg_balance":       round(turnover * 0.12, 0),
            "overdraft_days":    0 if not is_red else rng.randint(0, 8),
            "overdraft_depth":   0,
            "tax_payment_made":  "true",
            "tax_delay_days":    0,
            "payroll_amount":    round(turnover * 0.18, 0),
            "payroll_employees": rng.randint(30, 500),
            "deposit_balance":   round(turnover * 0.08, 0),
            "savings_balance":   round(turnover * 0.03, 0),
        })
    return months


def _mock_cribis(ico: str) -> dict | None:
    """Mock CRIBIS data pro demo mode — silver_data_cribis_v3."""
    client = get_applicant(ico) or get_client(ico)
    if not client:
        return None

    fd = client.get("financial_data", {})
    ebitda       = float(fd.get("ebitda", 0) or 0)
    revenue      = float(fd.get("revenue", 0) or 0)
    net_debt     = float(fd.get("net_debt", 0) or 0)
    curr_assets  = float(fd.get("current_assets", 0) or 0)
    curr_liab    = float(fd.get("current_liabilities", 0) or 0)
    total_assets = float(fd.get("total_assets", 0) or 0)

    bank_lt      = round(net_debt * 0.65 + ebitda * 0.1, 0) if net_debt else 0
    bank_st      = round(net_debt * 0.35 - ebitda * 0.1, 0) if net_debt else 0
    cash         = max(0.0, round(bank_st + bank_lt - net_debt, 0))
    interest_exp = round(net_debt * 0.045, 0) if net_debt else 0
    total_debt   = bank_st + bank_lt
    fixed_assets = max(0.0, total_assets - curr_assets)
    inventories  = round(curr_assets * 0.30, 0)
    depreciation = round(ebitda * 0.15, 0)
    income_tax   = round(ebitda * 0.55 * 0.19, 0)
    equity       = max(0.0, total_assets - total_debt)
    leverage     = round(net_debt / ebitda, 3) if ebitda else None
    current_r    = round(curr_assets / curr_liab, 3) if curr_liab else None
    ew           = client.get("ew_alert_level", "GREEN")

    return {
        "ic":                    ico,
        "nazev_subjektu":        client.get("company_name", ""),
        "revenue":               revenue,
        "ebitda":                ebitda,
        "ebit":                  round(ebitda * 0.85, 0),
        "net_income":            round(ebitda * 0.55, 0),
        "current_ratio":         current_r,
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
        "leverage_ratio":        leverage,
        "dscr":                  None,
        "dscr_note":             "Počítáno v calculator.py (EBITDA-CAPEX-daň / DS)",
        "net_working_capital_k": round((curr_assets - curr_liab) / 1000, 0),
        "yoy_revenue_change_pct": -5.0 if ew == "RED" else 3.5,
        "yoy_ebitda_change_pct":  -8.0 if ew == "RED" else 2.0,
        "is_suspicious":          False,
        "missing_key_kpi":        False,
        "periods_count":          4,
    }


def _mock_cribis_prev(ico: str) -> dict | None:
    """Mock CRIBIS data za předchozí účetní období (pro CAPEX výpočet)."""
    client = get_applicant(ico) or get_client(ico)
    if not client:
        return None

    fd = client.get("financial_data", {})
    total_assets = float(fd.get("total_assets", 0) or 0)
    curr_assets  = float(fd.get("current_assets", 0) or 0)
    fixed_assets = max(0.0, total_assets - curr_assets)

    return {
        "ic":           ico,
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
    n = len(portfolio)
    assert n >= 80, f"Očekáváno ≥80 klientů, ale {n}"

    client = get_client("27082440")
    assert client is not None
    assert client["company_name"] == "Stavební holding Praha a.s."
    assert client["ew_alert_level"] == "GREEN"

    client_red = get_client("49551895")
    assert client_red is not None
    assert client_red["ew_alert_level"] == "RED"

    result = get_mock_agent_result("49551895")
    assert result.get("wcr_passed") is False
    assert len(result["wcr_report"]["breaches"]) > 0
    assert "[CITATION:" in result["draft_memo"]

    result_green = get_mock_agent_result("27082440")
    assert "[CITATION:" in result_green["draft_memo"]

    # Zkontroluj rozložení EW levelů
    ew_counts = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for c in portfolio:
        ew_counts[c.get("ew_alert_level", "GREEN")] += 1

    print(f"OK — mock_data.py smoke test passed ({n} klientů)")
    print(f"  EW rozložení: GREEN={ew_counts['GREEN']} AMBER={ew_counts['AMBER']} RED={ew_counts['RED']}")
    for c in portfolio[:10]:
        breaches = c["wcr_breaches"]
        m = c["metrics"]
        print(
            f"  {c['ew_alert_level']:5s} {c['company_name'][:35]:35s} "
            f"lev={m['leverage_ratio']:.1f} dscr={m['dscr']:.2f} "
            f"util={m['utilisation_pct']:.0f}% dpd={c['dpd_current']} "
            f"→ {len(breaches)} breach"
        )
