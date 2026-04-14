# AI + DETERMINISTIC
"""
Fáze 1 — Extrakce dat — pipeline/nodes/phase1_extraction.py

Uzly:
  - data_extractor_agent    ← Silver tabulky (primární) + LLM pro text docs (AI)
  - extraction_validator    ← validace struktury raw_data (DETERMINISTIC)

Primární cesta: data_connector → Silver tabulky (demo i production).
Sekundární cesta: Claude API pro textové dokumenty (Helios memos), pokud raw_documents přítomny.
Fallback při API chybě: Process Freeze (NE T-1 fallback).
"""

import json
import logging
import re
import time

from pipeline.state import ProcessStatus
from skills import registry
from utils.audit import _audit
from utils.chunking import chunks_to_context, semantic_chunk
from utils.wcr_rules import API_RETRY_COUNT, API_RETRY_DELAY_SEC, MIN_CONFIDENCE_SCORE

log = logging.getLogger(__name__)

# Zdroje dat (pro citace v memu)
_SILVER_DATA_SOURCES = {
    "company_master":   "silver_company_master — základní info firmy",
    "fin_profile":      "silver_corporate_financial_profile — finanční profil (SCD Type 2)",
    "credit_history":   "silver_credit_history — kreditní historie a kovenanty",
    "transactions_12m": "silver_transactions — transakce posledních 12 měsíců",
    "incidents_24m":    "silver_client_incidents — incidenty posledních 24 měsíců",
    "cribis_external":  "CRIBIS — externí rating (pokud dostupný)",
}

# Metriky které nelze vypočítat bez CRIBIS / externích dat
_MISSING_EXTERNAL_METRICS = [
    "ebitda", "net_debt", "current_assets", "current_liabilities",
    "debt_service", "operating_cashflow", "cribis_rating",
]


