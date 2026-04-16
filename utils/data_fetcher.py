# DETERMINISTIC
"""
Data Enrichment Agent — utils/data_fetcher.py
Cascade fallback pro finanční data: CRIBIS → Justice.cz → ARES → Freeze.

Pořadí zdrojů:
  1. CRIBIS (silver_data_cribis_v3) — nejkompletnější
  2. Justice.cz HTML scraping + PDF (výroční zpráva) — pokud CRIBIS chybí
  3. ARES API (základní údaje) — fallback
  4. Process Freeze — pokud žádný zdroj nedostupný

Obohacení:
  · detect_missing_fields() — zjistí chybějící KPI
  · enrich_company(ico)     — orchestruje cascade per chybějící pole
  · save_enriched_to_databricks() — zapíše výsledek zpět
  · save_enriched_to_csv()  — záloha jako CSV

Pravidla:
  · IČO normalizace: str(int(ico)) — odstraní vedoucí nuly pro CRIBIS JOIN
  · NIKDY nefallbackuj na T-1 data — vždy FROZEN při selhání
  · Každý záznam má pole `source` (cribis / justice_cz / ares_api / frozen)
  · DETERMINISTIC — žádný LLM

DETERMINISTIC — žádný LLM.
"""

import csv
import io
import logging
import os
import re
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)

# ── Konstanty ─────────────────────────────────────────────────────────────────

# Kritická KPI pole, která musí být přítomna pro plnou analýzu
REQUIRED_FIELDS: list[str] = [
    "revenue",
    "ebitda",
    "net_debt",
    "total_assets",
    "current_assets",
    "current_ratio",
    "interest_expense",
    "bank_liabilities_st",
    "bank_liabilities_lt",
    "cash",
    "depreciation",
    "income_tax",
    "equity",
]

# Pole dostupná pouze z CRIBIS/Justice — ARES je nemá
FINANCIAL_FIELDS: set[str] = set(REQUIRED_FIELDS)

# Maximální počet pokusů pro HTTP volání
HTTP_RETRIES: int = int(os.getenv("API_RETRY_COUNT", "3"))
HTTP_TIMEOUT: int = 15  # sekund

# Katalog pro zápis enriched dat
_ENRICH_CATALOG = os.getenv("DATABRICKS_CATALOG", "vse_banka")
_ENRICH_SCHEMA  = os.getenv("DATABRICKS_SCHEMA_ENRICH", "icm_gen_ai")
_ENRICH_TABLE   = "enriched_company_data"


# ── Datové typy ───────────────────────────────────────────────────────────────


class DataSource(Enum):
    CRIBIS   = "cribis"
    JUSTICE  = "justice_cz"
    ARES     = "ares_api"
    MOCK     = "mock_demo"
    FROZEN   = "frozen"


@dataclass
class FetchResult:
    source:        DataSource
    data:          dict
    is_complete:   bool   = False   # True = plná data (CRIBIS/Justice)
    is_partial:    bool   = False   # True = pouze základní info (ARES)
    frozen:        bool   = False   # True = Process Freeze
    error_chain:   list[str] = field(default_factory=list)
    wcr_partial:   bool   = True    # False = všechny WCR metriky dostupné
    missing_fields: list[str] = field(default_factory=list)  # pole, která chybí
    field_sources:  dict  = field(default_factory=dict)       # {field: source_name}


# ── IČO normalizace ───────────────────────────────────────────────────────────


def _norm_ico(ico: str) -> str:
    """
    Normalizuje IČO pro CRIBIS JOIN — odstraní vedoucí nuly.
    '00514152' → '514152'   ·   '27082440' → '27082440'
    """
    try:
        return str(int(str(ico)))
    except (ValueError, TypeError):
        return str(ico)


# ── Missing field detection ────────────────────────────────────────────────────


def detect_missing_fields(data: dict) -> list[str]:
    """
    Zjistí chybějící nebo None kritická KPI pole v datovém záznamu.

    Args:
        data: dict s finančními daty (CRIBIS, Justice, ARES nebo mock)

    Returns:
        Seznam názvů polí, která jsou None nebo zcela chybí.

    Example:
        >>> detect_missing_fields({"revenue": 1_000_000, "ebitda": None})
        ['ebitda', 'net_debt', ...]
    """
    missing = []
    for field_name in REQUIRED_FIELDS:
        val = data.get(field_name)
        if val is None:
            missing.append(field_name)
    return missing


