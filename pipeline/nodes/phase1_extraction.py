# AI + DETERMINISTIC
"""
Fáze 1 — Extrakce dat — pipeline/nodes/phase1_extraction.py

Uzly:
  - data_extractor_agent    ← LLM extrakce z dokumentů (AI)
  - extraction_validator    ← validace confidence_score (DETERMINISTIC)

AI uzel používá: extractor_skill.yaml
Fallback při API chybě: Process Freeze (NE T-1 fallback).
Demo mode: pokud raw_documents prázdné → použije mock_data.
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


# AI
def data_extractor_agent(state: dict) -> dict:
    """
    Extrahuje strukturovaná finanční data z dokumentů pomocí LLM (Claude).

    Strategie:
    1. Pokud raw_documents prázdné → Demo mode (mock_data)
    2. Jinak: semantic chunking + Claude API (max 3 pokusy)
    3. API chyba → Process Freeze (NE fallback na T-1 data)

    Vstupy ze state:
        ico:           str  — IČO klienta
        raw_documents: dict[source_id → text]  — raw texty (volitelné)

    Výstupy do state:
        extraction_result:   dict  — extrahovaná data
        extraction_attempts: int   — počet pokusů
    """
    ico = state.get("ico", "UNKNOWN")
    log.info(f"[DataExtractorAgent] Zahajuji extrakci | ico={ico}")

    skill = registry.get("extractor_skill")
    prompt = skill["prompt"]
    skill_version = skill["version"]

    raw_documents: dict = state.get("raw_documents") or {}

    # ── Demo mode ──────────────────────────────────────────────────────────────
    if not raw_documents:
        log.info(f"[DataExtractorAgent] Demo mode — raw_documents prázdné | ico={ico}")
        from utils.mock_data import get_client

        client = get_client(ico)
        if client is None:
            log.error(f"[DataExtractorAgent] IČO {ico} nenalezeno v mock datech")
            audit = _audit(
                state,
                node="DataExtractorAgent",
                action="extraction_failed",
                result="unknown_ico",
                prompt=prompt,
                prompt_version=skill_version,
                metadata={"ico": ico, "mode": "demo"},
            )
            return {
                **state,
                "status": ProcessStatus.FROZEN,
                "fallback_reason": f"IČO {ico} nenalezeno v systému",
                "extraction_attempts": state.get("extraction_attempts", 0) + 1,
                "audit_trail": audit,
            }

        extraction_result = _mock_extraction_from_client(client)
        log.info(
            f"[DataExtractorAgent] Demo extrakce hotova | ico={ico} "
            f"company={extraction_result['company_name']}"
        )
        audit = _audit(
            state,
            node="DataExtractorAgent",
            action="extraction_demo_mode",
            result="success",
            prompt=prompt,
            prompt_version=skill_version,
            tokens_used=0,
            metadata={
                "ico":              ico,
                "mode":             "demo",
                "confidence_score": extraction_result["confidence_score"],
                "sources_count":    len(extraction_result["sources_used"]),
            },
        )
        return {
            **state,
            "extraction_result":   extraction_result,
            "extraction_attempts": state.get("extraction_attempts", 0) + 1,
            "audit_trail":         audit,
        }

    # ── Chunking dokumentů ─────────────────────────────────────────────────────
    all_chunks = []
    for source_id, doc_text in raw_documents.items():
        chunks = semantic_chunk(doc_text, source_id=source_id)
        all_chunks.extend(chunks)

    context = chunks_to_context(all_chunks)
    user_message = (
        f"IČO klienta: {ico}\n\n"
        f"DOKUMENTY K EXTRAKCI:\n{context}\n\n"
        f"Extrahuj všechna povinná pole a vrať validní JSON."
    )

    # ── Claude API s retry ─────────────────────────────────────────────────────
    attempts = state.get("extraction_attempts", 0)
    last_error: str | None = None

    for attempt in range(1, API_RETRY_COUNT + 1):
        attempts += 1
        log.info(
            f"[DataExtractorAgent] API volání pokus {attempt}/{API_RETRY_COUNT} | ico={ico}"
        )
        try:
            import anthropic

            api_client = anthropic.Anthropic()
            response = api_client.messages.create(
                model="claude-opus-4-6",
                max_tokens=2048,
                system=prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_text = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            json_text = _extract_json(raw_text)
            extraction_result = json.loads(json_text)
            # Doplnění data_sources mapou ze zdrojů dokumentů
            extraction_result.setdefault(
                "data_sources", {s: s for s in raw_documents}
            )

            log.info(
                f"[DataExtractorAgent] Extrakce úspěšná | ico={ico} "
                f"attempt={attempt} tokens={tokens_used} "
                f"confidence={extraction_result.get('confidence_score', 'N/A')}"
            )
            audit = _audit(
                state,
                node="DataExtractorAgent",
                action="extraction_completed",
                result="success",
                prompt=prompt,
                prompt_version=skill_version,
                tokens_used=tokens_used,
                metadata={
                    "ico":              ico,
                    "attempt":          attempt,
                    "confidence_score": extraction_result.get("confidence_score", 0.0),
                    "sources_used":     extraction_result.get("sources_used", []),
                },
            )
            return {
                **state,
                "extraction_result":   extraction_result,
                "extraction_attempts": attempts,
                "audit_trail":         audit,
            }

        except Exception as exc:
            last_error = str(exc)
            log.warning(
                f"[DataExtractorAgent] API chyba pokus {attempt}/{API_RETRY_COUNT} | "
                f"ico={ico} error={last_error}"
            )
            if attempt < API_RETRY_COUNT:
                log.info(
                    f"[DataExtractorAgent] Čekám {API_RETRY_DELAY_SEC}s "
                    "před dalším pokusem"
                )
                time.sleep(API_RETRY_DELAY_SEC)

    # ── Process Freeze — všechny pokusy selhaly ────────────────────────────────
    log.error(
        f"[DataExtractorAgent] Process Freeze | ico={ico} "
        f"attempts={attempts} last_error={last_error}"
    )
    audit = _audit(
        state,
        node="DataExtractorAgent",
        action="extraction_failed",
        result="process_freeze",
        prompt=prompt,
        prompt_version=skill_version,
        metadata={"ico": ico, "attempts": attempts, "last_error": last_error},
    )
    return {
        **state,
        "status":              ProcessStatus.FROZEN,
        "fallback_reason":     f"API selhala po {API_RETRY_COUNT} pokusech: {last_error}",
        "extraction_attempts": attempts,
        "audit_trail":         audit,
    }


# DETERMINISTIC
def extraction_validator(state: dict) -> dict:
    """
    Validuje výsledek extrakce:
    - extraction_result existuje
    - confidence_score >= MIN_CONFIDENCE_SCORE (0.85)
    - IČO: přesně 8 číslic
    - Povinná finanční pole přítomna (varování, NE freeze při chybějících)

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
            "status":         ProcessStatus.FROZEN,
            "fallback_reason": "Chybí extraction_result po extrakci",
            "audit_trail":    audit,
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
            "status":         ProcessStatus.FROZEN,
            "fallback_reason": (
                f"Confidence score {confidence:.2f} < minimum {MIN_CONFIDENCE_SCORE}"
            ),
            "audit_trail": audit,
        }

    # IČO formát
    extracted_ico = str(extraction.get("ico", ""))
    if not extracted_ico.isdigit() or len(extracted_ico) != 8:
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

    # Povinná finanční pole — varování (ne freeze)
    required = [
        "revenue", "ebitda", "net_debt", "total_assets",
        "current_assets", "current_liabilities", "debt_service", "operating_cashflow",
    ]
    fd = extraction.get("financial_data", {})
    missing = [f for f in required if fd.get(f) is None]
    if missing:
        log.warning(
            f"[ExtractionValidator] Chybí finanční pole (pokračuji) | "
            f"ico={ico} missing={missing}"
        )

    fields_ok = len(required) - len(missing)
    log.info(
        f"[ExtractionValidator] Validace OK | ico={ico} "
        f"confidence={confidence:.2f} fields={fields_ok}/{len(required)}"
    )

    audit = _audit(
        state,
        node="ExtractionValidator",
        action="validation_passed",
        result="passed",
        metadata={
            "ico":              ico,
            "confidence_score": confidence,
            "fields_validated": fields_ok,
            "missing_fields":   missing,
        },
    )
    return {**state, "audit_trail": audit}