# AI (Silver tabulky + volitelně LLM pro text docs)
def data_extractor_agent(state: dict) -> dict:
    """
    Načte surová data pro IČO ze Silver tabulek přes data_connector.
    Volitelně zpracuje textové dokumenty (Helios memos) přes Claude API.

    Vstupy ze state:
        ico:           str  — IČO klienta
        raw_documents: dict[source_id → text]  — textové dokumenty (volitelné)

    Výstupy do state:
        extraction_result:   dict  — raw_data + agregované pole
        extraction_attempts: int   — počet pokusů
    """
    ico = state.get("ico", "UNKNOWN")
    log.info(f"[DataExtractorAgent] Zahajuji extrakci ze Silver tabulek | ico={ico}")

    skill = registry.get("extractor_skill")
    prompt = skill["prompt"]
    skill_version = skill["version"]

    # ── Krok 1: Fetch ze Silver tabulek ────────────────────────────────────────
    from utils.data_connector import (
        get_company_master,
        get_credit_history,
        get_customer_id,
        get_financial_profile,
        get_incidents_24m,
        get_transactions_12m,
    )

    company = get_company_master(ico)
    if company is None:
        log.error(f"[DataExtractorAgent] IČO {ico} nenalezeno v silver_company_master")
        audit = _audit(
            state,
            node="DataExtractorAgent",
            action="extraction_failed",
            result="company_not_found",
            prompt=prompt,
            prompt_version=skill_version,
            metadata={"ico": ico, "table": "silver_company_master"},
        )
        return {
            **state,
            "status":              ProcessStatus.FROZEN,
            "fallback_reason":     f"IČO {ico} nenalezeno v silver_company_master",
            "extraction_attempts": state.get("extraction_attempts", 0) + 1,
            "audit_trail":         audit,
        }

    customer_id = get_customer_id(ico)
    fin_profile = get_financial_profile(customer_id) if customer_id is not None else None
    if fin_profile is None:
        log.error(
            f"[DataExtractorAgent] Finanční profil nenalezen | ico={ico} customer_id={customer_id}"
        )
        audit = _audit(
            state,
            node="DataExtractorAgent",
            action="extraction_failed",
            result="fin_profile_missing",
            prompt=prompt,
            prompt_version=skill_version,
            metadata={"ico": ico, "customer_id": customer_id},
        )
        return {
            **state,
            "status":              ProcessStatus.FROZEN,
            "fallback_reason":     (
                f"Finanční profil pro IČO {ico} nenalezen "
                f"(customer_id={customer_id})"
            ),
            "extraction_attempts": state.get("extraction_attempts", 0) + 1,
            "audit_trail":         audit,
        }

    credit = get_credit_history(ico)
    if not credit:
        log.error(f"[DataExtractorAgent] Kreditní historie nenalezena | ico={ico}")
        audit = _audit(
            state,
            node="DataExtractorAgent",
            action="extraction_failed",
            result="credit_history_missing",
            prompt=prompt,
            prompt_version=skill_version,
            metadata={"ico": ico, "table": "silver_credit_history"},
        )
        return {
            **state,
            "status":              ProcessStatus.FROZEN,
            "fallback_reason":     f"Kreditní historie pro IČO {ico} nenalezena",
            "extraction_attempts": state.get("extraction_attempts", 0) + 1,
            "audit_trail":         audit,
        }

    # Transakce a incidenty — pokud selžou, pokračujeme (partial_data)
    transactions: list[dict] = []
    incidents: list[dict] = []
    partial_sources: list[str] = []

    try:
        transactions = get_transactions_12m(ico)
    except Exception as exc:
        log.warning(f"[DataExtractorAgent] silver_transactions selhaly | ico={ico} error={exc}")
        partial_sources.append("transactions_12m")

    try:
        incidents = get_incidents_24m(ico)
    except Exception as exc:
        log.warning(f"[DataExtractorAgent] silver_client_incidents selhaly | ico={ico} error={exc}")
        partial_sources.append("incidents_24m")

    raw_data = {
        "company":      company,
        "customer":     {"customer_id": customer_id},
        "fin_profile":  fin_profile,
        "credit":       credit,
        "transactions": transactions,
        "incidents":    incidents,
    }

    # Sestavení extraction_result z raw_data
    extraction_result = _build_extraction_from_raw_data(ico, raw_data)
    if partial_sources:
        extraction_result["partial_data_sources"] = partial_sources

    rows_returned = {
        "company":      1,
        "fin_profile":  1,
        "credit":       len(credit),
        "transactions": len(transactions),
        "incidents":    len(incidents),
    }
    missing_fields = [k for k, v in fin_profile.items() if v is None]

    log.info(
        f"[DataExtractorAgent] Silver extrakce hotova | ico={ico} "
        f"company={company.get('company_name')} "
        f"credit_rows={len(credit)} tx_rows={len(transactions)}"
    )

    audit = _audit(
        state,
        node="DataExtractorAgent",
        action="extraction_silver_mode",
        result="success",
        prompt=prompt,
        prompt_version=skill_version,
        tokens_used=0,
        metadata={
            "ico":              ico,
            "mode":             "silver_tables",
            "sources_queried":  6,
            "rows_returned":    rows_returned,
            "missing_fields":   missing_fields,
            "partial_sources":  partial_sources,
            "confidence_score": 1.0,
        },
    )

    # ── Krok 2: LLM pro textové dokumenty (Helios memos) ──────────────────────
    raw_documents: dict = state.get("raw_documents") or {}
    if raw_documents:
        log.info(
            f"[DataExtractorAgent] Zpracovávám textové dokumenty přes LLM | "
            f"ico={ico} docs={list(raw_documents)}"
        )
        all_chunks = []
        for source_id, doc_text in raw_documents.items():
            all_chunks.extend(semantic_chunk(doc_text, source_id=source_id))

        context = chunks_to_context(all_chunks)
        user_message = (
            f"IČO klienta: {ico}\n\n"
            f"Strukturovaná data ze Silver tabulek jsou již k dispozici. "
            f"Níže jsou textové dokumenty (Helios memos) — extrahuj pouze "
            f"doplňující kvalitativní informace (historický kontext, obchodní "
            f"vztahy, komentáře managementu).\n\n"
            f"DOKUMENTY:\n{context}\n\n"
            f"Vrať JSON s polem 'qualitative_notes' (list[str])."
        )

        attempts = state.get("extraction_attempts", 0)
        last_error: str | None = None

        for attempt in range(1, API_RETRY_COUNT + 1):
            attempts += 1
            try:
                from utils.llm_factory import get_llm

                api_client  = get_llm()
                response    = api_client.complete(
                    system=prompt,
                    user_message=user_message,
                    max_tokens=1024,
                )
                raw_text    = response.text
                tokens_used = response.tokens_used
                json_text = _extract_json(raw_text)
                llm_result = json.loads(json_text)
                extraction_result["qualitative_notes"] = llm_result.get(
                    "qualitative_notes", []
                )
                log.info(
                    f"[DataExtractorAgent] LLM textová extrakce OK | "
                    f"ico={ico} tokens={tokens_used}"
                )
                audit = _audit(
                    state,
                    node="DataExtractorAgent",
                    action="extraction_llm_text_docs",
                    result="success",
                    prompt=prompt,
                    prompt_version=skill_version,
                    tokens_used=tokens_used,
                    metadata={"ico": ico, "attempt": attempt, "docs": list(raw_documents)},
                )
                break

            except Exception as exc:
                last_error = str(exc)
                log.warning(
                    f"[DataExtractorAgent] LLM pokus {attempt}/{API_RETRY_COUNT} selhal | "
                    f"ico={ico} error={last_error}"
                )
                if attempt < API_RETRY_COUNT:
                    time.sleep(API_RETRY_DELAY_SEC)
        else:
            log.error(
                f"[DataExtractorAgent] LLM Process Freeze | ico={ico} last_error={last_error}"
            )
            audit = _audit(
                state,
                node="DataExtractorAgent",
                action="extraction_llm_failed",
                result="process_freeze",
                prompt=prompt,
                prompt_version=skill_version,
                metadata={"ico": ico, "attempts": attempts, "last_error": last_error},
            )
            return {
                **state,
                "status":              ProcessStatus.FROZEN,
                "fallback_reason":     f"LLM API selhala po {API_RETRY_COUNT} pokusech: {last_error}",
                "extraction_attempts": attempts,
                "audit_trail":         audit,
            }

        return {
            **state,
            "extraction_result":   extraction_result,
            "extraction_attempts": attempts,
            "audit_trail":         audit,
        }

    return {
        **state,
        "extraction_result":   extraction_result,
        "extraction_attempts": state.get("extraction_attempts", 0) + 1,
        "audit_trail":         audit,
    }


