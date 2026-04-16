# DETERMINISTIC
"""
News & Signal Fetcher — utils/news_fetcher.py
EWS signály z veřejných zdrojů: ISIR, ČNB, Google News.

Funkce:
  get_all_ews_signals(ico, company_name) -> list[NewsSignal]
  check_isir(ico)         → insolvence / exekuce
  check_cnb_rates()       → ČNB repo sazba
  scrape_news(ico, name)  → Google News (REST)

DETERMINISTIC — žádný LLM.
"""

import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)

_TIMEOUT_SEC = 8   # timeout pro HTTP požadavky


# ── Datové typy ───────────────────────────────────────────────────────────────


class SignalType(Enum):
    INSOLVENCY   = "insolvency"
    EXECUTION    = "execution"
    CNB_RATE     = "cnb_rate_change"
    NEWS_NEGATIVE = "news_negative"
    NEWS_NEUTRAL  = "news_neutral"


class SignalLevel(Enum):
    RED   = "RED"
    AMBER = "AMBER"
    INFO  = "INFO"


@dataclass
class NewsSignal:
    signal_type:   SignalType
    level:         SignalLevel
    title:         str
    description:   str
    source:        str
    detected_at:   str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    url:           Optional[str] = None
    raw:           Optional[dict] = None


# ── 1. ISIR — Insolvenční rejstřík ───────────────────────────────────────────


def check_isir(ico: str) -> list[NewsSignal]:
    """
    Ověří insolvenci ve veřejném ISIR API (MSPRAVEDLNOSTI ČR).
    REST endpoint: https://isir.justice.cz/isir/ueu/vysledek_lustrace_dluznika.do
    POZN: endpoint vrací HTTP 500 při neexistujícím IČO — to je normální chování ISIR.

    Demo mode: vrátí prázdný seznam (žádná insolvence v mock datech).
    """
    signals: list[NewsSignal] = []
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"

    if is_demo:
        log.debug(f"[NewsFetcher] ISIR demo mode | ico={ico} → žádné signály")
        return signals

    try:
        url = (
            "https://isir.justice.cz/isir/ueu/vysledek_lustrace_dluznika.do"
            f"?ico={ico}&format=json"
        )
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; ICM-EWS/1.0)",
        })
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        entries = data.get("polozky", []) if isinstance(data, dict) else []
        for entry in entries:
            stav = str(entry.get("stavRizeni", "")).upper()
            if "INSOLVENC" in stav or "KONKURS" in stav:
                signals.append(NewsSignal(
                    signal_type=SignalType.INSOLVENCY,
                    level=SignalLevel.RED,
                    title=f"ISIR: Insolvence {ico}",
                    description=f"Stav řízení: {stav}",
                    source="isir.justice.cz",
                    url=f"https://isir.justice.cz/isir/ueu/vysledek_lustrace_dluznika.do?ico={ico}",
                    raw=entry,
                ))
            elif "EXEKUC" in stav:
                signals.append(NewsSignal(
                    signal_type=SignalType.EXECUTION,
                    level=SignalLevel.AMBER,
                    title=f"ISIR: Exekuce {ico}",
                    description=f"Stav řízení: {stav}",
                    source="isir.justice.cz",
                    raw=entry,
                ))

        log.info(f"[NewsFetcher] ISIR: ico={ico} → {len(signals)} signálů")
    except urllib.error.HTTPError as exc:
        # HTTP 500 = IČO nenalezeno v ISIR (normální chování) — není insolvence
        if exc.code == 500:
            log.debug(f"[NewsFetcher] ISIR: ico={ico} nenalezeno (HTTP 500) → žádná insolvence")
        else:
            log.warning(f"[NewsFetcher] ISIR selhalo HTTP {exc.code} | ico={ico}")
    except Exception as exc:
        log.warning(f"[NewsFetcher] ISIR selhalo: {exc} | ico={ico}")

    return signals


# ── 2. ČNB — repo sazba ────────────────────────────────────────────────────────


def check_cnb_rates() -> list[NewsSignal]:
    """
    Načte aktuální ČNB repo sazbu z veřejného API.
    Signál pokud sazba > 5 % (zvýšené úrokové riziko pro floating rate úvěry).

    Endpoint: https://www.cnb.cz/cnb/STAT.ARADY_PKG.VYSTUP?p_period=1&p_sort=2&p_des=50&p_format=4
    """
    signals: list[NewsSignal] = []
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"

    if is_demo:
        # Simulovaná repo sazba pro demo
        repo_rate = 3.75
        log.debug(f"[NewsFetcher] ČNB demo mode | repo={repo_rate}%")
        if repo_rate > 5.0:
            signals.append(NewsSignal(
                signal_type=SignalType.CNB_RATE,
                level=SignalLevel.AMBER,
                title=f"ČNB: Repo sazba {repo_rate}% (demo)",
                description="Zvýšené úrokové náklady pro floating rate úvěry.",
                source="cnb.cz_mock",
            ))
        return signals

    try:
        # ČNB API — CZEONIA denní sazba (api.cnb.cz/cnbapi/czeonia/daily)
        # Náhrada za starý ARAD endpoint (HTTP 404 od 2025)
        url = "https://api.cnb.cz/cnbapi/czeonia/daily?language=CS"
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "ICM-EWS/1.0",
        })
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # {"czeoniaDaily": {"validFor": "2026-04-15", "rate": 3.09, ...}}
        rate_obj  = data.get("czeoniaDaily", {})
        repo_rate = float(rate_obj.get("rate", 0))
        valid_for = rate_obj.get("validFor", "")
        log.info(f"[NewsFetcher] ČNB CZEONIA sazba: {repo_rate}% (k {valid_for})")

        if repo_rate > 5.0:
            signals.append(NewsSignal(
                signal_type=SignalType.CNB_RATE,
                level=SignalLevel.AMBER,
                title=f"ČNB: CZEONIA sazba {repo_rate}% (k {valid_for})",
                description=(
                    f"Overnight sazba {repo_rate}% překračuje 5% práh. "
                    "Zvýšené úrokové náklady pro klienty s floating rate úvěry."
                ),
                source="api.cnb.cz",
            ))
    except Exception as exc:
        log.warning(f"[NewsFetcher] ČNB sazba selhala: {exc}")

    return signals