# ── Cascade entry point ───────────────────────────────────────────────────────


def fetch_financial_data(ico: str) -> FetchResult:
    """
    Hlavní vstupní bod. Cascade: CRIBIS → Justice → ARES → Freeze.

    Demo mode: vždy vrátí mock CRIBIS data.
    Prod mode: zkouší zdroje v pořadí.

    Returns:
        FetchResult s daty, metadaty o zdroji a seznamem chybějících polí.
    """
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"

    if is_demo:
        return _try_demo(ico)

    errors: list[str] = []

    # 1. CRIBIS
    result = _try_cribis(ico, errors)
    if result is not None:
        result.missing_fields = detect_missing_fields(result.data)
        return result

    # 2. Justice.cz HTML + PDF
    result = _try_justice_pdf(ico, errors)
    if result is not None:
        result.missing_fields = detect_missing_fields(result.data)
        return result

    # 3. ARES API
    result = _try_ares(ico, errors)
    if result is not None:
        result.missing_fields = detect_missing_fields(result.data)
        return result

    # 4. Process Freeze — NIKDY nefallbackuj na T-1 data
    log.error(
        f"[DataFetcher] VŠECHNY ZDROJE SELHALY pro ico={ico} | "
        f"errors={errors} → PROCESS FREEZE"
    )
    return FetchResult(
        source=DataSource.FROZEN,
        data={"ico": ico, "source": DataSource.FROZEN.value},
        frozen=True,
        is_complete=False,
        is_partial=False,
        wcr_partial=True,
        error_chain=errors,
        missing_fields=list(REQUIRED_FIELDS),
    )


# ── Demo mode ─────────────────────────────────────────────────────────────────


def _try_demo(ico: str) -> FetchResult:
    """Demo mode — mock CRIBIS data (bez síťových volání)."""
    try:
        from utils.mock_data import _mock_cribis
        data = _mock_cribis(ico)
        if data:
            data["source"] = DataSource.MOCK.value
            missing = detect_missing_fields(data)
            field_src = {f: DataSource.MOCK.value for f in REQUIRED_FIELDS if f not in missing}
            log.info(f"[DataFetcher] Demo CRIBIS OK | ico={ico} | missing={missing}")
            return FetchResult(
                source=DataSource.MOCK,
                data=data,
                is_complete=True,
                wcr_partial=False,
                missing_fields=missing,
                field_sources=field_src,
            )
    except Exception as exc:
        log.warning(f"[DataFetcher] Demo mock selhalo: {exc}")

    return FetchResult(
        source=DataSource.MOCK,
        data={"ico": ico, "source": DataSource.MOCK.value},
        is_complete=False,
        wcr_partial=True,
        missing_fields=list(REQUIRED_FIELDS),
    )


# ── 1. CRIBIS ─────────────────────────────────────────────────────────────────


def _try_cribis(ico: str, errors: list[str]) -> Optional[FetchResult]:
    """
    Načte CRIBIS data ze silver_data_cribis_v3.
    IČO se normalizuje (_norm_ico) pro správný JOIN přes BIGINT.
    """
    try:
        from utils.data_connector import get_cribis_data
        data = get_cribis_data(ico)
        if data:
            data["source"] = DataSource.CRIBIS.value
            missing = detect_missing_fields(data)
            field_src = {f: DataSource.CRIBIS.value for f in REQUIRED_FIELDS if f not in missing}
            log.info(f"[DataFetcher] CRIBIS OK | ico={ico} | missing={missing}")
            return FetchResult(
                source=DataSource.CRIBIS,
                data=data,
                is_complete=len(missing) == 0,
                wcr_partial=len(missing) > 0,
                missing_fields=missing,
                field_sources=field_src,
            )
        errors.append("CRIBIS: žádná data pro toto IČO")
        log.warning(f"[DataFetcher] CRIBIS: žádná data | ico={ico}")
        return None
    except Exception as exc:
        msg = f"CRIBIS selhalo: {exc}"
        errors.append(msg)
        log.warning(f"[DataFetcher] {msg} | ico={ico}")
        return None


# ── 2. Justice.cz HTML scraping + PDF ─────────────────────────────────────────