# DETERMINISTIC
def extraction_validator(state: dict) -> dict:
    """
    Validuje výsledek extrakce ze Silver tabulek:
    - extraction_result existuje
    - company_master přítomen
    - fin_profile přítomen (jinak FROZEN)
    - credit_history přítomna (jinak FROZEN)
    - IČO: přesně 8 číslic
    - Typová kontrola kritických polí (varování, ne freeze)
    - confidence_score >= MIN_CONFIDENCE_SCORE

    Čistý Python, žádný LLM.
    """
    ico = state.get("ico", "UNKNOWN")
    log.info(f"[ExtractionValidator] Zahajuji validaci | ico={ico}")

    extraction = state.get("extraction_result")
    if not extraction:
        log.error(f"[ExtractionValidator] Chybí extraction_result | ico={ico}")
        audit = _audit(
            state,
            node="ExtractionValidator",
            action="validation_failed",
            result="missing_extraction_result",
            metadata={"ico": ico},
        )
        return {
            **state,
            "status":          ProcessStatus.FROZEN,
            "fallback_reason": "Chybí extraction_result po extrakci",
            "audit_trail":     audit,
        }

    # Confidence score check
    confidence: float = float(extraction.get("confidence_score", 0.0))
    if confidence < MIN_CONFIDENCE_SCORE:
        log.warning(
            f"[ExtractionValidator] Nízká confidence | ico={ico} "
            f"score={confidence:.2f} required>={MIN_CONFIDENCE_SCORE}"
        )
        audit = _audit(
            state,
            node="ExtractionValidator",
            action="validation_failed",
            result=f"low_confidence_{confidence:.2f}",
            metadata={
                "ico":          ico,
                "confidence":   confidence,
                "min_required": MIN_CONFIDENCE_SCORE,
            },
        )
        return {
            **state,
            "status":          ProcessStatus.FROZEN,
            "fallback_reason": (
                f"Confidence score {confidence:.2f} < minimum {MIN_CONFIDENCE_SCORE}"
            ),
            "audit_trail": audit,
        }

    # IČO formát
    extracted_ico = str(extraction.get("ico", ""))
    if not re.fullmatch(r"\d{8}", extracted_ico.replace(" ", "")):
        log.warning(
            f"[ExtractionValidator] Neplatné IČO | ico={ico} extracted={extracted_ico!r}"
        )
        audit = _audit(
            state,
            node="ExtractionValidator",
            action="validation_failed",
            result="invalid_ico_format",
            metadata={"ico": ico, "extracted_ico": extracted_ico},
        )
        return {
            **state,
            "status":          ProcessStatus.FROZEN,
            "fallback_reason": f"Neplatný formát IČO: '{extracted_ico}' (požadováno 8 číslic)",
            "audit_trail":     audit,
        }

    # raw_data přítomnost
    raw_data = extraction.get("raw_data", {})

    if not raw_data.get("company"):
        audit = _audit(
            state,
            node="ExtractionValidator",
            action="validation_failed",
            result="missing_company_master",
            metadata={"ico": ico},
        )
        return {
            **state,
            "status":          ProcessStatus.ESCALATED,
            "fallback_reason": "Chybí data z silver_company_master",
            "audit_trail":     audit,
        }

    if not raw_data.get("fin_profile"):
        audit = _audit(
            state,
            node="ExtractionValidator",
            action="validation_failed",
            result="missing_fin_profile",
            metadata={"ico": ico},
        )
        return {
            **state,
            "status":          ProcessStatus.FROZEN,
            "fallback_reason": "Chybí finanční profil — nelze počítat metriky",
            "audit_trail":     audit,
        }

    if not raw_data.get("credit"):
        audit = _audit(
            state,
            node="ExtractionValidator",
            action="validation_failed",
            result="missing_credit_history",
            metadata={"ico": ico},
        )
        return {
            **state,
            "status":          ProcessStatus.FROZEN,
            "fallback_reason": "Chybí kreditní historie",
            "audit_trail":     audit,
        }

    # Typová kontrola kritických polí (varování, ne freeze)
    extraction_warnings: list[str] = []
    credit = raw_data.get("credit", [{}])
    fin_profile = raw_data.get("fin_profile", {})
    critical_fields = {
        "approved_limit_czk":      (credit[0] if credit else {}, float),
        "outstanding_balance_czk": (credit[0] if credit else {}, float),
        "utilisation_pct":         (credit[0] if credit else {}, float),
        "dpd_current":             (credit[0] if credit else {}, int),
        "credit_limit_utilization": (fin_profile, float),
        "avg_monthly_turnover":    (fin_profile, float),
        "internal_rating_score":   (fin_profile, float),
    }
    for field, (source_dict, cast_type) in critical_fields.items():
        val = source_dict.get(field)
        if val is not None:
            try:
                cast_type(val)
            except (ValueError, TypeError):
                extraction_warnings.append(f"Pole '{field}' nelze přetypovat na {cast_type.__name__}: {val!r}")

    if extraction_warnings:
        log.warning(
            f"[ExtractionValidator] Typová varování | ico={ico} warnings={extraction_warnings}"
        )

    fields_ok = 7 - len(extraction_warnings)
    log.info(
        f"[ExtractionValidator] Validace OK | ico={ico} "
        f"confidence={confidence:.2f} fields_ok={fields_ok}/7 "
        f"warnings={len(extraction_warnings)}"
    )

    audit = _audit(
        state,
        node="ExtractionValidator",
        action="validation_passed",
        result="passed",
        metadata={
            "ico":                 ico,
            "confidence_score":    confidence,
            "fields_validated":    fields_ok,
            "extraction_warnings": extraction_warnings,
            "credit_rows":         len(raw_data.get("credit", [])),
            "transaction_rows":    len(raw_data.get("transactions", [])),
        },
    )
    return {**state, "audit_trail": audit}