# ── Privátní helpers ───────────────────────────────────────────────────────────


def _extract_json(text: str) -> str:
    """Extrahuje JSON ze surové LLM odpovědi (markdown nebo holý JSON)."""
    # Markdown JSON blok
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Holý JSON
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text


def _mock_extraction_from_client(client: dict) -> dict:
    """Převede mock klienta na standardní extraction_result formát."""
    return {
        "company_name":       client["company_name"],
        "ico":                client["ico"],
        "financial_data":     client["financial_data"],
        "credit_limit":       client["credit_limit"],
        "current_utilisation": client["current_utilisation"],
        "dpd_current":        client["dpd_current"],
        "cribis_rating":      client.get("cribis_rating"),
        "esg_score":          client.get("esg_score"),
        "katastr_data":       client.get("katastr_data"),
        "flood_risk":         client.get("flood_risk"),
        "historical_memos":   [f"Memo {client['last_memo_date']} — viz Helios"],
        "portfolio_status":   client.get("portfolio_status", "ACTIVE"),
        "confidence_score":   0.92,
        "sources_used":       list(client.get("data_sources", {}).keys()),
        "data_sources":       client.get("data_sources", {}),
    }


if __name__ == "__main__":
    # Smoke test — demo mode
    from pipeline.state import make_initial_state

    state = make_initial_state("27082440", "REQ-SMOKE-001")
    state = data_extractor_agent(state)
    assert state["extraction_result"] is not None, "extraction_result chybí"
    assert state["extraction_result"]["ico"] == "27082440"
    print(f"  company: {state['extraction_result']['company_name']}")
    print(f"  confidence: {state['extraction_result']['confidence_score']}")

    state = extraction_validator(state)
    assert state.get("status") != ProcessStatus.FROZEN, f"Neočekávaný freeze: {state.get('fallback_reason')}"
    print(f"  audit_events: {len(state['audit_trail'])}")

    # Test neznámé IČO
    state2 = make_initial_state("99999999", "REQ-SMOKE-002")
    state2 = data_extractor_agent(state2)
    assert state2["status"] == ProcessStatus.FROZEN
    print(f"  FROZEN pro neznámé IČO: OK")

    print("OK — phase1_extraction.py smoke test passed")