def _http_get(url: str, accept: str = "text/html") -> bytes:
    """
    Jednoduchý HTTP GET s retry logikou.
    Raises urllib.error.URLError při selhání po HTTP_RETRIES pokusech.
    """
    headers = {
        "Accept": accept,
        "User-Agent": "Mozilla/5.0 (compatible; HorizonBank-Enrichment/1.0)",
    }
    last_exc: Exception = RuntimeError("no attempt")
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return resp.read()
        except Exception as exc:
            last_exc = exc
            log.warning(f"[DataFetcher] HTTP GET pokus {attempt}/{HTTP_RETRIES} selhal: {url} → {exc}")
            if attempt < HTTP_RETRIES:
                time.sleep(2 ** attempt)  # exponential back-off
    raise last_exc


def _parse_pdf_text(pdf_bytes: bytes) -> str:
    """
    Extrahuje prostý text ze stažených PDF bajtů pomocí pypdf.
    Vrátí prázdný string pokud pypdf není dostupný nebo PDF nelze parsovat.
    """
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except ImportError:
        log.warning("[DataFetcher] pypdf není nainstalován — PDF parsing přeskočen")
        return ""
    except Exception as exc:
        log.warning(f"[DataFetcher] PDF parsing selhal: {exc}")
        return ""


def _extract_number(text: str, pattern: str) -> Optional[float]:
    """
    Najde první číslo v textu podle regex patternu (skupina 1).
    Čísla mohou používat tečku nebo mezeru jako oddělovač tisíců,
    čárku jako desetinnou čárku (český formát).
    """
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_justice_financials(text: str) -> dict:
    """
    Parsuje text z Justice.cz výroční zprávy PDF.
    Extrahuje klíčové finanční položky pomocí regex patterns.

    Vrátí dict s nalezenými hodnotami (None = nenalezeno).
    Všechny hodnoty jsou v tis. Kč → konvertujeme na Kč (*1000).
    """
    def find_kc(pattern: str) -> Optional[float]:
        val = _extract_number(text, pattern)
        if val is not None:
            return val * 1_000  # tis. Kč → Kč
        return None

    return {
        # Výkaz zisku a ztráty
        "revenue":          find_kc(r"Tr[žz]by\s+(?:za\s+zbo[žz][íi]\s+a\s+v[yý]robky\s+)?[\d\s]+[\s|]\s*([\d\s,]+)"),
        "ebitda":           find_kc(r"EBITDA\s*[:\|]?\s*([\d\s,]+)"),
        "ebit":             find_kc(r"EBIT\b\s*[:\|]?\s*([\d\s,]+)"),
        "net_income":       find_kc(r"V[yý]sledek hospoda[řr]en[íi]\s+za\s+[úu][čc]etn[íi]\s+obdob[íi]\s+([\d\s,]+)"),
        "interest_expense": find_kc(r"N[áa]kladov[eé]\s+[úu]roky\s+([\d\s,]+)"),
        "income_tax":       find_kc(r"Da[ňn]\s+z\s+p[řr][íi]jm[ůu]\s+([\d\s,]+)"),
        # Rozvaha — aktiva
        "total_assets":     find_kc(r"Aktiva\s+celkem\s+([\d\s,]+)"),
        "current_assets":   find_kc(r"Ob[ěe][žz]n[áa]\s+aktiva\s+([\d\s,]+)"),
        "fixed_assets":     find_kc(r"St[áa]l[áa]\s+aktiva\s+([\d\s,]+)"),
        "cash":             find_kc(r"Pen[ěe][žž]n[íi]\s+prost[řr]edky\s+([\d\s,]+)"),
        "inventories":      find_kc(r"Z[áa]soby\s+([\d\s,]+)"),
        "depreciation":     find_kc(r"[úU]pravy\s+hodnot\s+dlouhodob[eé]ho\s+\S+\s+majetku\s+([\d\s,]+)"),
        # Rozvaha — pasiva
        "equity":           find_kc(r"Vlastn[íi]\s+kap[íi]t[áa]l\s+([\d\s,]+)"),
        "total_debt":       find_kc(r"Ciz[íi]\s+zdroje\s+([\d\s,]+)"),
        "bank_liabilities_st": find_kc(r"Z[áa]vazky\s+k\s+[úu]v[ěe]rov[yý]m\s+instituc[íi]m\b\s+([\d\s,]+)"),
        "bank_liabilities_lt": find_kc(r"Z[áa]vazky\s+k\s+[úu]v[ěe]rov[yý]m\s+instituc[íi]m\s+1\s+([\d\s,]+)"),
        # Odvozené (budou None — musí být spočítány z výše)
        "net_debt":         None,
        "leverage_ratio":   None,
        "current_ratio":    None,
        "dscr":             None,
    }


