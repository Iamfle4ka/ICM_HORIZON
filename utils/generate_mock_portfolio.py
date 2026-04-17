"""
Генератор 97 mock фирм для demo режима.
Запускать: python utils/generate_mock_portfolio.py > /tmp/portfolio_data.py
"""
import random
import json

random.seed(42)

SECTORS = [
    ("Stavebnictví",             "A1","A2","B1","B2"),
    ("Logistika & Doprava",      "A2","B1","B2","C1"),
    ("Energetika",               "A1","A2","B1","B2"),
    ("Maloobchod",               "B1","B2","B2","C1"),
    ("Farmacie & Healthcare",    "A1","A2","A2","B1"),
    ("Výroba & Průmysl",         "A2","B1","B1","B2"),
    ("IT & Technologie",         "A1","A2","B1","B2"),
    ("Potravinářství",           "A2","B1","B2","C1"),
    ("Zemědělství",              "B1","B2","B2","C1"),
    ("Textilní průmysl",         "B2","C1","C1","C2"),
    ("Strojírenství",            "A2","B1","B1","B2"),
    ("Chemický průmysl",         "A2","B1","B2","C1"),
    ("Autoprůmysl & Doprava",    "A2","B1","B2","C1"),
    ("Realitní sektor",          "B1","B2","B2","C1"),
    ("Telekomunikace",           "A1","A2","B1","B2"),
]

CITIES = [
    "Praha", "Brno", "Ostrava", "Plzeň", "Liberec",
    "Olomouc", "Zlín", "Hradec Králové", "České Budějovice",
    "Pardubice", "Ústí nad Labem", "Karlovy Vary", "Jihlava",
]