# ── 3. Google News (RSS) ──────────────────────────────────────────────────────

_NEGATIVE_KEYWORDS = [
    "insolvenc", "konkurs", "likvidac", "exekuc", "pokuta", "sankce",
    "průšvih", "skandál", "podvod", "krach", "úpadek", "ztráta",
    "propouštěn", "restrukturaliz",
]

_POSITIVE_KEYWORDS = ["zisk", "rostl", "expanz", "investic", "akvizic"]


def scrape_news(ico: str, company_name: str, max_results: int = 5) -> list[NewsSignal]:
    """
    Vyhledá zprávy o firmě přes Google News RSS.
    Analyzuje titulky deterministicky (keyword matching) — BEZ LLM.

    Args:
        ico:          IČO firmy (pro identifikaci)
        company_name: Název firmy pro vyhledávání
        max_results:  Maximální počet výsledků

    Returns:
        list[NewsSignal]
    """
    signals: list[NewsSignal] = []
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"

    if is_demo:
        log.debug(f"[NewsFetcher] News demo mode | ico={ico} → žádné zprávy")
        return signals

    try:
        query = urllib.parse.quote(company_name)
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=cs&gl=CZ&ceid=CZ:cs"
        req = urllib.request.Request(rss_url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })

        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        # Jednoduchý XML parsing bez závislostí
        import re
        items = re.findall(r"<item>(.*?)</item>", content, re.DOTALL)[:max_results]

        for item in items:
            # Google News vrací buď CDATA nebo plain text v <title>
            title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item)
            if not title_m:
                title_m = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
            link_m  = re.search(r"<link>(.*?)</link>", item)
            title = title_m.group(1).strip() if title_m else ""
            link  = link_m.group(1).strip() if link_m else None

            if not title:
                continue

            title_lower = title.lower()
            is_negative = any(kw in title_lower for kw in _NEGATIVE_KEYWORDS)
            is_positive = any(kw in title_lower for kw in _POSITIVE_KEYWORDS)

            if is_negative:
                signals.append(NewsSignal(
                    signal_type=SignalType.NEWS_NEGATIVE,
                    level=SignalLevel.AMBER,
                    title=title,
                    description=f"Negativní zpráva o {company_name} (keyword matching)",
                    source="google_news",
                    url=link,
                ))
            elif not is_positive:
                signals.append(NewsSignal(
                    signal_type=SignalType.NEWS_NEUTRAL,
                    level=SignalLevel.INFO,
                    title=title,
                    description=f"Zpráva o {company_name}",
                    source="google_news",
                    url=link,
                ))

        log.info(f"[NewsFetcher] News: ico={ico} → {len(signals)} signálů")
    except Exception as exc:
        log.warning(f"[NewsFetcher] News scraping selhalo: {exc} | ico={ico}")

    return signals


# ── Hlavní vstupní bod ────────────────────────────────────────────────────────


def get_all_ews_signals(ico: str, company_name: str) -> list[NewsSignal]:
    """
    Agreguje EWS signály ze všech zdrojů: ISIR + ČNB + News.

    Returns:
        list[NewsSignal] seřazený RED → AMBER → INFO
    """
    signals: list[NewsSignal] = []

    signals.extend(check_isir(ico))
    signals.extend(check_cnb_rates())
    signals.extend(scrape_news(ico, company_name))

    level_order = {SignalLevel.RED: 0, SignalLevel.AMBER: 1, SignalLevel.INFO: 2}
    signals.sort(key=lambda s: level_order.get(s.level, 3))

    log.info(
        f"[NewsFetcher] Celkem signálů pro ico={ico}: {len(signals)} "
        f"(red={sum(1 for s in signals if s.level==SignalLevel.RED)}, "
        f"amber={sum(1 for s in signals if s.level==SignalLevel.AMBER)})"
    )
    return signals


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.environ.setdefault("ICM_ENV", "demo")

    signals = get_all_ews_signals("27082440", "Stavební holding Praha a.s.")
    print(f"Signals: {len(signals)}")
    for s in signals:
        print(f"  [{s.level.value}] {s.signal_type.value}: {s.title}")
    print("OK — news_fetcher.py smoke test passed")