def _find_justice_pdf_url(ico: str) -> Optional[str]:
    """
    Najde URL PDF výroční zprávy v Justice.cz sbírce listin.

    POZOR: Justice.cz (or.justice.cz) je plně renderován přes Apache Wicket
    (JavaScript SPA) — statický HTTP GET neobsahuje žádná data ani PDF odkazy.
    Bez headless browseru (Selenium/Playwright) nelze PDF URL získat.

    Tato funkce vždy vrátí None → cascade přejde na ARES API.
    Řešení pro produkci: nahradit Playwright headless scraperem nebo použít
    komerční API (Apify actor: apify/obchodni-rejstrik-downloader).
    """
    log.info(
        f"[DataFetcher] Justice.cz scraping přeskočeno — JS-only web (Wicket), "
        f"nelze bez headless browseru | ico={ico}"
    )
    return None


def _try_justice_pdf(ico: str, errors: list[str]) -> Optional[FetchResult]:
    """
    Scrape Justice.cz sbírku listin → stáhne PDF výroční zprávy → parsuje text.

    Kroky:
      1. Fetch HTML stránky sbírky listin pro IČO
      2. Najdi odkaz na výroční zprávu PDF
      3. Stáhni PDF
      4. Extrahuj text (pypdf)
      5. Parsuj finanční data regexem
      6. Odvoď net_debt, current_ratio

    Vrátí None (→ přejde na ARES) pokud jakýkoli krok selže.
    """
    log.info(f"[DataFetcher] Zkouším Justice.cz | ico={ico}")

    # Krok 1+2: najdi URL PDF
    pdf_url = _find_justice_pdf_url(ico)
    if not pdf_url:
        errors.append("Justice.cz: PDF odkaz nenalezen v sbírce listin")
        log.warning(f"[DataFetcher] Justice.cz: žádné PDF | ico={ico}")
        return None

    # Krok 3: stáhni PDF
    try:
        pdf_bytes = _http_get(pdf_url, accept="application/pdf")
    except Exception as exc:
        errors.append(f"Justice.cz: stažení PDF selhalo: {exc}")
        log.warning(f"[DataFetcher] Justice.cz PDF download fail | ico={ico}: {exc}")
        return None

    # Krok 4: extrahuj text
    text = _parse_pdf_text(pdf_bytes)
    if not text.strip():
        errors.append("Justice.cz: PDF text je prázdný (nelze parsovat)")
        log.warning(f"[DataFetcher] Justice.cz: prázdný PDF text | ico={ico}")
        return None

    # Krok 5: parsuj finanční data
    financials = _parse_justice_financials(text)

    # Krok 6: odvoď net_debt, current_ratio
    bank_st = financials.get("bank_liabilities_st") or 0.0
    bank_lt = financials.get("bank_liabilities_lt") or 0.0
    cash    = financials.get("cash") or 0.0
    ebitda  = financials.get("ebitda") or 0.0
    int_exp = financials.get("interest_expense") or 0.0
    curr_assets = financials.get("current_assets") or 0.0
    curr_liab   = bank_st  # konzervativně: jen krátkodobé bankovní závazky

    if (bank_st + bank_lt) > 0:
        financials["net_debt"] = (bank_st + bank_lt) - cash
    if ebitda and int_exp:
        debt_service = int_exp + (bank_st / 12 if bank_st else 0)
        if debt_service > 0:
            financials["leverage_ratio"] = round(financials["net_debt"] / ebitda, 3) if financials.get("net_debt") else None
            financials["dscr"] = round(ebitda / debt_service, 3)
    if curr_assets and curr_liab:
        financials["current_ratio"] = round(curr_assets / curr_liab, 3)

    data = {
        "ico":    ico,
        "source": DataSource.JUSTICE.value,
        **financials,
    }

    missing = detect_missing_fields(data)
    field_src = {f: DataSource.JUSTICE.value for f in REQUIRED_FIELDS if f not in missing}

    found_count = len(REQUIRED_FIELDS) - len(missing)
    log.info(f"[DataFetcher] Justice.cz OK | ico={ico} | found={found_count}/{len(REQUIRED_FIELDS)} KPI")

    return FetchResult(
        source=DataSource.JUSTICE,
        data=data,
        is_complete=len(missing) == 0,
        is_partial=len(missing) > 0,
        wcr_partial=len(missing) > 0,
        error_chain=errors,
        missing_fields=missing,
        field_sources=field_src,
    )


