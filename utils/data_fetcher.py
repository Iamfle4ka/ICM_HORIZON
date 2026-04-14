# DETERMINISTIC
"""
Data Fetcher — utils/data_fetcher.py
Cascade fallback pro finanční data: CRIBIS → Justice.cz → ARES → Freeze.

Pořadí zdrojů:
  1. CRIBIS (silver_data_cribis_v3) — nejkompletnější
  2. Justice.cz PDF (výroční zpráva) — pokud CRIBIS chybí
  3. ARES API (základní údaje) — fallback
  4. Process Freeze — pokud žádný zdroj nedostupný

DETERMINISTIC — žádný LLM.
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)


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


# ── Cascade entry point ───────────────────────────────────────────────────────


def fetch_financial_data(ico: str) -> FetchResult:
    """
    Hlavní vstupní bod. Cascade: CRIBIS → Justice → ARES → Freeze.

    Demo mode: vždy vrátí mock CRIBIS data.
    Prod mode: zkouší zdroje v pořadí.

    Returns:
        FetchResult s daty a metadaty o zdroji.
    """
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"

    if is_demo:
        return _try_demo(ico)

    errors: list[str] = []

    # 1. CRIBIS
    result = _try_cribis(ico, errors)
    if result is not None:
        return result

    # 2. Justice.cz PDF
    result = _try_justice_pdf(ico, errors)
    if result is not None:
        return result

    # 3. ARES API
    result = _try_ares(ico, errors)
    if result is not None:
        return result

    # 4. Process Freeze
    log.error(
        f"[DataFetcher] VŠECHNY ZDROJE SELHALY pro ico={ico} | "
        f"errors={errors} → PROCESS FREEZE"
    )
    return FetchResult(
        source=DataSource.FROZEN,
        data={},
        frozen=True,
        is_complete=False,
        is_partial=False,
        wcr_partial=True,
        error_chain=errors,
    )


# ── Demo mode ─────────────────────────────────────────────────────────────────


def _try_demo(ico: str) -> FetchResult:
    """Demo mode — mock CRIBIS data."""
    try:
        from utils.mock_data import _mock_cribis
        data = _mock_cribis(ico)
        if data:
            log.info(f"[DataFetcher] Demo CRIBIS OK | ico={ico}")
            return FetchResult(
                source=DataSource.MOCK,
                data=data,
                is_complete=True,
                wcr_partial=False,
            )
    except Exception as exc:
        log.warning(f"[DataFetcher] Demo mock selhalo: {exc}")

    return FetchResult(
        source=DataSource.MOCK,
        data={},
        is_complete=False,
        wcr_partial=True,
    )


# ── 1. CRIBIS ─────────────────────────────────────────────────────────────────


def _try_cribis(ico: str, errors: list[str]) -> Optional[FetchResult]:
    """Načte CRIBIS data ze silver_data_cribis_v3."""
    try:
        from utils.data_connector import get_cribis_data
        data = get_cribis_data(ico)
        if data:
            log.info(f"[DataFetcher] CRIBIS OK | ico={ico}")
            return FetchResult(
                source=DataSource.CRIBIS,
                data=data,
                is_complete=True,
                wcr_partial=False,
            )
        errors.append("CRIBIS: žádná data pro toto IČO")
        log.warning(f"[DataFetcher] CRIBIS: žádná data | ico={ico}")
        return None
    except Exception as exc:
        msg = f"CRIBIS selhalo: {exc}"
        errors.append(msg)
        log.warning(f"[DataFetcher] {msg} | ico={ico}")
        return None


# ── 2. Justice.cz PDF ─────────────────────────────────────────────────────────


def _try_justice_pdf(ico: str, errors: list[str]) -> Optional[FetchResult]:
    """
    Stáhne výroční zprávu z Justice.cz a extrahuje finanční data.
    Pouze v prod mode — v demo se přeskočí.

    URL vzor: https://or.justice.cz/ias/ui/vypis-sl-firma?subjektId={ico}
    Poznámka: Parsování PDF je stub — implementace závisí na konkrétním formátu.
    """
    try:
        log.info(f"[DataFetcher] Zkouším Justice.cz PDF | ico={ico}")
        # Stub — v reálném nasazení by se stáhlo PDF a parsovalo
        # Doporučené knihovny: pdfminer, pymupdf, nebo AI extraction
        # PDF URL: https://or.justice.cz/ias/ui/vypis-sl-firma?subjektId={ico}
        raise NotImplementedError("Justice.cz PDF parsing není implementován")
    except NotImplementedError:
        errors.append("Justice.cz: parser není implementován")
        log.warning(f"[DataFetcher] Justice.cz přeskočeno (stub) | ico={ico}")
        return None
    except Exception as exc:
        msg = f"Justice.cz selhalo: {exc}"
        errors.append(msg)
        log.warning(f"[DataFetcher] {msg} | ico={ico}")
        return None


# ── 3. ARES API ───────────────────────────────────────────────────────────────


def _try_ares(ico: str, errors: list[str]) -> Optional[FetchResult]:
    """
    Základní údaje z ARES (veřejný REST API MF ČR).
    Pouze základní info — BEZ finančních výkazů → wcr_partial=True.

    API: https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ico}
    """
    try:
        import urllib.request
        import json

        url = f"https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ico}"
        log.info(f"[DataFetcher] Zkouším ARES API | ico={ico}")

        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        if not raw:
            errors.append("ARES: prázdná odpověď")
            return None

        data = {
            "ico":          raw.get("ico", ico),
            "company_name": raw.get("obchodniJmeno", ""),
            "nace_code":    raw.get("czNace", [{}])[0].get("kod", "") if raw.get("czNace") else "",
            "legal_form":   raw.get("pravniForma", {}).get("nazev", ""),
            "city":         raw.get("sidlo", {}).get("obec", ""),
            "source":       "ares_api",
            # Finanční data nedostupná z ARES
            "ebitda":       None,
            "revenue":      None,
            "leverage_ratio": None,
            "dscr":         None,
            "current_ratio": None,
        }
        log.info(f"[DataFetcher] ARES OK | ico={ico} name={data['company_name']}")
        return FetchResult(
            source=DataSource.ARES,
            data=data,
            is_complete=False,
            is_partial=True,
            wcr_partial=True,
            error_chain=errors,
        )

    except Exception as exc:
        msg = f"ARES selhalo: {exc}"
        errors.append(msg)
        log.warning(f"[DataFetcher] {msg} | ico={ico}")
        return None


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    os.environ.setdefault("ICM_ENV", "demo")

    result = fetch_financial_data("27082440")
    print(f"Source: {result.source.value}")
    print(f"Complete: {result.is_complete}")
    print(f"Frozen: {result.frozen}")
    print(f"WCR partial: {result.wcr_partial}")
    print(f"EBITDA: {result.data.get('ebitda')}")
    assert not result.frozen, "Demo mode: nesmí být frozen"
    assert result.is_complete, "Demo mode: CRIBIS mock musí být kompletní"
    print("OK — data_fetcher.py smoke test passed")