COMPANY_NAMES = [
    # Stavebnictví (8)
    ("Stavební holding Praha a.s.",    "27082440", "Praha"),
    ("Stavby Morava s.r.o.",           "28145633", "Brno"),
    ("Construkt CZ a.s.",              "25643789", "Ostrava"),
    ("Inženýrské stavby Plzeň s.r.o.", "47821036", "Plzeň"),
    ("Pozemní stavby Zlín a.s.",       "60123456", "Zlín"),
    ("Betonstav Jihlava s.r.o.",       "48905712", "Jihlava"),
    ("Silniční stavby ČR a.s.",        "35967841", "Praha"),
    ("Modular Build s.r.o.",           "72345618", "Hradec Králové"),
    # Logistika (7)
    ("Logistika Morava s.r.o.",        "45274649", "Brno"),
    ("TransCargo CZ a.s.",             "52187430", "Ostrava"),
    ("Expres Logistik s.r.o.",         "63812745", "Praha"),
    ("Rychlá Přeprava a.s.",           "41789023", "Plzeň"),
    ("Dopravní holding s.r.o.",        "38904512", "Liberec"),
    ("CoolChain CZ a.s.",              "74512389", "České Budějovice"),
    ("Intermodal Trans s.r.o.",        "56723091", "Pardubice"),
    # Energetika (7)
    ("Energetika Brno a.s.",           "00514152", "Brno"),
    ("Solar Power CZ s.r.o.",          "29817345", "Praha"),
    ("Wind Energy Morava a.s.",        "68234571", "Ostrava"),
    ("Tepelné sítě ČR s.r.o.",         "43129867", "Plzeň"),
    ("Elektro Distribuce a.s.",        "57890123", "Olomouc"),
    ("GreenEnergy s.r.o.",             "81234567", "Liberec"),
    ("Bioplynové stanice CZ a.s.",     "34567890", "Zlín"),
    # Maloobchod (6)
    ("Retail Group CZ s.r.o.",         "26467054", "Praha"),
    ("MegaMart a.s.",                  "53902817", "Brno"),
    ("Fashion Retail s.r.o.",          "37891245", "Ostrava"),
    ("HomeDeco CZ a.s.",               "61823904", "Plzeň"),
    ("TechShop s.r.o.",                "44918273", "Praha"),
    ("Supermarket Holding a.s.",       "79012345", "Olomouc"),
    # Farmacie (6)
    ("Farmaceutika Nord a.s.",         "63999714", "Ostrava"),
    ("BioPharm CZ s.r.o.",             "31847509", "Praha"),
    ("MedTech Solutions a.s.",         "75239018", "Brno"),
    ("Lékárna Plus s.r.o.",            "48701234", "Liberec"),
    ("ClinLab CZ a.s.",                "92345678", "Praha"),
    ("HealthCare Holding s.r.o.",      "55678901", "Hradec Králové"),
    # Výroba (7)
    ("Průmyslový holding CZ a.s.",     "22345678", "Ostrava"),
    ("Kovárna Plzeň s.r.o.",           "18923456", "Plzeň"),
    ("Plastikárna Morava a.s.",        "87654321", "Zlín"),
    ("CNC Výroba Brno s.r.o.",         "14567890", "Brno"),
    ("SteelWork CZ a.s.",              "68901234", "Ostrava"),
    ("Pneu Pro s.r.o.",                "33490125", "Praha"),
    ("Elektronika Výroba a.s.",        "50123789", "Pardubice"),
    # IT & Technologie (7)
    ("SoftCo Praha a.s.",              "91234567", "Praha"),
    ("DataCloud CZ s.r.o.",            "16789012", "Brno"),
    ("CyberSec Solutions a.s.",        "78901234", "Praha"),
    ("AI Platform s.r.o.",             "43218765", "Praha"),
    ("ERP Systems CZ a.s.",            "67890123", "Brno"),
    ("IoT Connect s.r.o.",             "25890134", "Ostrava"),
    ("Fintech Labs a.s.",              "84321098", "Praha"),
    # Potravinářství (6)
    ("Potravinářský závod CZ a.s.",    "19876543", "Olomouc"),
    ("Mlékárna Morava s.r.o.",         "56019283", "České Budějovice"),
    ("Pivovar Bohemia a.s.",           "32107654", "Plzeň"),
    ("Cukrovary CZ s.r.o.",            "71234509", "Pardubice"),
    ("Pekárny a Cukrárny a.s.",        "44321567", "Praha"),
    ("FoodGroup Holding s.r.o.",       "89012345", "Brno"),
    # Zemědělství (5)
    ("Agrohospodářství Čechy a.s.",    "23456789", "Jihlava"),
    ("Živočišná výroba CZ s.r.o.",     "67012345", "Olomouc"),
    ("Agro Morava a.s.",               "12345098", "Zlín"),
    ("Zeleninofarma s.r.o.",           "54329876", "Hradec Králové"),
    ("Biofarm CZ a.s.",                "98012345", "České Budějovice"),
    # Textilní (4 — rizikovější)
    ("Textil Liberec s.r.o.",          "49551895", "Liberec"),
    ("Obuv Morava a.s.",               "37812904", "Zlín"),
    ("Konfekce CZ s.r.o.",             "61023458", "Ústí nad Labem"),
    ("Textilní holding a.s.",          "28901237", "Liberec"),
    # Strojírenství (6)
    ("Strojírna Praha a.s.",           "45678901", "Praha"),
    ("Hydraulika Brno s.r.o.",         "73012456", "Brno"),
    ("Nástrojárna Ostrava a.s.",       "19234567", "Ostrava"),
    ("Přesná Mechanika s.r.o.",        "86012345", "Plzeň"),
    ("Robotic Systems CZ a.s.",        "31209876", "Praha"),
    ("MachineGroup s.r.o.",            "54012378", "Pardubice"),
    # Chemický průmysl (5)
    ("Chemie Skupnina CZ a.s.",        "20987654", "Ústí nad Labem"),
    ("Laky Barvy CZ s.r.o.",           "64012398", "Praha"),
    ("Plasty Chemie a.s.",             "47012389", "Ostrava"),
    ("Hnojiva Morava s.r.o.",          "83012478", "Olomouc"),
    ("Pharma Chemie CZ a.s.",          "36012789", "Brno"),
    # Autoprůmysl (5)
    ("AutoDíly CZ a.s.",               "59012456", "Praha"),
    ("Karosérie CZ s.r.o.",            "72012389", "Mladá Boleslav"),
    ("Autoservis Holding a.s.",        "41012789", "Brno"),
    ("Fleet Management s.r.o.",        "26012347", "Praha"),
    ("Moto Import CZ a.s.",            "88012367", "Ostrava"),
    # Realitní (5)
    ("Realitní Holding Praha a.s.",    "13012456", "Praha"),
    ("Komerční nemovitosti s.r.o.",    "77012349", "Brno"),
    ("Industrial Park CZ a.s.",        "58012367", "Ostrava"),
    ("Office Solutions s.r.o.",        "39012456", "Praha"),
    ("Bytový Fond CZ a.s.",            "93012456", "Plzeň"),
    # Telekomunikace (5)
    ("TeleConnect CZ a.s.",            "24012789", "Praha"),
    ("BroadBand Solutions s.r.o.",     "61012789", "Brno"),
    ("FibreNet CZ a.s.",               "48012567", "Ostrava"),
    ("DataTel s.r.o.",                 "85012456", "Praha"),
    ("Satelitní Sítě CZ a.s.",         "37012456", "Karlovy Vary"),
]