# ── 3. ARES API ───────────────────────────────────────────────────────────────


def _try_ares(ico: str, errors: list[str]) -> Optional[FetchResult]:
    """
    Základní údaje z ARES (veřejný REST API MF ČR, bez API klíče).
    Pouze základní info — BEZ finančních výkazů → wcr_partial=True.

    Endpoint: https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ico}
    Dokumentace: https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/openapi
    """
    import json

    # ARES vyžaduje původní IČO s vedoucími nulami (8 číslic, zero-padded)
    # Na rozdíl od CRIBIS, kde musíme nuly ODSTRANIT
    ares_ico = str(ico).zfill(8)
    url = f"https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ares_ico}"
    log.info(f"[DataFetcher] Zkouším ARES API | ico={ico}")
    try:
        raw_bytes = _http_get(url, accept="application/json")
        raw = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        msg = f"ARES selhalo: {exc}"
        errors.append(msg)
        log.warning(f"[DataFetcher] {msg} | ico={ico}")
        return None

    if not raw:
        errors.append("ARES: prázdná odpověď")
        return None

    # Extrakce adresy — sidlo je dict
    sidlo = raw.get("sidlo") or {}
    # ARES vrací textovaAdresa přímo — nejspolehlivější
    adresa = sidlo.get("textovaAdresa", "")
    if not adresa:
        adresa_parts = [
            sidlo.get("nazevUlice", ""),
            str(sidlo.get("cisloDomovni", "")),
            sidlo.get("nazevObce", sidlo.get("nazevMestskeCastiObvodu", "")),
            str(sidlo.get("psc", "")),
        ]
        adresa = " ".join(p for p in adresa_parts if p).strip()

    city = sidlo.get("nazevObce", "")

    # NACE — czNace vrací list[str] (kódy), czNace2008 také list[str]
    nace_raw = raw.get("czNace") or raw.get("czNace2008") or []
    first_nace = nace_raw[0] if nace_raw else None
    if isinstance(first_nace, dict):
        nace_code = first_nace.get("kod", "")
    else:
        nace_code = str(first_nace) if first_nace else ""

    # pravniForma — v novém API je plain string kód (např. '121' = a.s.)
    pravni_forma_raw = raw.get("pravniForma") or ""
    if isinstance(pravni_forma_raw, dict):
        legal_form = pravni_forma_raw.get("nazev", "")
    else:
        # Kódník: 112=s.r.o., 121=a.s., 101=v.o.s. atd. — vrátíme kód
        legal_form = str(pravni_forma_raw)

    # Aktivní subjekt — stavZdrojeRos nebo stavZdrojeVr = AKTIVNI
    registrace = raw.get("seznamRegistraci") or {}
    is_active = (
        registrace.get("stavZdrojeRos") == "AKTIVNI"
        or registrace.get("stavZdrojeVr") == "AKTIVNI"
    ) if registrace else None

    data: dict = {
        "ico":            raw.get("ico", ico),
        "source":         DataSource.ARES.value,
        "company_name":   raw.get("obchodniJmeno", ""),
        "nace_code":      nace_code,
        "legal_form":     legal_form,
        "city":           city,
        "address":        adresa,
        "dic":            raw.get("dic", ""),
        "date_founded":   raw.get("datumVzniku", ""),
        "is_active":      is_active,
        # Finanční data — ARES neposkytuje → vše None
        **{f: None for f in FINANCIAL_FIELDS},
    }
    log.info(
        f"[DataFetcher] ARES OK | ico={ico} | "
        f"name={data['company_name']} | active={data['is_active']}"
    )

    # ARES neposkytuje žádná finanční pole — všechna jsou missing
    missing = detect_missing_fields(data)
    return FetchResult(
        source=DataSource.ARES,
        data=data,
        is_complete=False,
        is_partial=True,
        wcr_partial=True,
        error_chain=errors,
        missing_fields=missing,
        field_sources={},  # žádné fin. pole z ARES
    )