# ── Privátní helpers ───────────────────────────────────────────────────────────


def _build_extraction_from_raw_data(ico: str, raw_data: dict) -> dict:
    """
    Sestaví standardní extraction_result ze Silver tabulkových dat.
    DETERMINISTIC — čistý Python.
    """
    company    = raw_data.get("company", {})
    fin_profile = raw_data.get("fin_profile", {})
    credit     = raw_data.get("credit", [])

    # Agregace z credit_history
    total_limit       = sum(float(r.get("approved_limit_czk", 0) or 0) for r in credit)
    total_outstanding = sum(float(r.get("outstanding_balance_czk", 0) or 0) for r in credit)
    max_dpd           = max((int(r.get("dpd_current", 0) or 0) for r in credit), default=0)
    util_pct          = (total_outstanding / total_limit * 100) if total_limit > 0 else 0.0
    relationship_yrs  = max((float(r.get("relationship_years", 0) or 0) for r in credit), default=0.0)
    cmp_monitored     = any(r.get("cmp_flag", "false") == "true" for r in credit)
    is_restructured   = any(r.get("restructured", "false") == "true" for r in credit)

    # Aktivní covenant status
    covenant_status = "OK"
    for r in credit:
        if r.get("covenant_breach", "false") == "true":
            covenant_status = r.get("covenant_status", "BREACH")
            break
    if covenant_status == "OK" and credit:
        covenant_status = credit[0].get("covenant_status", "OK")

    return {
        "company_name":              company.get("company_name", ""),
        "ico":                       ico,
        "raw_data":                  raw_data,
        # Pole dostupná ze Silver tabulek
        "credit_limit":              total_limit,
        "current_utilisation":       total_outstanding,
        "utilisation_pct":           round(util_pct, 1),
        "dpd_current":               max_dpd,
        "covenant_status":           covenant_status,
        "cmp_monitored":             cmp_monitored,
        "is_restructured":           is_restructured,
        "relationship_years":        relationship_yrs,
        "portfolio_status":          "ACTIVE",
        # financial_data prázdné — EBITDA/Net Debt/atd. vyžadují CRIBIS
        "financial_data":            {},
        # Metadata
        "confidence_score":          1.0,   # Strukturovaná DB data = plná důvěra
        "sources_used":              list(_SILVER_DATA_SOURCES.keys()),
        "data_sources":              dict(_SILVER_DATA_SOURCES),
        "missing_external_metrics":  list(_MISSING_EXTERNAL_METRICS),
    }