# Sektory pro každou firmu
SECTOR_MAP = {}
for name, ico, city in COMPANY_NAMES:
    # Determine sector from name patterns
    n = name.lower()
    if any(x in n for x in ["stav","inž","beton","siln","modul","construct"]):
        SECTOR_MAP[ico] = "Stavebnictví"
    elif any(x in n for x in ["logist","trans","cargo","přepr","dopr","chain","modal"]):
        SECTOR_MAP[ico] = "Logistika & Doprava"
    elif any(x in n for x in ["energet","solar","wind","tepeln","elektr","green","biop"]):
        SECTOR_MAP[ico] = "Energetika"
    elif any(x in n for x in ["retail","mart","fashion","home","shop","supermarket"]):
        SECTOR_MAP[ico] = "Maloobchod"
    elif any(x in n for x in ["farm","bioph","medtech","lékárn","clinlab","health"]):
        SECTOR_MAP[ico] = "Farmacie & Healthcare"
    elif any(x in n for x in ["průmysl","kovárn","plastik","cnc","steel","pneu","elektron"]):
        SECTOR_MAP[ico] = "Výroba & Průmysl"
    elif any(x in n for x in ["soft","data","cyber","ai ","erp","iot","fintech"]):
        SECTOR_MAP[ico] = "IT & Technologie"
    elif any(x in n for x in ["potrav","mlékárn","pivovar","cukro","pekárn","food"]):
        SECTOR_MAP[ico] = "Potravinářství"
    elif any(x in n for x in ["agro","živočišn","zeleninof","biofarm"]):
        SECTOR_MAP[ico] = "Zemědělství"
    elif any(x in n for x in ["textil","obuv","konfekce"]):
        SECTOR_MAP[ico] = "Textilní průmysl"
    elif any(x in n for x in ["strojírn","hydraul","nástrojárn","přesná","robotic","machine"]):
        SECTOR_MAP[ico] = "Strojírenství"
    elif any(x in n for x in ["chemie","laky","plasty","hnojiv","pharma chem"]):
        SECTOR_MAP[ico] = "Chemický průmysl"
    elif any(x in n for x in ["auto","karos","autoserv","fleet","moto"]):
        SECTOR_MAP[ico] = "Autoprůmysl & Doprava"
    elif any(x in n for x in ["realit","nemovit","industrial park","office","bytový"]):
        SECTOR_MAP[ico] = "Realitní sektor"
    elif any(x in n for x in ["telecon","broadband","fibre","datatel","satelit"]):
        SECTOR_MAP[ico] = "Telekomunikace"
    else:
        SECTOR_MAP[ico] = "Výroba & Průmysl"

# Risk profiles with WCR-meaningful numbers
def gen_financials(ew_level: str, sector: str, rng: random.Random) -> dict:
    """Generate financially consistent data."""
    # Revenue base by size
    rev_ranges = {
        "GREEN": (400_000_000, 5_000_000_000),
        "AMBER": (200_000_000, 2_000_000_000),
        "RED":   (100_000_000, 1_000_000_000),
    }
    rev_lo, rev_hi = rev_ranges[ew_level]
    revenue = rng.randint(int(rev_lo/1e6), int(rev_hi/1e6)) * 1_000_000

    # EBITDA margin by risk
    if ew_level == "GREEN":
        margin = rng.uniform(0.10, 0.22)
    elif ew_level == "AMBER":
        margin = rng.uniform(0.06, 0.12)
    else:
        margin = rng.uniform(0.03, 0.08)
    ebitda = revenue * margin

    # Net debt → leverage
    if ew_level == "GREEN":
        lev = rng.uniform(1.5, 4.6)  # safe side of 5.0
    elif ew_level == "AMBER":
        lev = rng.uniform(3.5, 5.2)
    else:
        lev = rng.uniform(4.8, 7.0)
    net_debt = ebitda * lev

    total_assets = net_debt * rng.uniform(1.8, 3.5)
    current_ratio_target = {
        "GREEN": rng.uniform(1.3, 2.5),
        "AMBER": rng.uniform(0.9, 1.4),
        "RED":   rng.uniform(0.6, 1.1),
    }[ew_level]
    current_liab = revenue * rng.uniform(0.10, 0.25)
    current_assets = current_liab * current_ratio_target

    # DSCR
    if ew_level == "GREEN":
        dscr_target = rng.uniform(1.25, 2.5)
    elif ew_level == "AMBER":
        dscr_target = rng.uniform(0.95, 1.35)
    else:
        dscr_target = rng.uniform(0.70, 1.10)
    debt_service = ebitda / dscr_target
    operating_cashflow = debt_service * dscr_target

    return {
        "revenue":             round(revenue, 0),
        "ebitda":              round(ebitda, 0),
        "net_debt":            round(net_debt, 0),
        "total_assets":        round(total_assets, 0),
        "current_assets":      round(current_assets, 0),
        "current_liabilities": round(current_liab, 0),
        "debt_service":        round(debt_service, 0),
        "operating_cashflow":  round(operating_cashflow, 0),
    }