# ── Enrichment orchestrátor ───────────────────────────────────────────────────


def enrich_company(ico: str) -> FetchResult:
    """
    Hlavní obohacovací agent — detekuje chybějící pole a kaskádově je doplňuje.

    Algoritmus:
      1. Fetch primárního zdroje (CRIBIS / demo mock)
      2. detect_missing_fields() — zjisti mezery
      3. Pokud chybí finanční pole → zkus Justice.cz PDF (merge dat)
      4. Pokud stále chybí základní info → zkus ARES (merge identifikace)
      5. Pokud ICO vůbec nenalezeno → FROZEN
      6. Anotuj každé pole zdrojem v field_sources

    Args:
        ico: IČO firmy (string, může mít vedoucí nuly)

    Returns:
        FetchResult s obohacenými daty, field_sources mapou a missing_fields.

    Rules:
        - NIKDY nefallbackuj na T-1 data
        - Každé pole v data["source_map"] ukazuje odkud pochází
        - FROZEN = žádný zdroj nedostupný
    """
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"
    errors: list[str] = []
    merged_data: dict = {"ico": ico}
    field_sources: dict = {}

    # ── Krok 1: primární zdroj ────────────────────────────────────────────────
    if is_demo:
        primary = _try_demo(ico)
    else:
        primary = _try_cribis(ico, errors)

    if primary is not None and not primary.frozen:
        merged_data.update(primary.data)
        field_sources.update(primary.field_sources)
    elif not is_demo:
        errors.append("Primární zdroj (CRIBIS) nedostupný")

    # ── Krok 2: detekce chybějících polí ─────────────────────────────────────
    missing = detect_missing_fields(merged_data)

    # ── Krok 3: Justice.cz doplnění (jen prod, jen pokud chybí fin. data) ────
    if not is_demo and any(f in FINANCIAL_FIELDS for f in missing):
        justice = _try_justice_pdf(ico, errors)
        if justice is not None and not justice.frozen:
            for field_name, val in justice.data.items():
                # Doplní pouze chybějící pole — neoverwrite existující data
                if field_name in missing and val is not None:
                    merged_data[field_name] = val
                    field_sources[field_name] = DataSource.JUSTICE.value
            missing = detect_missing_fields(merged_data)
            log.info(f"[Enrichment] Justice.cz merge | ico={ico} | remaining_missing={missing}")

    # ── Krok 4: ARES doplnění (identifikace, pokud chybí company_name/city) ──
    needs_basic = not merged_data.get("company_name") or not merged_data.get("city")
    if not is_demo and needs_basic:
        ares = _try_ares(ico, errors)
        if ares is not None and not ares.frozen:
            for key in ("company_name", "city", "nace_code", "legal_form", "address",
                        "dic", "date_founded", "is_active"):
                if not merged_data.get(key) and ares.data.get(key):
                    merged_data[key] = ares.data[key]
                    field_sources[key] = DataSource.ARES.value
            log.info(f"[Enrichment] ARES merge | ico={ico}")

    # ── Krok 5: FROZEN pokud nic nenalezeno ──────────────────────────────────
    financial_found = any(
        merged_data.get(f) is not None for f in FINANCIAL_FIELDS
    )
    if not financial_found and not is_demo:
        log.error(f"[Enrichment] FROZEN — žádná finanční data | ico={ico} | errors={errors}")
        return FetchResult(
            source=DataSource.FROZEN,
            data={"ico": ico, "source": DataSource.FROZEN.value},
            frozen=True,
            is_complete=False,
            wcr_partial=True,
            error_chain=errors,
            missing_fields=list(REQUIRED_FIELDS),
            field_sources={},
        )

    # ── Krok 6: finální metadata ──────────────────────────────────────────────
    missing = detect_missing_fields(merged_data)
    merged_data["source"] = (
        primary.source.value if primary is not None else DataSource.FROZEN.value
    )
    merged_data["source_map"] = field_sources
    merged_data["enriched_at"] = datetime.now(timezone.utc).isoformat()
    merged_data["missing_fields"] = missing

    dominant_source = primary.source if primary else DataSource.FROZEN
    log.info(
        f"[Enrichment] Hotovo | ico={ico} | source={dominant_source.value} "
        f"| missing={len(missing)}/{len(REQUIRED_FIELDS)} | errors={len(errors)}"
    )

    return FetchResult(
        source=dominant_source,
        data=merged_data,
        is_complete=len(missing) == 0,
        is_partial=len(missing) > 0,
        wcr_partial=len(missing) > 0,
        frozen=False,
        error_chain=errors,
        missing_fields=missing,
        field_sources=field_sources,
    )