def _extract_json(text: str) -> str:
    """Extrahuje JSON ze surové LLM odpovědi (markdown nebo holý JSON)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text


if __name__ == "__main__":
    # Smoke test — Silver mode
    from pipeline.state import make_initial_state

    state = make_initial_state("27082440", "REQ-SMOKE-001")
    state = data_extractor_agent(state)
    assert state.get("status") != ProcessStatus.FROZEN, f"Neočekávaný freeze: {state.get('fallback_reason')}"
    assert state["extraction_result"] is not None, "extraction_result chybí"
    assert state["extraction_result"]["ico"] == "27082440"
    assert "raw_data" in state["extraction_result"], "raw_data chybí"
    print(f"  company: {state['extraction_result']['company_name']}")
    print(f"  credit_limit: {state['extraction_result']['credit_limit']:,.0f}")
    print(f"  dpd_current: {state['extraction_result']['dpd_current']}")

    state = extraction_validator(state)
    assert state.get("status") != ProcessStatus.FROZEN, f"Neočekávaný freeze: {state.get('fallback_reason')}"
    print(f"  audit_events: {len(state['audit_trail'])}")

    # Test neznámé IČO
    state2 = make_initial_state("99999999", "REQ-SMOKE-002")
    state2 = data_extractor_agent(state2)
    assert state2["status"] == ProcessStatus.FROZEN
    print("  FROZEN pro neznámé IČO: OK")

    print("OK — phase1_extraction.py smoke test passed")