def gen_client(name: str, ico: str, city: str) -> dict:
    rng = random.Random(int(ico) % 10**9)
    sector = SECTOR_MAP.get(ico, "Výroba & Průmysl")

    # Determine EW level
    # ~55% GREEN, 25% AMBER, 20% RED
    r = rng.random()
    if r < 0.55:
        ew = "GREEN"
    elif r < 0.80:
        ew = "AMBER"
    else:
        ew = "RED"

    # Override for original 6 to match docs
    overrides = {
        "27082440": "GREEN",
        "45274649": "RED",
        "00514152": "GREEN",
        "26467054": "AMBER",
        "63999714": "GREEN",
        "49551895": "RED",
    }
    ew = overrides.get(ico, ew)

    fd = gen_financials(ew, sector, rng)

    # Credit limit
    if ew == "GREEN":
        limit_mult = rng.uniform(0.2, 0.5)
        util_pct = rng.uniform(0.30, 0.78)
    elif ew == "AMBER":
        limit_mult = rng.uniform(0.15, 0.35)
        util_pct = rng.uniform(0.65, 0.92)
    else:
        limit_mult = rng.uniform(0.10, 0.25)
        util_pct = rng.uniform(0.82, 0.98)

    credit_limit = round(fd["revenue"] * limit_mult / 1e6) * 1_000_000
    credit_limit = max(credit_limit, 50_000_000)
    current_util = round(credit_limit * util_pct / 1e5) * 100_000

    dpd = 0
    if ew == "GREEN":
        dpd = rng.choice([0, 0, 0, 0, 5])
    elif ew == "AMBER":
        dpd = rng.choice([0, 5, 8, 12, 15])
    else:
        dpd = rng.choice([15, 20, 30, 40, 45, 60])

    cov_status = "OK"
    if ew == "RED" and rng.random() < 0.5:
        cov_status = "BREACH"
    elif ew == "AMBER" and rng.random() < 0.3:
        cov_status = "WARNING"

    # CRIBIS rating from leverage
    lev = fd["net_debt"] / max(fd["ebitda"], 1)
    dscr = fd["operating_cashflow"] / max(fd["debt_service"], 1)
    if lev <= 2.5 and dscr >= 1.8:
        rating = "A1"
    elif lev <= 3.5 and dscr >= 1.4:
        rating = "A2"
    elif lev <= 4.5 and dscr >= 1.2:
        rating = "B1"
    elif lev <= 5.0 and dscr >= 1.0:
        rating = "B2"
    elif lev <= 6.0:
        rating = "C1"
    else:
        rating = "C2"

    esg = round(rng.uniform(30, 85), 1)
    flood_risks = ["Velmi nízké", "Nízké", "Střední", "Vysoké"]
    flood_weights = [0.4, 0.35, 0.15, 0.10]
    flood = rng.choices(flood_risks, weights=flood_weights)[0]

    # Memo date
    months = rng.randint(1, 18)
    from datetime import date, timedelta
    memo_date = (date(2026, 4, 17) - timedelta(days=months*30)).strftime("%Y-%m-%d")

    sources = {
        "cbs_2024": "CBS finanční výkazy FY2024",
        "cribis_q3": "CRIBIS rating report Q3/2025",
        "helios_memos": f"Historické memo v Helios (2022-2025)",
    }
    if ew == "GREEN":
        sources["esg_report"] = "ESG Due Diligence Report 2025"
    if rng.random() < 0.5:
        sources["katastr"] = "Katastr nemovitostí ČR — výpis LV"

    katastr = None
    if "katastr" in sources:
        lv = str(rng.randint(100, 9999))
        parcel1 = f"{rng.randint(100,9999)}/{rng.randint(1,20)}"
        katastr = {
            "parcely": [parcel1],
            "LV": lv,
            "katastralni_uzemi": f"{city} — část",
        }

    return {
        "ico":                 ico,
        "company_name":        name,
        "sector":              sector,
        "city":                city,
        "ew_alert_level":      ew,
        "covenant_status":     cov_status,
        "cribis_rating":       rating,
        "esg_score":           esg,
        "credit_limit":        credit_limit,
        "current_utilisation": current_util,
        "dpd_current":         dpd,
        "financial_data":      fd,
        "katastr_data":        katastr,
        "flood_risk":          flood,
        "last_memo_date":      memo_date,
        "portfolio_status":    "ACTIVE",
        "data_sources":        sources,
    }


if __name__ == "__main__":
    clients = [gen_client(n, ico, city) for n, ico, city in COMPANY_NAMES]
    print(f"# Generated {len(clients)} clients")
    print(json.dumps(clients, ensure_ascii=False, indent=2, default=str))