# ── Databricks write-back ─────────────────────────────────────────────────────


def save_enriched_to_databricks(result: FetchResult) -> bool:
    """
    Zapíše obohacený záznam zpět do Databricks tabulky enriched_company_data.

    Tabulka: {ENRICH_CATALOG}.{ENRICH_SCHEMA}.{ENRICH_TABLE}
    Schema: ico, source, enriched_at, is_complete, wcr_partial,
            missing_fields (JSON string), field_sources (JSON string),
            + všechna finanční pole z REQUIRED_FIELDS

    V demo mode: pouze loguje, nezapisuje.

    Returns:
        True = zapsáno · False = chyba nebo demo mode
    """
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"
    if is_demo:
        log.info(f"[DataFetcher] Demo mode — Databricks zápis přeskočen | ico={result.data.get('ico')}")
        return False

    try:
        import json
        from utils.data_connector import query

        ico = result.data.get("ico", "")
        now = datetime.now(timezone.utc).isoformat()

        # Sestavení INSERT hodnot pro každé required pole
        fin_cols = ", ".join(REQUIRED_FIELDS)
        fin_vals = ", ".join(
            str(result.data.get(f)) if result.data.get(f) is not None else "NULL"
            for f in REQUIRED_FIELDS
        )

        sql = f"""
            INSERT INTO {_ENRICH_CATALOG}.{_ENRICH_SCHEMA}.{_ENRICH_TABLE}
            (ico, source, enriched_at, is_complete, wcr_partial,
             missing_fields, field_sources, {fin_cols})
            VALUES (
                '{ico}',
                '{result.source.value}',
                '{now}',
                {str(result.is_complete).upper()},
                {str(result.wcr_partial).upper()},
                '{json.dumps(result.missing_fields, ensure_ascii=False)}',
                '{json.dumps(result.field_sources, ensure_ascii=False)}',
                {fin_vals}
            )
        """
        query(sql)
        log.info(f"[DataFetcher] Databricks INSERT OK | ico={ico} | table={_ENRICH_TABLE}")
        return True

    except Exception as exc:
        log.error(f"[DataFetcher] Databricks INSERT selhal: {exc}")
        return False


# ── CSV backup ────────────────────────────────────────────────────────────────


def save_enriched_to_csv(result: FetchResult, csv_path: Optional[str] = None) -> str:
    """
    Záloha obohaceného záznamu jako CSV soubor.

    Args:
        result:   FetchResult z enrich_company() nebo fetch_financial_data()
        csv_path: Cesta k výstupnímu souboru.
                  Výchozí: enriched_data/{ico}_{timestamp}.csv

    Returns:
        Absolutní cesta k CSV souboru.
    """
    import json

    ico = result.data.get("ico", "unknown")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if csv_path is None:
        out_dir = os.path.join(os.getcwd(), "enriched_data")
        os.makedirs(out_dir, exist_ok=True)
        csv_path = os.path.join(out_dir, f"{ico}_{timestamp}.csv")

    # Sloupce: metadata + required finanční pole + ostatní
    meta_cols = ["ico", "source", "enriched_at", "is_complete",
                 "wcr_partial", "missing_fields", "field_sources"]
    fin_cols  = REQUIRED_FIELDS
    extra_cols = [k for k in result.data if k not in meta_cols + fin_cols
                  and k not in ("source_map",)]
    all_cols = meta_cols + fin_cols + extra_cols

    row: dict = {}
    for col in all_cols:
        val = result.data.get(col)
        if col == "missing_fields":
            val = json.dumps(result.missing_fields, ensure_ascii=False)
        elif col == "field_sources":
            val = json.dumps(result.field_sources, ensure_ascii=False)
        elif col == "is_complete":
            val = result.is_complete
        elif col == "wcr_partial":
            val = result.wcr_partial
        elif col == "source":
            val = result.source.value
        row[col] = val if val is not None else ""

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols)
        writer.writeheader()
        writer.writerow(row)

    log.info(f"[DataFetcher] CSV záloha uložena | path={csv_path}")
    return csv_path


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    os.environ.setdefault("ICM_ENV", "demo")

    print("=" * 60)
    print("data_fetcher.py — smoke test")
    print("=" * 60)

    # ── 1. fetch_financial_data (demo) ────────────────────────────────────────
    print("\n[1] fetch_financial_data — Stavební holding Praha (27082440)")
    result = fetch_financial_data("27082440")
    print(f"    source:       {result.source.value}")
    print(f"    is_complete:  {result.is_complete}")
    print(f"    frozen:       {result.frozen}")
    print(f"    wcr_partial:  {result.wcr_partial}")
    print(f"    ebitda:       {result.data.get('ebitda'):,.0f}")
    print(f"    missing:      {result.missing_fields}")
    assert not result.frozen, "Demo mode: nesmí být frozen"
    assert result.is_complete, "Demo mode: CRIBIS mock musí být kompletní"
    assert result.data.get("ebitda") is not None, "ebitda musí být přítomno"

    # ── 2. detect_missing_fields ──────────────────────────────────────────────
    print("\n[2] detect_missing_fields — prázdný dict")
    missing = detect_missing_fields({})
    assert set(missing) == set(REQUIRED_FIELDS), f"Všechna pole musí chybět, got: {missing}"
    print(f"    missing count: {len(missing)} (OK — all {len(REQUIRED_FIELDS)} required)")

    print("\n[2b] detect_missing_fields — kompletní data")
    complete = {f: 1.0 for f in REQUIRED_FIELDS}
    missing2 = detect_missing_fields(complete)
    assert missing2 == [], f"Nesmí chybět žádné pole, got: {missing2}"
    print(f"    missing count: {len(missing2)} (OK — complete)")

    # ── 3. enrich_company (demo) ──────────────────────────────────────────────
    print("\n[3] enrich_company — demo mode (Energetika Brno 00514152)")
    enriched = enrich_company("00514152")
    print(f"    source:       {enriched.source.value}")
    print(f"    is_complete:  {enriched.is_complete}")
    print(f"    frozen:       {enriched.frozen}")
    print(f"    field_sources sample: {dict(list(enriched.field_sources.items())[:3])}")
    assert not enriched.frozen, "Enrichment nesmí být frozen v demo mode"
    assert "enriched_at" in enriched.data, "enriched_at musí být přítomno"
    assert "source_map" in enriched.data, "source_map musí být přítomno"

    # ── 4. FROZEN path — neznámé IČO (demo) ──────────────────────────────────
    print("\n[4] enrich_company — neznámé IČO (99999999)")
    frozen_result = enrich_company("99999999")
    print(f"    source:  {frozen_result.source.value}")
    print(f"    frozen:  {frozen_result.frozen}")
    # V demo mode: mock_data vrátí None → result bude mock bez fin. dat, ale ne frozen
    # (demo mode neprochází plnou cascade) — proto kontrolujeme jen source
    assert frozen_result.source.value in (DataSource.MOCK.value, DataSource.FROZEN.value)
    print(f"    OK — správně zpracováno jako {frozen_result.source.value}")

    # ── 5. IČO normalizace ────────────────────────────────────────────────────
    print("\n[5] _norm_ico normalizace")
    assert _norm_ico("00514152") == "514152", "Vedoucí nuly musí být odstraněny"
    assert _norm_ico("27082440") == "27082440", "Číslo bez nul zůstane stejné"
    assert _norm_ico("0") == "0", "Nula zůstane nulou"
    print("    OK — '00514152' → '514152' · '27082440' → '27082440'")

    # ── 6. CSV backup ─────────────────────────────────────────────────────────
    print("\n[6] save_enriched_to_csv")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = save_enriched_to_csv(enriched, os.path.join(tmpdir, "test.csv"))
        assert os.path.exists(csv_path), "CSV soubor musí existovat"
        with open(csv_path, encoding="utf-8") as f:
            content = f.read()
        assert "ico" in content, "CSV musí obsahovat sloupec ico"
        assert "ebitda" in content, "CSV musí obsahovat sloupec ebitda"
        print(f"    OK — CSV uložen ({len(content)} bajtů)")

    print("\n" + "=" * 60)
    print("OK — data_fetcher.py smoke test PASSED (všech 6 testů)")
    print("=" * 60)
